"""交互运行时的核心数据模型：Turn / Job / NarrationItem 与各类枚举。

对应方案第 5 章「核心数据模型」。所有对象都用 dataclass 表达，
通过 to_dict() 暴露给快照 / 控制台调试 / 事件 envelope。
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ------------------------------------------------------------------ #
# 全局自增 id 生成器（进程内单调递增，便于 trace）
# ------------------------------------------------------------------ #
_turn_counter = itertools.count(1)
_job_counter = itertools.count(1)
_nar_counter = itertools.count(1)
_utt_counter = itertools.count(1)
_evt_counter = itertools.count(1)


def next_turn_id() -> str:
    return f"turn_{next(_turn_counter):04d}"


def next_job_id() -> str:
    return f"job_{next(_job_counter):04d}"


def next_narration_id() -> str:
    return f"nar_{next(_nar_counter):04d}"


def next_utterance_id() -> str:
    return f"utt_{next(_utt_counter):04d}"


def next_event_id() -> str:
    return f"evt_{next(_evt_counter):06d}"


# ------------------------------------------------------------------ #
# 枚举
# ------------------------------------------------------------------ #
class Priority(str, Enum):
    """统一优先级：urgent 可打断当前播报，low 仅装饰。"""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


PRIORITY_RANK = {
    Priority.LOW.value: 0,
    Priority.NORMAL.value: 1,
    Priority.HIGH.value: 2,
    Priority.URGENT.value: 3,
}


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TurnRoute(str, Enum):
    IMMEDIATE_ACK = "immediate_ack"
    CONTEXT_QUESTION = "context_question"
    START_JOB = "start_job"
    CONFIRM = "confirm"
    PUBLISH = "publish"
    CANCEL = "cancel"
    MODIFY = "modify"
    SMALLTALK = "smalltalk"
    RESET = "reset"


class NarrationKind(str, Enum):
    PROGRESS = "progress"
    RESULT = "result"
    WARNING = "warning"
    ERROR = "error"
    CONFIRMATION = "confirmation"
    ANSWER_FOLLOWUP = "answer_followup"


# ------------------------------------------------------------------ #
# Turn
# ------------------------------------------------------------------ #
@dataclass
class Turn:
    turn_id: str
    session_id: str
    text: str
    source: str = "voice"  # voice | text | control
    received_at: float = field(default_factory=time.time)
    routed_as: str | None = None
    related_job_id: str | None = None
    interrupts_utterance_id: str | None = None
    interrupt_policy: str | None = None  # stop_low_priority | stop_all | listen_only | none
    barge_in: bool = False
    first_response_at: float | None = None

    def mark_first_response(self) -> float:
        """记录首个前台响应时间，返回首响延迟（毫秒）。"""
        if self.first_response_at is None:
            self.first_response_at = time.time()
        return (self.first_response_at - self.received_at) * 1000.0

    @property
    def first_response_latency_ms(self) -> float | None:
        if self.first_response_at is None:
            return None
        return (self.first_response_at - self.received_at) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "source": self.source,
            "text": self.text,
            "received_at": self.received_at,
            "routed_as": self.routed_as,
            "related_job_id": self.related_job_id,
            "interrupts_utterance_id": self.interrupts_utterance_id,
            "interrupt_policy": self.interrupt_policy,
            "barge_in": self.barge_in,
            "first_response_at": self.first_response_at,
            "first_response_latency_ms": self.first_response_latency_ms,
        }


# ------------------------------------------------------------------ #
# Job
# ------------------------------------------------------------------ #
@dataclass
class Job:
    job_id: str
    session_id: str
    type: str  # arrange_exam | ...
    status: str = JobStatus.QUEUED.value
    current_step: str | None = None
    progress_percent: int = 0
    progress_label: str = ""
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    deadline_at: float = 0.0
    last_user_visible_event_at: float = field(default_factory=time.time)
    cancel_requested: bool = False
    pause_requested: bool = False
    replan_requested: bool = False
    waiting_confirmation_type: str | None = None
    error: str | None = None
    related_turn_id: str | None = None

    def touch(self) -> None:
        self.updated_at = time.time()

    def mark_user_visible(self) -> None:
        self.last_user_visible_event_at = time.time()
        self.touch()

    def set_progress(self, percent: int, label: str) -> None:
        self.progress_percent = max(0, min(100, int(percent)))
        self.progress_label = label
        self.touch()

    @property
    def is_active(self) -> bool:
        return self.status in (
            JobStatus.QUEUED.value,
            JobStatus.RUNNING.value,
            JobStatus.WAITING_USER.value,
            JobStatus.PAUSED.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "type": self.type,
            "status": self.status,
            "current_step": self.current_step,
            "progress": {"percent": self.progress_percent, "label": self.progress_label},
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "deadline_at": self.deadline_at,
            "last_user_visible_event_at": self.last_user_visible_event_at,
            "cancel_requested": self.cancel_requested,
            "pause_requested": self.pause_requested,
            "waiting_confirmation_type": self.waiting_confirmation_type,
            "error": self.error,
            "related_turn_id": self.related_turn_id,
        }


# ------------------------------------------------------------------ #
# Pending Narration Item
# ------------------------------------------------------------------ #
@dataclass
class NarrationItem:
    item_id: str
    session_id: str
    kind: str
    priority: str
    summary_key: str
    fact_path: str | None = None
    fact_version: int = 0
    job_id: str | None = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    requires_verbatim: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "session_id": self.session_id,
            "kind": self.kind,
            "priority": self.priority,
            "summary_key": self.summary_key,
            "fact_path": self.fact_path,
            "fact_version": self.fact_version,
            "job_id": self.job_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "requires_verbatim": self.requires_verbatim,
            "payload": self.payload,
        }
