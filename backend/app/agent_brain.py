"""分层智能体大脑。

分层接入：
- 对话层（进入技能前的自然聊天 / 意图识别）：始终用 flash 模型「直连」DeepSeek，
  低延迟、可流式（classify + stream_chat）。
- 执行层（真正执行 Agent 任务 / arrange_exam 技能话术）：LLM_PROVIDER=claude_cli 时
  走 CC + DeepSeek v4-pro（generate_arrange_text）。

任何失败（未配置 / 超时 / 报错 / JSON 解析失败）都返回 None / 空，
由 orchestrator 回退到本地确定性编排（fallback），确保展厅永不翻车。
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("agent_brain")

VALID_INTENTS = {"arrange_exam", "confirm", "publish", "reset", "smalltalk"}

# 不同演示阶段给大模型的上下文提示，帮助它判断「确认 / 下发」等意图。
_STATE_HINT: dict[str, str] = {
    "IDLE": "空闲，等待讲师发起需求。",
    "INTENT_RECOGNIZED": "刚识别到安排考试的需求。",
    "PLAN_PROPOSED": "已给出考试方案，等待讲师确认。",
    "WAITING_PLAN_CONFIRM": "已给出考试方案，正在等待讲师确认是否按此方案准备（用户说同意/可以=confirm）。",
    "CREATING_EXAM": "正在创建考试草稿。",
    "EXAM_PREVIEW_READY": "试卷预览已就绪，等待讲师确认下发。",
    "WAITING_PUBLISH_CONFIRM": "试卷已预览，正在等待讲师确认是否下发考试（用户说下发/发布/可以=publish）。",
    "PUBLISHING_EXAM": "正在下发考试。",
    "EXAM_PUBLISHED": "考试已下发，正在监控答题。",
    "MONITORING_PROGRESS": "正在监控答题进度。",
    "GRADING": "正在自动阅卷。",
    "REPORT_READY": "成绩分析已完成。",
    "RECOMMENDING": "正在推荐复训病例。",
    "DONE": "本轮演示已完成，可以重置或再安排一场。",
}

_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」，一个在医学教学展厅里现场演示的语音数字助教。

你唯一的业务闭环是「安排一场胸部 CT 基础诊断考试」，固定流程为：
识别需求 → 生成考试方案 → 讲师确认 → 创建并预览试卷 → 下发考试 → 监控答题 → 自动阅卷 → 推荐复训病例。

你的任务：判断现场讲师这句话的意图，并用口语化、简洁、专业的中文（2~3 句，可朗读）回应，
始终把现场引导回这条黄金路径。不要展开与考试演示无关的话题，不要输出针对真实病人的临床诊断建议。

你必须只输出一个 JSON 对象（不要使用 Markdown 代码块、不要任何额外解释），字段如下：
{
  "intent": "arrange_exam | confirm | publish | reset | smalltalk",
  "assistant_text": "要朗读给现场观众听的话，口语化、不超过 3 句"
}

intent 取值规则：
- arrange_exam：讲师想安排/创建/出题/组织一场考试或测评（即使没说全参数也算）。
  此时 assistant_text 用一句话概括将要安排的考试（主题、时长、人数、题量、总分），并询问是否按此方案准备。
- confirm：讲师在确认/同意/通过当前方案或试卷（如"可以""确认""没问题""就这样""按这个来""往下走""没意见""开始吧"）。
- publish：讲师明确要求下发/发布考试。
- reset：讲师要求重置/重来/再来一次。
- smalltalk：寒暄、提问、与流程无关或信息不足。
  此时 assistant_text 要先简短回应，再自然地把话题引导回"要不要现在安排一场胸部 CT 基础考试"。

请结合下面给出的"当前演示状态"和"默认考试方案"来判断意图、组织话术。只输出 json。"""

