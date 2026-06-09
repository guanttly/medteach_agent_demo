"""演示编排核心 (Demo Orchestrator)。

负责驱动"安排考试"黄金路径，并通过 WebSocket 以动画节奏把
智能体动作、阶段成果实时推送给大屏与数字形象两个前端。

设计原则（呼应 PRD）：
- 强制优先：每条用户消息先交给真实智能体大脑（CC + DeepSeek）理解意图、组织话术。
- 任何失败（未配置 / 超时 / 报错）都自动回退到本地确定性编排 + Mock 数据，保证展厅永不翻车。
- 本编排器负责把"真实智能"包装成稳定、可控、好演示的黄金路径。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from . import mock_data
from .agent_brain import agent_brain
from .config import settings
from .constants import DemoState, SharkState
from .session_store import Session
from .ws_manager import ws_manager

logger = logging.getLogger("orchestrator")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""


def _load_templates() -> dict[str, str]:
    path = (
        settings.CLAUDE_CORE_DIR
        / ".claude"
        / "skills"
        / "arrange_exam"
        / "response_templates.json"
    )
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


TEMPLATES = _load_templates()

ARRANGE_KEYWORDS = (
    "安排", "考试", "测评", "考核", "出题", "出一套", "考一下", "组织", "ct", "CT", "测试",
)

# 句末切分符：流式回复按句推送，前端据此做句级流式 TTS。
_SENTENCE_END = "。！？!?；;…\n"


class Orchestrator:
    def __init__(self) -> None:
        self._delay = settings.STEP_DELAY
        self._progress_delay = settings.PROGRESS_DELAY

    # ------------------------------------------------------------------ #
    # 基础事件推送
    # ------------------------------------------------------------------ #
    async def _emit(self, s: Session, type_: str, data: dict[str, Any]) -> None:
        import time

        s.updated_at = time.time()
        await ws_manager.broadcast(s.session_id, {"type": type_, "data": data})

    async def _emit_state(self, s: Session) -> None:
        await self._emit(
            s,
            "core_status_update",
            {
                "state": s.state,
                "mode": s.mode,
                "core_status": s.core_status,
                "fallback_active": s.fallback_active,
                "agent_source": s.agent_source,
                "agent_provider": s.agent_provider,
                "need_user_confirmation": s.need_user_confirmation,
                "confirmation_type": s.confirmation_type,
                "busy": s.busy,
            },
        )

    async def _set_shark(self, s: Session, state: SharkState, text: str | None = None) -> None:
        s.shark_state = state.value
        await self._emit(s, "shark_state_update", {"state": state.value, "text": text})

    async def _say(self, s: Session, text: str, tts: bool = True) -> None:
        s.speech_seq += 1
        speech_id = f"{s.session_id}:{s.speech_seq}"
        s.assistant_text = text
        s.shark_state = SharkState.SPEAKING.value
        await self._emit(
            s,
            "assistant_message",
            {
                "speech_id": speech_id,
                "text": text,
                "tts": tts,
                "shark_state": SharkState.SPEAKING.value,
            },
        )

    # ------------------------------------------------------------------ #
    # 流式播报：逐字推送文本，并按句推送供前端做流式 TTS
    # ------------------------------------------------------------------ #
    async def _emit_stream(self, s: Session, speech_id: str, phase: str, **extra: Any) -> None:
        await self._emit(
            s, "assistant_stream", {"speech_id": speech_id, "phase": phase, **extra}
        )

    @staticmethod
    def _find_sentence_cut(buf: str, min_len: int = 4) -> int:
        """返回 buf 中第一个可切句位置（下标），不足 min_len 不切，避免碎句。"""
        for i, ch in enumerate(buf):
            if ch in _SENTENCE_END and i + 1 >= min_len:
                return i
        return -1

    async def _say_stream_iter(
        self, s: Session, pieces: AsyncIterator[str], *, tts: bool = True
    ) -> str:
        """消费一个文本异步流，边推 delta（逐字字幕）边推 sentence（供 TTS）。"""
        s.speech_seq += 1
        speech_id = f"{s.session_id}:{s.speech_seq}"
        s.shark_state = SharkState.SPEAKING.value
        await self._emit_stream(
            s, speech_id, "start", shark_state=SharkState.SPEAKING.value, tts=tts
        )
        full = ""
        buf = ""
        idx = 0
        try:
            async for piece in pieces:
                if not piece:
                    continue
                full += piece
                buf += piece
                s.assistant_text = full
                await self._emit_stream(s, speech_id, "delta", delta=piece, text=full)
                while True:
                    cut = self._find_sentence_cut(buf)
                    if cut == -1:
                        break
                    sentence = buf[: cut + 1].strip()
                    buf = buf[cut + 1 :]
                    if sentence:
                        await self._emit_stream(
                            s, speech_id, "sentence", sentence=sentence, index=idx
                        )
                        idx += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("assistant stream interrupted: %s", exc)
        tail = buf.strip()
        if tail:
            await self._emit_stream(s, speech_id, "sentence", sentence=tail, index=idx)
        if full.strip():
            s.assistant_text = full
        await self._emit_stream(s, speech_id, "end", text=full)
        return full

    async def _say_stream_text(self, s: Session, text: str, *, tts: bool = True) -> str:
        """将一段已知文本以流式方式推送（逐字显现 + 句级 TTS）。"""

        async def _gen() -> AsyncIterator[str]:
            step = 10
            for i in range(0, len(text), step):
                yield text[i : i + step]
                await asyncio.sleep(0.018)

        return await self._say_stream_iter(s, _gen(), tts=tts)

    async def _set_step(self, s: Session, step_id: str, status: str) -> None:
        for step in s.workflow:
            if step["id"] == step_id:
                step["status"] = status
                break
        await self._emit(s, "workflow_update", {"workflow": s.workflow, "step_id": step_id, "status": status})

    async def _sleep(self, seconds: float | None = None) -> None:
        await asyncio.sleep(self._delay if seconds is None else seconds)

    def _tpl(self, key: str, ctx: dict[str, Any]) -> str:
        raw = TEMPLATES.get(key, "")
        return raw.format_map(_SafeDict(ctx))

    async def _progress_recap_text(self, s: Session, progress: dict[str, Any]) -> str:
        try:
            text = await asyncio.wait_for(
                agent_brain.generate_progress_recap_text(
                    progress=progress, exam_plan=s.exam_plan
                ),
                timeout=min(4.0, max(1.0, settings.LLM_TIMEOUT_SECONDS)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("progress recap fallback: %s", exc)
            text = None
        if text and text.strip():
            return text.strip()

        total = int(
            progress.get("published")
            or (s.exam_plan or {}).get("student_count")
            or progress.get("entered")
            or 0
        )
        submitted = int(progress.get("submitted") or 0)
        answering = int(progress.get("answering") or 0)
        remaining = max(total - submitted, answering, 0)
        if submitted > 0 and remaining > 0:
            return (
                f"哦，刚刚我们说话的时候，已经有 {submitted} 名学员交卷了。"
                f"分数要等自动阅卷后统一展示，我们再等等另外 {remaining} 名学员。"
            )
        if submitted > 0:
            return "哦，刚刚这一轮答题已经收齐了。我马上看自动阅卷结果，再把分数和薄弱点告诉您。"
        return "我这边已经开始盯答题进度了。有学员交卷后，我会自然接着告诉您。"

    # ------------------------------------------------------------------ #
    # 快照（新连接同步）
    # ------------------------------------------------------------------ #
    async def push_snapshot(self, s: Session) -> None:
        await self._emit(s, "snapshot", s.snapshot())

    # ------------------------------------------------------------------ #
    # 1) 用户发起：安排考试
    # ------------------------------------------------------------------ #
    async def handle_message(self, s: Session, message: str) -> bool:
        if s.busy:
            return False
        s.user_text = message
        await self._emit(s, "user_message", {"text": message})
        await self._set_shark(s, SharkState.LISTENING, message)
        await self._sleep(0.4)

        # 分层接入：先用「对话层」flash 直连识别意图；失败再走本地正则兜底。
        intent = await self._classify(s, message)
        if intent is None:
            intent = self._fallback_intent(s, message)

        if intent == "reset":
            await self.reset(s)
            return True
        if intent == "confirm":
            if s.state == DemoState.WAITING_PLAN_CONFIRM.value:
                return await self.handle_confirm(s, "confirm_plan")
            if s.state == DemoState.WAITING_PUBLISH_CONFIRM.value:
                return await self.handle_publish(s)
            intent = "smalltalk"
        if intent == "publish":
            if s.state in (
                DemoState.WAITING_PUBLISH_CONFIRM.value,
                DemoState.EXAM_PREVIEW_READY.value,
            ):
                return await self.handle_publish(s)
            intent = "smalltalk"
        if intent == "arrange_exam":
            return await self._run_arrange(s, message)

        await self._smalltalk_stream(s, message)
        return True

    # ------------------------------------------------------------------ #
    # 智能体大脑：意图识别 + 话术（真实接入优先，失败回退本地确定性编排）
    # ------------------------------------------------------------------ #
    async def _classify(self, s: Session, message: str) -> str | None:
        """对话层：flash 直连识别意图；未配置或出错返回 None 走本地正则兑底。"""
        if not settings.chat_llm_configured:
            self._mark_fallback(s)
            await self._emit_state(s)
            return None
        await self._set_shark(s, SharkState.THINKING)
        try:
            intent = await agent_brain.classify(
                message=message,
                state=s.state,
                need_confirm=s.need_user_confirmation,
                confirmation_type=s.confirmation_type,
                default_plan=mock_data.exam_plan_default(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intent classify error, fallback to local: %s", exc)
            intent = None
        if intent is not None:
            self._mark_live(s)
        else:
            self._mark_fallback(s)
        await self._emit_state(s)
        return intent

    def _mark_live(self, s: Session) -> None:
        s.agent_source = "llm"
        s.core_status = "live"
        s.fallback_active = False
        s.agent_provider = settings.llm_provider_label

    def _mark_fallback(self, s: Session) -> None:
        s.agent_source = "local"
        s.core_status = "fallback"
        s.fallback_active = True
        s.agent_provider = settings.llm_provider_label if settings.llm_configured else "本地编排"

    def _fallback_intent(self, s: Session, message: str) -> str:
        if re.search(r"重置|重来|重新开始|再来一次", message):
            return "reset"
        if s.state == DemoState.WAITING_PLAN_CONFIRM.value and re.search(
            r"确认|确定|可以|好的|没问题|同意|通过|开始", message
        ):
            return "confirm"
        if s.state == DemoState.WAITING_PUBLISH_CONFIRM.value and re.search(
            r"下发|发布|确认|可以|开始", message
        ):
            return "publish"
        if self._looks_like_arrange(message):
            return "arrange_exam"
        return "smalltalk"

    def _looks_like_arrange(self, message: str) -> bool:
        return any(k in message for k in ARRANGE_KEYWORDS)

    async def _smalltalk_stream(self, s: Session, message: str) -> None:
        # 对话层：flash 直连「流式」生成回复，并以句为单位推送给前端做流式 TTS。
        if settings.chat_llm_configured:
            await self._set_shark(s, SharkState.THINKING)
            stream = agent_brain.stream_smalltalk(
                message=message,
                state=s.state,
                need_confirm=s.need_user_confirmation,
                confirmation_type=s.confirmation_type,
                default_plan=mock_data.exam_plan_default(),
            )
            full = await self._say_stream_iter(s, stream)
            if full.strip():
                self._mark_live(s)
                await self._set_shark(s, SharkState.IDLE)
                await self._emit_state(s)
                return
            # 流式没产出 -> 兑底
            self._mark_fallback(s)
        text = "我是巨鲨数字助教鲨鲨，可以帮你安排考试。你可以说「安排一场胸部 CT 基础考试」。"
        await self._say_stream_text(s, text)
        await self._set_shark(s, SharkState.IDLE)
        await self._emit_state(s)

    async def _run_arrange(self, s: Session, message: str) -> bool:
        if s.busy:
            return False
        s.busy = True
        try:
            await self._sleep(0.3)

            # 识别教学任务
            s.state = DemoState.INTENT_RECOGNIZED.value
            await self._emit_state(s)
            await self._set_step(s, "intent", "running")
            await self._set_shark(s, SharkState.THINKING)
            await self._sleep()
            await self._set_step(s, "intent", "completed")
            await self._emit(
                s,
                "screen_event",
                {"type": "intent_recognized", "title": "已识别教学任务", "message": "安排一场胸部 CT 基础诊断考试", "status": "completed"},
            )

            # 生成考试方案
            await self._set_step(s, "plan", "running")
            await self._set_shark(s, SharkState.WORKING)
            await self._sleep()
            plan = mock_data.exam_plan_default()
            s.exam_plan = plan
            await self._emit(s, "exam_plan_update", {"exam_plan": plan})
            await self._set_step(s, "plan", "completed")

            # 等待确认
            await self._set_step(s, "confirm_plan", "running")
            s.state = DemoState.WAITING_PLAN_CONFIRM.value
            s.need_user_confirmation = True
            s.confirmation_type = "confirm_plan"
            await self._emit_state(s)

            ctx = {**plan, **plan.get("question_structure", {})}
            # 执行层：CC + ds（或 flash 兑底）生成方案播报话术，再以流式方式播报。
            text = await agent_brain.generate_arrange_text(
                message=message, state=s.state, default_plan=plan
            )
            if not (text and text.strip()):
                text = self._tpl("plan_proposed", ctx) or "我已生成考试方案，请确认。"
            await self._say_stream_text(s, text.strip())
            await self._set_shark(s, SharkState.WAITING_CONFIRM)
            await self._emit(
                s,
                "screen_event",
                {"type": "plan_proposed", "title": "已生成考试方案", "message": s.assistant_text, "status": "completed"},
            )
            return True
        finally:
            s.busy = False
            await self._emit_state(s)

    # ------------------------------------------------------------------ #
    # 2) 确认方案 -> 查询学员 / 创建考试 / 试卷预览
    # ------------------------------------------------------------------ #
    async def handle_confirm(self, s: Session, confirmation_type: str) -> bool:
        if confirmation_type == "confirm_publish":
            return await self.handle_publish(s)
        if s.busy:
            return False
        if s.state != DemoState.WAITING_PLAN_CONFIRM.value:
            return False
        s.busy = True
        try:
            s.need_user_confirmation = False
            s.confirmation_type = None
            await self._set_step(s, "confirm_plan", "completed")
            await self._say(s, self._tpl("plan_confirmed", {}) or "已确认，我现在开始创建考试。")
            await self._sleep()

            s.state = DemoState.CREATING_EXAM.value
            await self._emit_state(s)

            # 查询学员
            await self._set_step(s, "students", "running")
            await self._set_shark(s, SharkState.WORKING, "正在查询现场学员……")
            await self._sleep()
            students = mock_data.students()
            s.students = students
            await self._emit(s, "students_update", {"students": students})
            await self._set_step(s, "students", "completed")

            # 创建考试草稿
            await self._set_step(s, "create", "running")
            await self._set_shark(s, SharkState.WORKING, "正在匹配胸部 CT 题库并创建考试草稿……")
            await self._sleep()
            await self._set_step(s, "create", "completed")
            await self._emit(
                s,
                "screen_event",
                {"type": "tool_call_succeeded", "title": "考试草稿已创建", "message": "exam_demo_001", "status": "completed"},
            )

            # 试卷预览
            await self._set_step(s, "preview", "running")
            await self._sleep()
            preview = mock_data.exam_preview()
            s.exam_preview = preview
            await self._emit(s, "exam_preview_update", {"exam_preview": preview})
            await self._set_step(s, "preview", "completed")

            s.state = DemoState.WAITING_PUBLISH_CONFIRM.value
            s.need_user_confirmation = True
            s.confirmation_type = "confirm_publish"
            await self._emit_state(s)

            q_total = (s.exam_plan or {}).get("question_total", 17)
            text = self._tpl("preview_ready", {"question_total": q_total}) or "试卷已生成，确认后我就可以下发考试。"
            await self._say(s, text)
            await self._set_shark(s, SharkState.WAITING_CONFIRM)
            await self._emit(
                s,
                "screen_event",
                {"type": "exam_preview_ready", "title": "试卷预览已就绪", "message": text, "status": "completed"},
            )
            return True
        finally:
            s.busy = False
            await self._emit_state(s)

    # ------------------------------------------------------------------ #
    # 3) 下发考试 -> 进度 -> 阅卷 -> 报告 -> 推荐
    # ------------------------------------------------------------------ #
    async def handle_publish(self, s: Session) -> bool:
        if s.busy:
            return False
        if s.state not in (DemoState.WAITING_PUBLISH_CONFIRM.value, DemoState.EXAM_PREVIEW_READY.value):
            return False
        s.busy = True
        try:
            s.need_user_confirmation = False
            s.confirmation_type = None
            s.state = DemoState.PUBLISHING_EXAM.value
            await self._emit_state(s)

            await self._set_step(s, "publish", "running")
            await self._set_shark(s, SharkState.WORKING, "正在下发考试……")
            await self._sleep()
            await self._set_step(s, "publish", "completed")
            s.state = DemoState.EXAM_PUBLISHED.value
            await self._emit(
                s,
                "screen_event",
                {
                    "type": "exam_published",
                    "title": "考试已下发",
                    "message": "已开启答题入口，二维码已生成。",
                    "status": "completed",
                    "payload": {"entry_url": "https://demo.giant-shark.local/exam/exam_demo_001"},
                },
            )
            count = (s.exam_plan or {}).get("student_count", 8)
            await self._say(s, self._tpl("exam_published", {"student_count": count}) or "考试已下发。")
            await self._emit_state(s)

            await self._run_progress(s)
            await self._run_grading(s)
            await self._run_recommend(s)
            return True
        finally:
            s.busy = False
            await self._emit_state(s)

    async def _run_progress(self, s: Session) -> None:
        s.state = DemoState.MONITORING_PROGRESS.value
        await self._emit_state(s)
        await self._set_step(s, "progress", "running")
        await self._set_shark(s, SharkState.WORKING, "正在监控答题进度……")
        announced_partial_submit = False
        for snap in mock_data.exam_progress_steps():
            s.progress = snap
            await self._emit(s, "exam_progress_update", {"progress": snap})
            if (
                not announced_partial_submit
                and int(snap.get("submitted") or 0) > 0
                and int(snap.get("answering") or 0) > 0
            ):
                announced_partial_submit = True
                await self._say_stream_text(s, await self._progress_recap_text(s, snap))
            await self._sleep(self._progress_delay)
        await self._set_step(s, "progress", "completed")

    async def _run_grading(self, s: Session) -> None:
        s.state = DemoState.GRADING.value
        await self._emit_state(s)
        await self._set_step(s, "grading", "running")
        await self._set_shark(s, SharkState.THINKING, "正在自动阅卷与智能点评……")
        await self._say(s, self._tpl("all_submitted", {}) or "全部学员已提交，正在自动阅卷。")
        await self._sleep(self._progress_delay)
        result = mock_data.exam_result()
        s.result = result
        await self._emit(s, "exam_result_update", {"result": result})
        await self._set_step(s, "grading", "completed")
        s.state = DemoState.REPORT_READY.value
        await self._emit_state(s)

        summary = result["summary"]
        weak = result["weak_points"]
        top_student = max(result.get("students", []), key=lambda item: item.get("score", 0), default={})
        ctx = {
            "average": summary["average"],
            "pass_rate": summary["pass_rate"],
            "highest": summary.get("highest", ""),
            "lowest": summary.get("lowest", ""),
            "top_student": top_student.get("name", ""),
            "top_score": top_student.get("score", ""),
            "weak_point_1": weak[0]["name"] if len(weak) > 0 else "",
            "weak_point_2": weak[1]["name"] if len(weak) > 1 else "",
            "weak_point_3": weak[2]["name"] if len(weak) > 2 else "",
        }
        await self._say(s, self._tpl("report_ready", ctx) or "阅卷完成。")
        await self._emit(
            s,
            "screen_event",
            {"type": "report_ready", "title": "阅卷分析已完成", "message": f"平均分 {summary['average']}，及格率 {summary['pass_rate']}%", "status": "completed"},
        )

    async def _run_recommend(self, s: Session) -> None:
        s.state = DemoState.RECOMMENDING.value
        await self._emit_state(s)
        await self._set_step(s, "recommend", "running")
        await self._set_shark(s, SharkState.WORKING, "正在为薄弱点匹配复训病例……")
        await self._sleep()
        rec = mock_data.recommended_cases()
        s.recommendation = rec
        await self._emit(s, "case_recommendation_update", {"recommendation": rec})
        await self._set_step(s, "recommend", "completed")

        s.state = DemoState.DONE.value
        s.core_status = "idle"
        await self._emit_state(s)
        text = self._tpl("recommendation_ready", {"case_count": len(rec.get("cases", []))}) or "已生成复训建议。"
        await self._say(s, text)
        await self._set_shark(s, SharkState.SUCCESS)
        await self._emit(
            s,
            "screen_event",
            {"type": "demo_done", "title": "演示完成", "message": "考试安排闭环已完整演示。", "status": "completed"},
        )

    # ------------------------------------------------------------------ #
    # 导演台：模拟全部提交（跳过进度等待）
    # ------------------------------------------------------------------ #
    async def handle_simulate_submit(self, s: Session) -> bool:
        if s.busy:
            return False
        if s.state not in (
            DemoState.EXAM_PUBLISHED.value,
            DemoState.MONITORING_PROGRESS.value,
        ):
            return False
        s.busy = True
        try:
            steps = mock_data.exam_progress_steps()
            s.progress = steps[-1]
            await self._set_step(s, "progress", "completed")
            await self._emit(s, "exam_progress_update", {"progress": steps[-1]})
            await self._run_grading(s)
            await self._run_recommend(s)
            return True
        finally:
            s.busy = False
            await self._emit_state(s)

    # ------------------------------------------------------------------ #
    # 导演台：强制跳到指定阶段（保命用）
    # ------------------------------------------------------------------ #
    async def handle_control_step(self, s: Session, target_state: str) -> bool:
        target = target_state.upper()
        if target in (DemoState.PLAN_PROPOSED.value, DemoState.WAITING_PLAN_CONFIRM.value):
            s.state = DemoState.IDLE.value
            return await self.handle_message(s, "安排一场胸部 CT 基础考试")
        if target in (DemoState.EXAM_PREVIEW_READY.value, DemoState.WAITING_PUBLISH_CONFIRM.value):
            if s.exam_plan is None:
                s.state = DemoState.IDLE.value
                await self.handle_message(s, "安排一场胸部 CT 基础考试")
            s.state = DemoState.WAITING_PLAN_CONFIRM.value
            return await self.handle_confirm(s, "confirm_plan")
        if target in (DemoState.EXAM_PUBLISHED.value, DemoState.PUBLISHING_EXAM.value):
            s.state = DemoState.WAITING_PUBLISH_CONFIRM.value
            return await self.handle_publish(s)
        if target in (DemoState.REPORT_READY.value, DemoState.GRADING.value):
            if s.busy:
                return False
            s.busy = True
            try:
                await self._run_grading(s)
            finally:
                s.busy = False
                await self._emit_state(s)
            return True
        if target in (DemoState.RECOMMENDING.value, DemoState.DONE.value):
            if s.busy:
                return False
            s.busy = True
            try:
                if s.result is None:
                    await self._run_grading(s)
                await self._run_recommend(s)
            finally:
                s.busy = False
                await self._emit_state(s)
            return True
        return False

    # ------------------------------------------------------------------ #
    # 重置 / 模式切换
    # ------------------------------------------------------------------ #
    async def reset(self, s: Session) -> None:
        s.reset()
        await self._emit(s, "demo_reset", {"snapshot": s.snapshot()})
        await self.push_snapshot(s)

    async def set_mode(self, s: Session, mode: str) -> None:
        s.mode = mode
        await self._emit_state(s)


orchestrator = Orchestrator()
