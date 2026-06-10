"""前台交互通道：Conversation Gateway。

对应方案第 7 章。用户输入的唯一入口：
1. 立即接住用户（即时模板回应 / 确定性上下文问答），保证 300-800ms 内有可见回应。
2. 识别意图并路由：上下文问答走 facts，业务任务挂到后台 job，确认/下发/取消唤醒 job。
3. barge-in：用户插话时推进 generation、广播 interaction.interrupted，旧字幕/音频失效。
4. 回声拒绝：识别到数字人自己的播报内容时不创建业务 turn。

前台永不被后台 job 阻塞：job 在确认点用 asyncio 信号挂起，由本网关唤醒。
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import re
from typing import TYPE_CHECKING

from .. import mock_data, platform_bridge
from ..agent_brain import agent_brain
from ..claude_code_client import claude_client
from ..config import settings
from ..constants import DemoState, SharkState
from ..tasks import spawn
from . import business
from .events import Ev, event_bus
from .facts import facts_resolver
from .models import JobStatus, Priority, Turn, TurnRoute, next_turn_id
from .narration import narration
from .presenter import presenter
from .speaker import speaker
from .workflow import workflow_engine

if TYPE_CHECKING:
    from ..session_store import Session

logger = logging.getLogger("interaction.gateway")

ARRANGE_KEYWORDS = (
    "安排", "考试", "测评", "考核", "出题", "出一套", "考一下", "组织", "ct", "CT", "测试",
)

_CONFIRM_POSITIVE_PATTERNS = (
    r"^(好|好的|好啊|好吧|好嘞|行|行啊|行吧|行的|那行|可以|可以了|可以吧|可以呀|可|嗯|嗯嗯|嗯好|嗯可以|ok|ok了|ok吧)$",
    r"没问题|没意见|没异议|没毛病|没错|可以的|可以继续",
    r"同意|通过|认可|批准|确认|确定|定了|就这么定",
    r"就这样|就按(这个|这套|你说的|刚才的|方案)|按(这个|这套|你说的|刚才的|方案).*(来|办|执行|准备)?",
    r"照(这个|这套|刚才的|方案).*(来|办|执行|准备)?",
    r"继续|往下|下一步|开始吧|开始准备|准备吧|执行吧|安排吧|走吧|来吧",
)

_PUBLISH_POSITIVE_PATTERNS = (
    r"下发|发布|发(给|下去|出去|吧|一下)|推送|开考",
    r"给.*(发|下发|发布)",
    r"让(他们|学员).*(开始|做|答|考试)",
    r"开始考试|开放答题|生成入口|二维码",
)

_NEGATIVE_CONFIRM_PATTERNS = (
    r"不行|不可以|不要|先不|暂时不|等一下|再等等|先等等|有问题|不同意|不通过|不确定|算了|别",
)

# 即时回应模板（硬保障：不依赖模型，先接住用户）
ACK = {
    "arrange": "收到。我先按胸部 CT 基础诊断考试来准备，会同步整理方案、查询学员名单和匹配题库。",
    "confirm_plan": "好的。我继续往下创建试卷草稿，过程会边做边告诉您。",
    "confirm_publish": "收到。我开始下发考试，同时盯住学员进入和提交情况。",
    "publish": "收到。我开始下发考试，同时盯住学员进入和提交情况。",
    "cancel": "好的。我先停一下当前流程。",
    "pause": "好的。我先暂停，您随时让我继续。",
    "reset": "好的。我把演示重置，您可以重新开始。",
    "modify": "可以。我先记下这个调整，再同步更新考试方案。",
}

# 执行较慢的查询 / CC 任务时的「执行中安抚」轮播句：保持与用户的语音沟通，不让其干等工具返回。
REASSURE_LINES = (
    "还在查，请您稍等一下。",
    "我正在调取相关数据，马上就好。",
    "这边还在处理，尽快给您结果。",
)

# 疑似「需要查平台数据 / 复杂分析」的问题：未命中固定 skill 时交给 CC 自主编排工具并组织答案。
_AGENTIC_HINT_RE = re.compile(
    "考试|学员|学生|成绩|分数|及格|通过率|题目|题库|教学|阅片|病例|复训|训练|"
    "数据|看板|统计|报告|分析|对比|评估|掌握|薄弱|知识点|建议|方案|怎么|如何|"
    "为什么|哪些|多少|情况|表现|进度|排课|计划|推荐"
)


class ConversationGateway:
    # ------------------------------------------------------------------ #
    # 用户输入唯一入口
    # ------------------------------------------------------------------ #
    async def handle_turn(
        self,
        s: "Session",
        text: str,
        *,
        source: str = "voice",
        barge_in: bool = False,
        interrupts_utterance_id: str | None = None,
        interrupt_policy: str | None = None,
        preassigned_turn_id: str | None = None,
    ) -> Turn:
        text = (text or "").strip()
        turn = Turn(
            turn_id=preassigned_turn_id or next_turn_id(),
            session_id=s.session_id,
            text=text,
            source=source,
            barge_in=barge_in,
            interrupts_utterance_id=interrupts_utterance_id,
            interrupt_policy=interrupt_policy,
        )
        if not text:
            return turn

        s.conversation["last_user_text"] = text

        # 回声拒绝：识别到数字人自己的播报，不创建业务 turn
        if source == "voice" and self._is_echo(s, text):
            s.metrics["echo_rejected_count"] += 1
            await event_bus.emit(
                s, Ev.INTERACTION_BARGE_IGNORED,
                {"reason": "echo_rejected", "text": text}, priority=Priority.LOW.value,
            )
            return turn

        s.add_turn(turn)
        # 语音交互即 UI：用户一旦真实开口，立刻标记前台活跃，
        # 后台「过程类」播报随即让路，避免淹没/抢占用户的语音交互通道。
        if source != "control":
            s.mark_user_active()

        # barge-in：正在播报且本次是真实输入 -> 打断低/普通优先级播报
        if (barge_in or s.interaction.get("speaking")) and source != "control":
            await self.handle_interrupt(
                s, policy=interrupt_policy or "stop_low_priority",
                new_turn_id=turn.turn_id, reason="user_barge_in",
                utterance_id=interrupts_utterance_id,
            )

        await presenter.emit_user_message(s, text, turn_id=turn.turn_id)
        # 立即给出「思考中」过渡态，覆盖意图识别（可能含 LLM 调用）的耗时，消除空窗感
        await presenter.set_shark(s, SharkState.THINKING)

        route = await self._route_intent(s, text)
        turn.routed_as = route.value
        s.conversation["last_user_intent"] = route.value

        if route == TurnRoute.RESET:
            await self._route_reset(s, turn)
        elif route in (TurnRoute.CANCEL,):
            await self._route_cancel(s, turn, pause=False)
        elif route == TurnRoute.MODIFY:
            await self._route_modify(s, turn, text)
        elif route == TurnRoute.CONTEXT_QUESTION:
            await self._route_context_question(s, turn, text)
        elif route == TurnRoute.BUSINESS_QUERY:
            await self._route_business_query(s, turn)
        elif route == TurnRoute.CONFIRM:
            await self._route_confirm(s, turn)
        elif route == TurnRoute.PUBLISH:
            await self._route_publish(s, turn)
        elif route == TurnRoute.START_JOB:
            await self._route_arrange(s, turn)
        else:
            await self._route_smalltalk(s, turn, text)
        return turn

    # ------------------------------------------------------------------ #
    # 打断
    # ------------------------------------------------------------------ #
    async def handle_interrupt(
        self,
        s: "Session",
        *,
        policy: str = "stop_low_priority",
        new_turn_id: str | None = None,
        reason: str = "user_barge_in",
        utterance_id: str | None = None,
        job_policy: str = "continue",
    ) -> None:
        old_utt = utterance_id or s.interaction.get("current_utterance_id")
        old_priority = s.interaction.get("current_utterance_priority")
        # 确认请求 / urgent 播报不被普通插话打断
        if policy == "stop_low_priority" and old_priority in (
            Priority.HIGH.value, Priority.URGENT.value,
        ):
            stopped: list[str] = []
        else:
            s.bump_generation()
            s.interaction["speaking"] = False
            s.interaction["current_utterance_id"] = None
            s.interaction["current_utterance_priority"] = None
            # 真实打断：延长前台活跃窗口，避免后台 job 下一拍立刻重新抢播。
            s.mark_user_active()
            stopped = ["low", "normal"] if policy == "stop_low_priority" else ["low", "normal", "high"]

        affected_job = s.active_jobs()[0].job_id if s.active_jobs() else None
        await event_bus.emit(
            s,
            Ev.INTERACTION_INTERRUPTED,
            {
                "reason": reason,
                "new_turn_id": new_turn_id,
                "stopped_priorities": stopped,
                "affected_job_id": affected_job,
                "job_policy": job_policy,
                "interrupt_generation": s.interaction["interrupt_generation"],
            },
            turn_id=new_turn_id,
            utterance_id=old_utt,
            priority=Priority.URGENT.value,
            generation=s.generation,
        )

    # ------------------------------------------------------------------ #
    # 路由处理
    # ------------------------------------------------------------------ #
    async def _route_context_question(self, s: "Session", turn: Turn, text: str) -> None:
        qa = facts_resolver.answer(s, text)
        turn.routed_as = TurnRoute.CONTEXT_QUESTION.value
        s.conversation["last_answer_topic"] = qa.topic
        s.record_first_response(turn)
        priority = Priority.HIGH.value
        await speaker.say(
            s, qa.text, priority=priority, turn_id=turn.turn_id,
            source="context_qa", shark_state=SharkState.SPEAKING,
        )
        # 回答后，若后台积压了与问题相关的进展，补一段总结（不逐条补播）。
        # 这是「响应用户提问」的补播，用户正在等回答，不受前台活跃让路限制。
        if narration.has_pending(s):
            await narration.flush(
                s, focus_topic=qa.topic, turn_id=turn.turn_id, respect_user_active=False
            )
        await self._restore_idle_shark(s)

    async def _route_business_query(self, s: "Session", turn: Turn) -> None:
        """业务查询：调用 medteach-agent-core 真实工具箱取数，刷新大屏面板并口播总结。

        这是修复「控制台选 Real，问答仍走强制模板」的核心：业务问题不再被本地
        facts 模板拦截，而是真正命中 TeachingPlatformClient（real/hybrid/mock）。
        """
        intent = s.conversation.pop("pending_business_intent", None) or business.detect_intent(turn.text)
        sp = business.spec(intent) if intent else None
        if sp is None:
            await self._route_smalltalk(s, turn, turn.text)
            return
        turn.routed_as = TurnRoute.BUSINESS_QUERY.value
        s.conversation["last_business_intent"] = intent
        s.record_first_response(turn)
        title = sp["title"]
        logger.info(
            "route=business_query intent=%s engine=%s skill=%s",
            intent, settings.AGENT_ENGINE, sp["skill"],
        )
        await presenter.set_shark(s, SharkState.WORKING, f"正在查询{title}…")
        await presenter.emit_screen_event(
            s,
            {"type": "tool_call_started", "title": f"正在查询{title}",
             "message": f"调用真实工具箱 · {sp['skill']}", "status": "running", "module": intent},
        )
        # 1) 立即安抚：先接住用户、保持语音沟通，不让其干等工具返回（前台不被后台执行阻塞）。
        await speaker.say(
            s, f"好的，我现在去查一下{title}，稍等。",
            priority=Priority.NORMAL.value, turn_id=turn.turn_id,
            source="reassure", shark_state=SharkState.WORKING,
        )
        # 2) 执行真实工具箱取数：带「执行中安抚」心跳，慢任务期间周期补一句，保持沟通。
        import time as _time

        _t0 = _time.monotonic()
        res = await self._await_with_reassurance(
            s, turn, self._safe_cached_read(intent, sp["call"]),
        )
        elapsed = _time.monotonic() - _t0
        data = res.get("data") if isinstance(res, dict) else None
        fallback = bool(res.get("fallback")) if isinstance(res, dict) else True

        # 通用业务数据面板（大屏 BusinessDataPanel）
        await event_bus.emit_legacy(
            s, "business_data_update",
            {"module": intent, "title": title, "data": data, "fallback": fallback},
        )
        # 专属面板：学员名册 / 成绩报告 / 病例推荐（与金线 workflow 同款事件）
        panel = sp.get("panel")
        if data is not None and panel == "students":
            s.students = data
            await presenter.emit_domain(
                s, fact_path="participants", legacy_type="students_update",
                legacy_data={"students": data},
            )
        elif data is not None and panel == "result":
            s.result = data
            await presenter.emit_domain(
                s, fact_path="result", legacy_type="exam_result_update",
                legacy_data={"result": data},
            )
        elif data is not None and panel == "recommendation":
            s.recommendation = data
            await presenter.emit_domain(
                s, fact_path="recommendation", legacy_type="case_recommendation_update",
                legacy_data={"recommendation": data},
            )

        facts = business.summarize(intent, data, fallback)
        summary = await self._compose_business_answer(s, turn, facts)
        # 3) 主动汇报：查询完成，向用户汇报结果。耗时较久时加「查好了」衔接，秒回则直接说结果。
        report = self._as_report(title, summary, elapsed)
        await speaker.say(
            s, report, priority=Priority.HIGH.value, turn_id=turn.turn_id,
            source="business_qa", shark_state=SharkState.SPEAKING,
        )
        await presenter.emit_screen_event(
            s,
            {"type": sp["ready_event"], "title": title, "message": report,
             "status": "completed", "module": intent, "fallback": fallback},
        )
        await self._restore_idle_shark(s)

    async def _safe_cached_read(self, intent: str, call) -> dict:
        """真实工具箱取数（永不抛）：超时/异常都吞成 dict 结果，保证展厅不翻车。"""
        try:
            # 预热缓存命中即时返回真数据；冷调用 5~20s，故超时放宽到 25s。
            res = await asyncio.wait_for(
                platform_bridge.cached_read(intent, call), timeout=25.0
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("business query %s failed: %s", intent, exc)
            res = {"ok": False, "fallback": True, "data": None, "error": {"message": str(exc)}}
        return res if isinstance(res, dict) else {"ok": False, "fallback": True, "data": None}

    async def _await_with_reassurance(
        self,
        s: "Session",
        turn: Turn,
        coro,
        *,
        reassure_lines: tuple[str, ...] = REASSURE_LINES,
        first_delay: float = 3.0,
        interval: float = 4.5,
    ):
        """等待较慢任务；执行期间周期补一句安抚口播，保持与用户的语音沟通（前台不被阻塞）。

        安抚走 speaker.say（NORMAL，可被打断）；用户插话会推进 generation，speaker 检测到
        即中止本句，不会与用户抢话。传入的 coro 必须自带兜底（永不抛），异常请在 coro 内吞掉。
        """
        task = asyncio.ensure_future(coro)
        gen = s.generation
        tick = 0
        while not task.done():
            timeout = first_delay if tick == 0 else interval
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except asyncio.TimeoutError:
                # 用户已打断本轮（新一代）或正在说话：不抢话，仅静默等任务收尾。
                if s.generation == gen and not s.user_active:
                    line = reassure_lines[tick % len(reassure_lines)]
                    await speaker.say(
                        s, line, priority=Priority.NORMAL.value, turn_id=turn.turn_id,
                        source="reassure", shark_state=SharkState.WORKING,
                    )
                tick += 1
        return task.result()

    @staticmethod
    def _as_report(title: str, summary: str, elapsed: float) -> str:
        """完成汇报话术：耗时较久时加「查好了」衔接（主动告知完成），秒回则直接说结果。"""
        summary = (summary or "").strip()
        if not summary:
            return f"{title}我看过了，不过这次没拿到更多可说的内容。"
        if elapsed >= 2.0:
            return f"好，{title}我查好了。{summary}"
        return summary

    async def _refine_business_answer(self, s: "Session", user_text: str, facts: str) -> str:
        """用 LLM 把确定性事实话术按用户问法自然改写；失败/超时回退事实话术（杜绝编造）。"""
        if not settings.voice_summary_llm_enabled:
            return facts
        refined = await agent_brain.refine_answer(
            user_text=user_text, facts=facts, budget=settings.VOICE_SUMMARY_LLM_BUDGET,
        )
        return refined or facts

    async def _compose_business_answer(self, s: "Session", turn: Turn, facts: str) -> str:
        """生成业务回答话术（引擎可切换，三层兑底永不翻车）。

        AGENT_ENGINE：
        - ``claude``：交给 Claude Code 自主选 MCP 工具、调真实工具箱、口语化总结，
          完整落地「意图识别→交给 Claude 工具调用总结→语音回答」链路。
        - ``hybrid`` / ``deepseek``：DeepSeek flash 按用户问法自然改写确定性事实（快路径，
          展厅默认，300ms~3s 出话，保证流畅无感）。
        Claude 失败/超时 → 回退 DeepSeek 改写 → 回退确定性事实。
        """
        if settings.AGENT_ENGINE == "claude" and settings.claude_agentic_enabled:
            agentic = await self._agentic_business_answer(turn.text)
            if agentic:
                s.conversation["last_answer_engine"] = "claude_agentic"
                return agentic
        s.conversation["last_answer_engine"] = "deepseek_refine"
        return await self._refine_business_answer(s, turn.text, facts)

    async def _agentic_business_answer(self, user_text: str) -> str | None:
        """交给 Claude：自主选 MCP 工具、调真实工具箱、口语化总结。失败/超时返回 None。"""
        try:
            result = await claude_client.run_agentic_query(user_text)
        except Exception as exc:  # noqa: BLE001 - 任何异常都回退快路径，保证展厅不翻车
            logger.warning("claude agentic business answer failed: %s", exc)
            return None
        text = (result or {}).get("assistant_text")
        return text.strip() if isinstance(text, str) and text.strip() else None

    async def _route_arrange(self, s: "Session", turn: Turn) -> None:
        # 已有进行中的安排 job：当作上下文/澄清，避免重复起任务
        running = [j for j in s.active_jobs() if j.type == "arrange_exam"]
        if running:
            s.record_first_response(turn)
            await speaker.say(
                s, "这场考试我已经在准备了，您可以问我目前到哪一步，或确认是否继续。",
                priority=Priority.HIGH.value, turn_id=turn.turn_id, source="dialogue",
            )
            await self._restore_idle_shark(s)
            return
        # 即时接住用户（硬保障，先于任何后台任务）
        s.record_first_response(turn)
        await speaker.say(
            s, ACK["arrange"], priority=Priority.HIGH.value, turn_id=turn.turn_id, source="ack",
        )
        # 挂起后台 job
        job = workflow_engine.create_job(s, "arrange_exam", turn_id=turn.turn_id)
        turn.related_job_id = job.job_id
        await presenter.emit_job(s, job)
        spawn(workflow_engine.run_arrange_exam(s, job))

    async def _route_confirm(self, s: "Session", turn: Turn) -> None:
        job = self._waiting_job(s, "confirm_plan")
        s.record_first_response(turn)
        if job is None:
            await speaker.say(
                s, "现在还没有需要确认的方案，您可以先对我说「安排一场胸部 CT 基础考试」。",
                priority=Priority.HIGH.value, turn_id=turn.turn_id, source="dialogue",
            )
            await self._restore_idle_shark(s)
            return
        await speaker.say(
            s, ACK["confirm_plan"], priority=Priority.HIGH.value,
            turn_id=turn.turn_id, source="ack",
        )
        sig = workflow_engine.signals(job.job_id)
        if sig:
            sig.confirm.set()

    async def _route_publish(self, s: "Session", turn: Turn) -> None:
        job = self._waiting_job(s, "confirm_publish")
        s.record_first_response(turn)
        if job is None:
            await speaker.say(
                s, "现在还没有可下发的试卷，等试卷预览准备好我会提醒您确认。",
                priority=Priority.HIGH.value, turn_id=turn.turn_id, source="dialogue",
            )
            await self._restore_idle_shark(s)
            return
        await speaker.say(
            s, ACK["confirm_publish"], priority=Priority.HIGH.value,
            turn_id=turn.turn_id, source="ack",
        )
        sig = workflow_engine.signals(job.job_id)
        if sig:
            sig.confirm.set()

    async def _route_cancel(self, s: "Session", turn: Turn, *, pause: bool) -> None:
        s.record_first_response(turn)
        jobs = s.active_jobs()
        for job in jobs:
            if pause:
                job.pause_requested = True
                job.status = JobStatus.PAUSED.value
            else:
                job.cancel_requested = True
            sig = workflow_engine.signals(job.job_id)
            if sig:
                sig.cancel.set()
            await presenter.emit_job(s, job)
        await speaker.say(
            s, ACK["pause"] if pause else ACK["cancel"], priority=Priority.URGENT.value,
            turn_id=turn.turn_id, source="control", interruptible=False,
        )
        s.busy = bool(s.active_jobs())
        await presenter.emit_state(s)
        await self._restore_idle_shark(s)

    async def _route_modify(self, s: "Session", turn: Turn, text: str) -> None:
        s.record_first_response(turn)
        updated = self._apply_modification(s, text)
        await speaker.say(
            s, ACK["modify"], priority=Priority.HIGH.value, turn_id=turn.turn_id, source="ack",
        )
        if updated and s.exam_plan:
            await presenter.emit_domain(
                s, fact_path="exam_plan", legacy_type="exam_plan_update",
                legacy_data={"exam_plan": s.exam_plan},
            )
            q = s.exam_plan.get("question_structure", {})
            total_q = s.exam_plan.get("question_total") or (
                q.get("single_choice", 0) + q.get("multiple_choice", 0) + q.get("case_analysis", 0)
            )
            await speaker.say(
                s,
                f"已经把方案更新成 {s.exam_plan.get('student_count', 8)} 名学员、"
                f"{s.exam_plan.get('duration_minutes', 15)} 分钟、{total_q} 道题。您看这样可以吗？",
                priority=Priority.HIGH.value, turn_id=turn.turn_id, source="dialogue",
            )
        await self._restore_idle_shark(s)

    async def _route_reset(self, s: "Session", turn: Turn) -> None:
        s.record_first_response(turn)
        for job in s.active_jobs():
            job.cancel_requested = True
            sig = workflow_engine.signals(job.job_id)
            if sig:
                sig.cancel.set()
        await self.reset(s)

    async def _route_smalltalk(self, s: "Session", turn: Turn, text: str) -> None:
        # 复杂/疑似业务问题：交给 Claude Code 自主选 MCP 工具、调真实工具箱、组织答案（CC 底色）。
        # 命中固定 skill 的标准查询不会落到这里（已被 BUSINESS_QUERY 处理），简单查询仍走快路径秒回。
        if settings.claude_agentic_enabled and self._looks_agentic(text):
            if await self._route_agentic_smalltalk(s, turn, text):
                return
        if settings.chat_llm_configured:
            from ..agent_brain import agent_brain
            from .. import mock_data

            await presenter.set_shark(s, SharkState.THINKING)
            stream = agent_brain.stream_smalltalk(
                message=text, state=s.state,
                need_confirm=s.need_user_confirmation, confirmation_type=s.confirmation_type,
                default_plan=mock_data.exam_plan_default(),
            )
            s.record_first_response(turn)
            full = await speaker.say_stream(
                s, stream, priority=Priority.NORMAL.value, turn_id=turn.turn_id, source="smalltalk",
            )
            if full:
                await self._restore_idle_shark(s)
                return
        # 兜底
        s.record_first_response(turn)
        await speaker.say(
            s,
            "我是巨鲨数字助教鲨鲨，可以帮您安排一场胸部 CT 基础考试。您可以说「安排一场胸部 CT 基础考试」。",
            priority=Priority.NORMAL.value, turn_id=turn.turn_id, source="smalltalk",
        )
        await self._restore_idle_shark(s)

    async def _route_agentic_smalltalk(self, s: "Session", turn: Turn, text: str) -> bool:
        """把复杂/开放问题交给 Claude Code 自主编排（选工具→调真实工具箱→口语化总结）。

        立即安抚保持语音沟通 → CC 自主执行（带心跳安抚）→ 完成后主动汇报。
        CC 失败/超时/空结果返回 False，由调用方回退 DeepSeek flash 聊天，三层兜底永不翻车。
        """
        s.record_first_response(turn)
        logger.info("route=smalltalk delegate=claude_agentic text=%r", text[:40])
        await presenter.set_shark(s, SharkState.WORKING, "正在分析…")
        # 立即安抚：复杂任务通常较慢，先接住用户、保持沟通，不让其干等。
        await speaker.say(
            s, "这个问题我需要查一下平台数据再回答您，稍等。",
            priority=Priority.NORMAL.value, turn_id=turn.turn_id,
            source="reassure", shark_state=SharkState.WORKING,
        )
        answer = await self._await_with_reassurance(s, turn, self._safe_agentic_query(text))
        if not answer:
            logger.info("claude agentic empty/failed; fallback to flash smalltalk")
            return False
        await speaker.say(
            s, answer, priority=Priority.HIGH.value, turn_id=turn.turn_id,
            source="agentic_qa", shark_state=SharkState.SPEAKING,
        )
        await self._restore_idle_shark(s)
        return True

    async def _safe_agentic_query(self, text: str) -> str | None:
        """调用 Claude Code 自主工具通道（永不抛）：失败/超时/空结果返回 None。"""
        try:
            result = await asyncio.wait_for(
                claude_client.run_agentic_query(text),
                timeout=settings.CLAUDE_AGENTIC_TIMEOUT + 8,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("claude agentic query failed: %s", exc)
            return None
        txt = (result or {}).get("assistant_text") if isinstance(result, dict) else None
        return txt.strip() if isinstance(txt, str) and txt.strip() else None

    def _looks_agentic(self, text: str) -> bool:
        """是否「复杂/疑似业务」问题：值得交给 CC 自主编排（纯寒暄/语气词不劳 CC）。"""
        t = (text or "").strip()
        if len(t) < 4:
            return False
        return bool(_AGENTIC_HINT_RE.search(t))

    # ------------------------------------------------------------------ #
    # 供 REST / 控制台直接调用
    # ------------------------------------------------------------------ #
    async def confirm(self, s: "Session", confirmation_type: str) -> None:
        ctype = confirmation_type or "confirm_plan"
        turn = Turn(turn_id=next_turn_id(), session_id=s.session_id, text=f"[confirm:{ctype}]", source="control")
        s.add_turn(turn)
        if ctype == "confirm_publish":
            await self._route_publish(s, turn)
        else:
            await self._route_confirm(s, turn)

    async def publish(self, s: "Session") -> None:
        turn = Turn(turn_id=next_turn_id(), session_id=s.session_id, text="[publish]", source="control")
        s.add_turn(turn)
        await self._route_publish(s, turn)

    async def start_arrange(self, s: "Session", message: str) -> None:
        await self.handle_turn(s, message, source="control")

    async def simulate_submit(self, s: "Session") -> bool:
        if s.state not in (DemoState.EXAM_PUBLISHED.value, DemoState.MONITORING_PROGRESS.value):
            return False
        jobs = [j for j in s.active_jobs() if j.type == "arrange_exam"]
        job = jobs[0] if jobs else workflow_engine.create_job(s, "arrange_exam")
        spawn(workflow_engine.simulate_submit(s, job))
        return True

    async def control_step(self, s: "Session", target_state: str) -> None:
        """导演台保命：强制把演示推进到目标状态（自动越过确认点）。"""
        target = (target_state or "").upper()
        # 取消现有 job，避免并发冲突
        for job in list(s.active_jobs()):
            job.cancel_requested = True
            sig = workflow_engine.signals(job.job_id)
            if sig:
                sig.cancel.set()
        await asyncio.sleep(0.05)

        post_publish = {
            DemoState.EXAM_PUBLISHED.value,
            DemoState.PUBLISHING_EXAM.value,
            DemoState.MONITORING_PROGRESS.value,
            DemoState.GRADING.value,
            DemoState.REPORT_READY.value,
            DemoState.RECOMMENDING.value,
            DemoState.DONE.value,
        }
        pre_publish = {
            DemoState.EXAM_PREVIEW_READY.value,
            DemoState.CREATING_EXAM.value,
        }
        if target in post_publish:
            auto = 2
        elif target in pre_publish:
            auto = 1
        else:
            auto = 0  # 停在方案确认点

        job = workflow_engine.create_job(s, "arrange_exam")
        await presenter.emit_job(s, job)
        spawn(workflow_engine.run_arrange_exam(s, job))
        if auto:
            spawn(self._auto_confirm(s, job, auto))

    async def _auto_confirm(self, s: "Session", job, times: int) -> None:
        """等待 job 到达确认点后自动确认，连续 times 次（用于导演台跳步）。"""
        for _ in range(times):
            for _ in range(200):  # 最多等约 20s
                if job.status == JobStatus.WAITING_USER.value:
                    break
                if not job.is_active:
                    return
                await asyncio.sleep(0.1)
            sig = workflow_engine.signals(job.job_id)
            if sig is None:
                return
            sig.confirm.set()
            await asyncio.sleep(0.2)
            for _ in range(50):
                if job.status != JobStatus.WAITING_USER.value:
                    break
                await asyncio.sleep(0.1)

    async def reset(self, s: "Session") -> None:
        s.reset()
        await presenter.emit_reset(s)
        await presenter.push_snapshot(s)

    async def set_mode(self, s: "Session", mode: str) -> None:
        s.mode = mode
        # 真实/Mock 切换同步到工具箱单例，让 Real 模式的业务查询真正直连平台。
        platform_bridge.set_mode(mode)
        await presenter.emit_state(s)

    # ------------------------------------------------------------------ #
    # 路由判定（确定性，低延迟）
    # ------------------------------------------------------------------ #
    async def _route_intent(self, s: "Session", text: str) -> TurnRoute:
        if re.search(r"重置|重来|重新开始|再来一次", text):
            return TurnRoute.RESET
        if re.search(r"停一?下|取消|暂停|停止|先别|不用了|别说了", text):
            return TurnRoute.CANCEL
        # 业务查询：命中关键词直连真实工具箱取数（修复「Real 模式问答仍走模板」）。
        # 金线（安排考试）进行中时，本场相关问题让位 facts，回答「这一场」而非平台全局。
        biz_intent = business.detect_intent(text)
        if biz_intent is not None and not (
            biz_intent in business.FACTS_BACKED_INTENTS and s.active_jobs()
        ):
            s.conversation["pending_business_intent"] = biz_intent
            return TurnRoute.BUSINESS_QUERY
        if facts_resolver.looks_like_context_question(text):
            return TurnRoute.CONTEXT_QUESTION
        if self._looks_like_modify(s, text):
            return TurnRoute.MODIFY

        if s.need_user_confirmation:
            route = self._local_confirmation_route(s, text)
            if route is not None:
                return route

        if any(k in text for k in ARRANGE_KEYWORDS):
            return TurnRoute.START_JOB

        # 正则未命中明确意图 → LLM 语义意图识别兜底（让自然问法也能指向真实工具）。
        # 失败/超时返回 None，回退 smalltalk，保证零回归、不阻塞语音关键路径。
        llm_route = await self._llm_intent_route(s, text)
        if llm_route is not None:
            return llm_route
        return TurnRoute.SMALLTALK

    async def _llm_intent_route(self, s: "Session", text: str) -> TurnRoute | None:
        """正则兜底之外的 LLM 语义意图识别（限时；失败/超时返回 None 回退 smalltalk）。"""
        if not settings.voice_intent_llm_enabled:
            return None
        intent = await agent_brain.classify_voice_intent(
            message=text, state=s.state, budget=settings.VOICE_INTENT_LLM_BUDGET,
            need_confirm=s.need_user_confirmation, confirmation_type=s.confirmation_type,
            default_plan=mock_data.exam_plan_default(),
        )
        if not intent:
            return None
        s.conversation["last_intent_source"] = "llm"
        if intent in business.QUERY_INTENTS:
            # 金线进行中且为本场相关意图：让位 facts 上下文问答，回答「这一场」。
            if intent in business.FACTS_BACKED_INTENTS and s.active_jobs():
                return None
            s.conversation["pending_business_intent"] = intent
            return TurnRoute.BUSINESS_QUERY
        if intent == "arrange_exam":
            return TurnRoute.START_JOB
        if intent in ("confirm", "publish") and s.need_user_confirmation:
            if intent == "publish" or s.confirmation_type == "confirm_publish":
                return TurnRoute.PUBLISH
            return TurnRoute.CONFIRM
        if intent == "reset":
            return TurnRoute.RESET
        return None

    def _local_confirmation_route(self, s: "Session", text: str) -> TurnRoute | None:
        normalized = self._normalize_intent_text(text)
        if not normalized:
            return None
        if re.search("|".join(_NEGATIVE_CONFIRM_PATTERNS), normalized):
            return TurnRoute.SMALLTALK

        generic_confirm = re.search("|".join(_CONFIRM_POSITIVE_PATTERNS), normalized)
        publish_confirm = re.search("|".join(_PUBLISH_POSITIVE_PATTERNS), normalized)
        if not (generic_confirm or publish_confirm):
            generic_confirm = self._looks_like_short_confirmation(normalized)
        if not (generic_confirm or publish_confirm):
            return None

        if s.confirmation_type == "confirm_publish":
            return TurnRoute.PUBLISH
        if s.confirmation_type == "confirm_plan":
            return TurnRoute.CONFIRM
        return None

    @staticmethod
    def _normalize_intent_text(text: str) -> str:
        text = (text or "").strip().lower()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[，。！？、,.!?；;：:\"'“”‘’（）()【】\[\]]+", "", text)
        return text

    @staticmethod
    def _looks_like_short_confirmation(normalized: str) -> bool:
        if len(normalized) > 12:
            return False
        return bool(re.search(r"好|行|可以|嗯|确认|确定|同意|继续|开始|下发|发布|走", normalized))

    def _looks_like_modify(self, s: "Session", text: str) -> bool:
        if s.exam_plan is None:
            return False
        if not re.search(r"改成|换成|改为|调成|调整为|变成", text):
            return False
        return bool(re.search(r"\d+\s*(分钟|分|人|名|道|题)", text))

    def _apply_modification(self, s: "Session", text: str) -> bool:
        if not s.exam_plan:
            return False
        changed = False
        m = re.search(r"(\d+)\s*分钟", text)
        if m:
            s.exam_plan["duration_minutes"] = int(m.group(1))
            changed = True
        m = re.search(r"(\d+)\s*(人|名)", text)
        if m:
            s.exam_plan["student_count"] = int(m.group(1))
            changed = True
        if changed:
            s.bump_fact("exam_plan")
        return changed

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _waiting_job(self, s: "Session", ctype: str):
        for job in s.active_jobs():
            if job.status == JobStatus.WAITING_USER.value and job.waiting_confirmation_type == ctype:
                return job
        return None

    def _is_echo(self, s: "Session", text: str) -> bool:
        last = s.conversation.get("last_assistant_utterance") or ""
        if not last or len(text) < 4:
            return False
        if text in last:
            return True
        ratio = difflib.SequenceMatcher(None, text, last).ratio()
        return ratio > 0.6 and s.interaction.get("speaking", False)

    async def _restore_idle_shark(self, s: "Session") -> None:
        if s.need_user_confirmation:
            await presenter.set_shark(s, SharkState.WAITING_CONFIRM)
        elif s.active_jobs():
            await presenter.set_shark(s, SharkState.WORKING)
        else:
            await presenter.set_shark(s, SharkState.IDLE)


gateway = ConversationGateway()