# 对话层：纯意图路由（只输出 intent 的小 JSON，flash 直连、低延迟）。
_INTENT_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」的意图路由器。固定业务闭环是「安排一场胸部 CT 基础诊断考试」：
识别需求 → 生成方案 → 讲师确认 → 创建并预览试卷 → 下发考试 → 监控答题 → 自动阅卷 → 推荐复训病例。

判断现场讲师这句话的意图，只输出一个 JSON 对象（不要 Markdown、不要解释）：
{"intent": "arrange_exam | confirm | publish | reset | smalltalk"}

规则：
- arrange_exam：想安排/创建/出题/组织一场考试或测评（即使参数不全）。
- confirm：在确认/同意/通过当前方案或试卷（可以/确认/没问题/就这样/按这个来/往下走/没意见/开始吧）。
- publish：明确要求下发/发布考试。
- reset：要求重置/重来/再来一次。
- smalltalk：寒暄、提问、与流程无关或信息不足。

只输出 json。"""

# 对话层：自然聊天（流式、纯文本朗读，不要 JSON）。
_CHAT_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」，医学教学展厅里的语音数字助教。
你的业务闭环是「安排一场胸部 CT 基础诊断考试」。

现在处于「进入技能之前的自然对话」：请用口语化、简洁、温暖、专业的中文直接回答现场讲师，
2~3 句即可，能被语音合成自然朗读。先正面回答对方的问题或需求；只有在对方确实没有具体诉求时，
才自然地提一句"也可以让我现在安排一场胸部 CT 基础考试"。不要每句话都生硬地往安排考试上引导。

你是「正在协助老师的助教本人」。用第一人称"我"，称呼老师用"您"。
禁止出现这些工程视角词：后台、系统、workflow、job、任务队列、接口、模型、TTS、generation、事件。
不要展开与考试演示无关的话题，不要输出针对真实病人的临床诊断建议。

直接输出要朗读的话即可，不要使用 JSON、不要使用 Markdown、不要加引号或任何前缀。"""

# 播报聚合层：把后台积压的多条进度/结果，合并成「一段」自然口播（Narration Summarizer）。
_NARRATION_SUMMARY_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」，正在协助现场老师安排考试。
我会给你一份 JSON：包含用户最近问的问题、当前最新事实(latest_facts)、是否需要确认、以及若干条积压的待播报信息(pending_items)。

请把这些信息合并成「一段」自然、口语化的中文口播（1~3 句，适合 TTS 朗读，不超过 80 字）：
- 用第一人称"我"，称呼老师用"您"，像助教自然补充进展，不要逐条复述。
- 结果类信息优先于过程类；过期的过程信息不要再说。
- 如果 latest_facts 里学员名单/草稿/预览已就绪，可以合并成一句"我这边也把…准备好了"。
- 如果 need_confirmation 为真，必须在结尾保留一句明确的确认请求（如"您确认后我就下发考试"）。
- 如果用户刚问过某件事(current_user_focus)，可以用"您刚才问…时，我这边也…"自然衔接。

严禁出现：后台、系统、workflow、job、接口、模型、TTS、队列、事件、generation 这些词。
直接输出要朗读的话即可，不要使用 JSON、不要使用 Markdown、不要加引号或任何前缀。"""

# 对话层兜底用：当执行层（CC）不可用时，用 flash 直接生成方案播报话术（纯文本）。
_ARRANGE_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」，医学教学展厅里的语音数字助教。
讲师希望安排一场胸部 CT 基础诊断考试。请用一句到两句口语化中文概括将要安排的考试
（主题、时长、人数、题量、总分），并询问讲师是否按此方案准备。
说话要像现场对老师确认方案，不要像系统通知。

直接输出要朗读的话即可，不要使用 JSON、不要使用 Markdown、不要加引号或任何前缀。"""

_PROGRESS_RECAP_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」，医学教学展厅里的语音数字助教。
请把后台刚收到的考试进度更新，转成一句自然、有人味的现场口播。

