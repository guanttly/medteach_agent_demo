"""演示会话状态（内存版，MVP 足够）。

在原有「演示状态机」字段之外，新增交互/工作流解耦运行时所需的结构：
- facts：单一事实源（由业务字段计算 + 版本号），供上下文问答与播报聚合使用。
- conversation：对话历史、最近意图、最近一次交互时间。
- jobs：后台工作流 job 表。
- interaction：前台交互状态（generation / speaking / 当前 utterance / 确认状态）。
- pending_narration：后台积压、等待聚合播报的条目。
- metrics：观测指标（首响延迟等）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .config import settings
from .constants import DemoState, SharkState, initial_workflow
from .interaction.models import Job, NarrationItem, Turn


def _new_interaction() -> dict[str, Any]:
    return {
        "generation": 0,
        "foreground_state": "idle",  # idle | listening | acking | answering | speaking
        "speaking": False,
        "current_utterance_id": None,
        "current_utterance_priority": None,
        "interrupt_generation": 0,
        "last_interrupt_at": 0.0,
        "barge_in_enabled": True,
        "need_user_confirmation": False,
        "confirmation_type": None,
        # 前台用户活跃截止时间：用户刚说话/打断后的窗口内，后台过程类播报主动让路。
        "user_active_until": 0.0,
    }


def _new_conversation() -> dict[str, Any]:
    return {
        "turns": [],  # 最近若干轮的精简记录（dict）
        "last_user_intent": None,
        "last_user_text": "",
        "last_answer_topic": None,
        "last_assistant_utterance": "",
        "last_interaction_at": 0.0,
    }


def _new_metrics() -> dict[str, Any]:
    return {
        "turn_first_response_latency_ms": [],
        "stale_event_dropped_count": 0,
        "echo_rejected_count": 0,
        "narration_coalesced_count": 0,
        "narration_dropped_stale_count": 0,
        "verbatim_item_preserved_count": 0,
    }


@dataclass
class Session:
    session_id: str
    state: str = DemoState.IDLE.value
    mode: str = field(default_factory=lambda: settings.DEMO_MODE)
    shark_state: str = SharkState.IDLE.value
    assistant_text: str = "你好，我是巨鲨数字助教鲨鲨。请对我说「安排一场胸部 CT 基础考试」。"
    user_text: str = ""
    workflow: list[dict] = field(default_factory=initial_workflow)
    exam_plan: dict | None = None
    students: dict | None = None
    exam_preview: dict | None = None
    progress: dict | None = None
    result: dict | None = None
    recommendation: dict | None = None
    publish_info: dict | None = None
    need_user_confirmation: bool = False
    confirmation_type: str | None = None
    core_status: str = field(
        default_factory=lambda: "ready" if settings.llm_configured else "fallback"
    )  # idle | ready | live | timeout | fallback | error
    fallback_active: bool = field(default_factory=lambda: not settings.llm_configured)
    agent_source: str = field(
        default_factory=lambda: "llm" if settings.llm_configured else "local"
    )  # llm | local
    agent_provider: str = field(default_factory=lambda: settings.llm_provider_label)
    busy: bool = False
    speech_seq: int = 0
    updated_at: float = field(default_factory=time.time)

    # ---- 交互/工作流解耦运行时 ----
    fact_versions: dict[str, int] = field(default_factory=dict)
    conversation: dict[str, Any] = field(default_factory=_new_conversation)
    jobs: dict[str, Job] = field(default_factory=dict)
    turns: dict[str, Turn] = field(default_factory=dict)
    interaction: dict[str, Any] = field(default_factory=_new_interaction)
    pending_narration: list[NarrationItem] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=_new_metrics)

    # ------------------------------------------------------------------ #
    # facts：单一事实源（由业务字段计算）
    # ------------------------------------------------------------------ #
    @property
    def facts(self) -> dict[str, Any]:
        return {
            "exam_plan": self.exam_plan,
            "participants": self.students,
            "exam_draft": (
                {"exam_id": "exam_demo_001", "created": True}
                if self._fact_present("exam_draft")
                else None
            ),
            "exam_preview": self.exam_preview,
            "publish_info": self.publish_info,
            "progress": self.progress,
            "result": self.result,
            "recommendation": self.recommendation,
        }

    def _fact_present(self, path: str) -> bool:
        return self.fact_versions.get(path, 0) > 0

    def bump_fact(self, path: str) -> int:
        v = self.fact_versions.get(path, 0) + 1
        self.fact_versions[path] = v
        self.updated_at = time.time()
        return v

    def fact_version(self, path: str) -> int:
        return self.fact_versions.get(path, 0)

    # ------------------------------------------------------------------ #
    # 交互状态便捷读写
    # ------------------------------------------------------------------ #
    @property
    def generation(self) -> int:
        return self.interaction["generation"]

    def bump_generation(self) -> int:
        self.interaction["generation"] += 1
        self.interaction["interrupt_generation"] += 1
        self.interaction["last_interrupt_at"] = time.time()
        return self.interaction["generation"]

    def set_confirmation(self, need: bool, ctype: str | None) -> None:
        self.need_user_confirmation = need
        self.confirmation_type = ctype
        self.interaction["need_user_confirmation"] = need
        self.interaction["confirmation_type"] = ctype

    def mark_user_active(self, seconds: float | None = None) -> None:
        """标记前台用户正在交互（刚说话/打断）。

        在窗口内，后台「过程类」主动播报（进度 / 安抚）会主动让路，
        把语音通道留给用户，保证语音交互始终优先、不被后台流程淹没。
        """
        hold = settings.FOREGROUND_HOLD_SECONDS if seconds is None else seconds
        self.interaction["user_active_until"] = time.time() + max(0.0, hold)

    @property
    def user_active(self) -> bool:
        return time.time() < self.interaction.get("user_active_until", 0.0)

    # ------------------------------------------------------------------ #
    # 对话历史
    # ------------------------------------------------------------------ #
    def add_turn(self, turn: Turn) -> None:
        self.turns[turn.turn_id] = turn
        rec = {"turn_id": turn.turn_id, "role": "user", "text": turn.text, "ts": turn.received_at}
        self.conversation["turns"].append(rec)
        self.conversation["last_user_text"] = turn.text
        self.conversation["last_interaction_at"] = turn.received_at
        if len(self.conversation["turns"]) > 20:
            self.conversation["turns"] = self.conversation["turns"][-20:]

    def record_assistant_utterance(self, text: str) -> None:
        self.conversation["last_assistant_utterance"] = text
        self.conversation["turns"].append(
            {"role": "assistant", "text": text, "ts": time.time()}
        )
        if len(self.conversation["turns"]) > 20:
            self.conversation["turns"] = self.conversation["turns"][-20:]

    def recent_turns(self, n: int = 6) -> list[dict[str, Any]]:
        return self.conversation["turns"][-n:]

    def active_jobs(self) -> list[Job]:
        return [j for j in self.jobs.values() if j.is_active]

    def record_first_response(self, turn: Turn) -> None:
        latency = turn.mark_first_response()
        self.metrics["turn_first_response_latency_ms"].append(round(latency, 1))
        if len(self.metrics["turn_first_response_latency_ms"]) > 50:
            self.metrics["turn_first_response_latency_ms"] = self.metrics[
                "turn_first_response_latency_ms"
            ][-50:]

    # ------------------------------------------------------------------ #
    # 重置 / 快照
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.state = DemoState.IDLE.value
        self.shark_state = SharkState.IDLE.value
        self.assistant_text = "演示已重置。请对我说「安排一场胸部 CT 基础考试」。"
        self.user_text = ""
        self.workflow = initial_workflow()
        self.exam_plan = None
        self.students = None
        self.exam_preview = None
        self.progress = None
        self.result = None
        self.recommendation = None
        self.publish_info = None
        self.need_user_confirmation = False
        self.confirmation_type = None
        self.core_status = "ready" if settings.llm_configured else "fallback"
        self.fallback_active = not settings.llm_configured
        self.agent_source = "llm" if settings.llm_configured else "local"
        self.agent_provider = settings.llm_provider_label
        self.busy = False
        self.speech_seq = 0
        self.updated_at = time.time()
        # 交互运行时：重置但推进 generation，使旧流式回包失效
        prev_gen = self.interaction.get("generation", 0)
        self.fact_versions = {}
        self.conversation = _new_conversation()
        self.jobs = {}
        self.turns = {}
        self.interaction = _new_interaction()
        self.interaction["generation"] = prev_gen + 1
        self.pending_narration = []
        self.metrics = _new_metrics()

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "mode": self.mode,
            "shark_state": self.shark_state,
            "assistant_text": self.assistant_text,
            "user_text": self.user_text,
            "workflow": self.workflow,
            "exam_plan": self.exam_plan,
            "students": self.students,
            "exam_preview": self.exam_preview,
            "progress": self.progress,
            "result": self.result,
            "recommendation": self.recommendation,
            "need_user_confirmation": self.need_user_confirmation,
            "confirmation_type": self.confirmation_type,
            "core_status": self.core_status,
            "fallback_active": self.fallback_active,
            "agent_source": self.agent_source,
            "agent_provider": self.agent_provider,
            "busy": self.busy,
            "speech_seq": self.speech_seq,
            "updated_at": self.updated_at,
            # 交互/工作流解耦运行时
            "generation": self.generation,
            "facts": self.facts,
            "fact_versions": self.fact_versions,
            "interaction": self.interaction,
            "jobs": [j.to_dict() for j in self.jobs.values()],
            "active_jobs": [j.to_dict() for j in self.active_jobs()],
            "conversation": {
                "last_user_intent": self.conversation["last_user_intent"],
                "last_user_text": self.conversation["last_user_text"],
                "last_answer_topic": self.conversation["last_answer_topic"],
                "last_assistant_utterance": self.conversation["last_assistant_utterance"],
                "recent_turns": self.recent_turns(),
            },
        }


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]


session_store = SessionStore()