要求：
- 可以用"哦，刚刚我们说话的时候..."这类自然过渡。
- 如果只是部分学员交卷，只说已交卷人数和还需等待的人数；不要编造姓名或分数，提醒分数要等自动阅卷后统一展示。
- 如果已经全部交卷，说明答题已经收齐，下一步查看自动阅卷结果。
- 中文 1~2 句，适合 TTS 朗读，不超过 70 字。

直接输出要朗读的话即可，不要使用 JSON、不要使用 Markdown、不要加引号或任何前缀。"""


class AgentBrain:
    """分层意图路由 + 话术生成（对话层 flash 直连 / 执行层 CC+ds）。"""

    # ------------------------------------------------------------------ #
    # 公共工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _apply_chat_thinking(payload: dict[str, Any]) -> None:
        """对话层默认关闭思考模式：低延迟、可流式、temperature 生效。"""
        if settings.DEEPSEEK_CHAT_THINKING:
            payload["thinking"] = {"type": "enabled"}
        else:
            payload["thinking"] = {"type": "disabled"}
            payload["temperature"] = settings.LLM_TEMPERATURE

    def _context_block(self, state: str, need_confirm: bool, confirmation_type: str | None,
                       default_plan: dict[str, Any] | None) -> str:
        hint = _STATE_HINT.get(state, state)
        lines = [f"当前演示状态：{state}（{hint}）"]
        if need_confirm:
            lines.append(f"正在等待用户确认，确认类型：{confirmation_type}")
        if default_plan:
            q = default_plan.get("question_structure", {})
            lines.append(
                "默认考试方案：{name}，面向{group}共{count}名，时长{dur}分钟，"
                "单选{sc}道/多选{mc}道/病例分析{ca}道，总分{total}分，难度{diff}。".format(
                    name=default_plan.get("exam_name", "胸部 CT 基础诊断测评"),
                    group=default_plan.get("student_group", "现场规培学员"),
                    count=default_plan.get("student_count", 8),
                    dur=default_plan.get("duration_minutes", 15),
                    sc=q.get("single_choice", 10),
                    mc=q.get("multiple_choice", 5),
                    ca=q.get("case_analysis", 2),
                    total=default_plan.get("total_score", 100),
                    diff=default_plan.get("difficulty", "中级"),
                )
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 对话层（flash 直连 DeepSeek）
    # ------------------------------------------------------------------ #
    async def classify(
        self,
        *,
        message: str,
        state: str,
        need_confirm: bool = False,
        confirmation_type: str | None = None,
        default_plan: dict[str, Any] | None = None,
    ) -> str | None:
        """意图路由：flash 直连、非流式、小 JSON。失败返回 None 交给上层兜底。"""
        if not settings.chat_llm_configured:
            return None
        context = self._context_block(state, need_confirm, confirmation_type, default_plan)
        payload = {
            "model": settings.DEEPSEEK_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": f"{_INTENT_SYSTEM_PROMPT}\n\n{context}"},
                {"role": "user", "content": message},
            ],
            "max_tokens": 64,
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                settings.deepseek_chat_url, json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            body = resp.json()
        content = body["choices"][0]["message"].get("content") or ""
        data = self._parse_json(content)
        intent = str(data.get("intent", "")).strip()
        return intent if intent in VALID_INTENTS else "smalltalk"

    async def stream_smalltalk(
        self,
        *,
        message: str,
        state: str,
        need_confirm: bool = False,
        confirmation_type: str | None = None,
        default_plan: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """对话层自然聊天的流式封装：组装 chat 系统提示 + 上下文后逐 token 产出。"""
        context = self._context_block(state, need_confirm, confirmation_type, default_plan)
        system = f"{_CHAT_SYSTEM_PROMPT}\n\n{context}"
        async for piece in self.stream_chat(system, message):
            yield piece

    async def generate_progress_recap_text(
        self,
        *,
        progress: dict[str, Any],
        exam_plan: dict[str, Any] | None = None,
    ) -> str | None:
        """用对话层 flash 把答题进度转成自然口播；失败交给上层兜底。"""
        if not settings.chat_llm_configured:
            return None
        total = int(
            progress.get("published")
            or (exam_plan or {}).get("student_count")
            or progress.get("entered")
            or 0
        )
        submitted = int(progress.get("submitted") or 0)
        answering = int(progress.get("answering") or 0)
        entered = int(progress.get("entered") or 0)
        remaining = max(total - submitted, answering, 0)
        label = str(progress.get("label") or "答题进度更新")
        user_prompt = (
            f"考试进度：{label}。\n"
            f"总人数：{total}，已进入：{entered}，已交卷：{submitted}，"
            f"仍在答题/等待：{remaining}。"
        )
        try:
            text = await self._chat_once(_PROGRESS_RECAP_SYSTEM_PROMPT, user_prompt)
            return text.strip().strip("\"'“”") or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("generate_progress_recap_text failed: %s", exc)
            return None

    async def summarize_narration(self, payload: dict[str, Any]) -> str | None:
        """把后台积压的多条进度/结果合并成一段自然口播；失败交给上层确定性兜底。"""
        if not settings.chat_llm_configured:
            return None
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            text = await self._chat_once(_NARRATION_SUMMARY_SYSTEM_PROMPT, user_prompt)
            return text.strip().strip("\"'“”") or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("summarize_narration failed: %s", exc)
            return None

    async def stream_chat(self, system_prompt: str, user_message: str) -> AsyncIterator[str]:
        """对话层流式：flash 直连，逐 token 产出回复文本（忽略 reasoning_content）。"""
        if not settings.chat_llm_configured:
            return
        payload = {
            "model": settings.DEEPSEEK_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": settings.LLM_CHAT_MAX_TOKENS,
            "stream": True,
        }
        self._apply_chat_thinking(payload)
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", settings.deepseek_chat_url, json=payload, headers=self._headers()
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"DeepSeek 流式失败 HTTP {resp.status_code}: {body[:200]!r}"
                    )
                async for raw_line in resp.aiter_lines():
                    line = raw_line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    piece = (choices[0].get("delta") or {}).get("content")
                    if piece:
                        yield piece

    async def _chat_once(self, system_prompt: str, user_message: str) -> str:
        """对话层非流式：flash 直连，返回纯文本。"""
        payload = {
            "model": settings.DEEPSEEK_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": settings.LLM_CHAT_MAX_TOKENS,
            "stream": False,
        }
        self._apply_chat_thinking(payload)
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                settings.deepseek_chat_url, json=payload, headers=self._headers()
            )
            resp.raise_for_status()
            body = resp.json()
        return (body["choices"][0]["message"].get("content") or "").strip()

    # ------------------------------------------------------------------ #
    # 执行层（CC + ds v4-pro；不可用时回退 flash 直连）
    # ------------------------------------------------------------------ #
    async def generate_arrange_text(
        self,
        *,
        message: str,
        state: str,
        default_plan: dict[str, Any] | None = None,
    ) -> str | None:
        """生成「考试方案」播报话术：执行层任务。

        LLM_PROVIDER=claude_cli 时由 CC + DeepSeek v4-pro 生成；否则 flash 直连兜底。
        """
        if not settings.chat_llm_configured:
            return None
        context = self._context_block(state, True, "confirm_plan", default_plan)
        try:
            if settings.LLM_PROVIDER == "claude_cli":
                from .claude_code_client import claude_client

                data = await claude_client.run_agent_turn(
                    f"{_SYSTEM_PROMPT}\n\n{context}", message
                )
                text = (data or {}).get("assistant_text")
                return text.strip() if isinstance(text, str) and text.strip() else None
            text = await self._chat_once(f"{_ARRANGE_SYSTEM_PROMPT}\n\n{context}", message)
            return text or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("generate_arrange_text failed (%s): %s", settings.LLM_PROVIDER, exc)
            return None

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text[:4].lower() == "json":
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


agent_brain = AgentBrain()
