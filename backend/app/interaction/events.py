"""统一事件 envelope 与事件总线。

对应方案第 6 章「事件协议」。所有事件都带 envelope：
event_id / session_id / turn_id / job_id / utterance_id / generation / type / priority / created_at / data。

为保证旧前端（大屏 / 控制台）不被破坏，EventBus 同时支持发送：
- 新语义事件：utterance.* / interaction.* / narration.* / workflow.* / domain.* / diagnostic.*
- 旧兼容事件：assistant_stream / core_status_update / workflow_update / *_update 等
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..ws_manager import ws_manager
from .models import Priority, next_event_id

if TYPE_CHECKING:
    from ..session_store import Session

logger = logging.getLogger("interaction.events")


# 事件类型常量（新语义事件）
class Ev:
    UTT_STARTED = "utterance.started"
    UTT_DELTA = "utterance.delta"
    UTT_SENTENCE = "utterance.sentence"
    UTT_COMPLETED = "utterance.completed"
    UTT_PROGRESS = "utterance.progress"
    UTT_CONFIRMATION = "utterance.confirmation_requested"

    WF_STEP_STARTED = "workflow.step_started"
    WF_STEP_COMPLETED = "workflow.step_completed"
    WF_JOB_UPDATED = "workflow.job_updated"

    DOMAIN_UPDATED = "domain.updated"

    INTERACTION_INTERRUPTED = "interaction.interrupted"
    INTERACTION_BARGE_IN = "interaction.barge_in_started"
    INTERACTION_BARGE_IGNORED = "interaction.barge_in_ignored"
    INTERACTION_TURN_ACCEPTED = "interaction.turn_accepted"

    NAR_ITEM_QUEUED = "narration.item_queued"
    NAR_SUMMARY_EMITTED = "narration.summary_emitted"

    DIAG = "diagnostic.event"


class EventBus:
    """按 session 维度广播事件，统一注入 envelope。"""

    async def emit(
        self,
        session: "Session",
        type_: str,
        data: dict[str, Any] | None = None,
        *,
        turn_id: str | None = None,
        job_id: str | None = None,
        utterance_id: str | None = None,
        priority: str = Priority.NORMAL.value,
        generation: int | None = None,
    ) -> dict[str, Any]:
        session.updated_at = time.time()
        envelope = {
            "event_id": next_event_id(),
            "session_id": session.session_id,
            "turn_id": turn_id,
            "job_id": job_id,
            "utterance_id": utterance_id,
            "generation": session.interaction["generation"] if generation is None else generation,
            "type": type_,
            "priority": priority,
            "created_at": time.time(),
            "data": data or {},
        }
        await ws_manager.broadcast(session.session_id, envelope)
        return envelope

    async def emit_legacy(
        self, session: "Session", type_: str, data: dict[str, Any]
    ) -> None:
        """发送旧版事件（保持 envelope 字段，便于前端统一做 generation 校验）。"""
        session.updated_at = time.time()
        envelope = {
            "event_id": next_event_id(),
            "session_id": session.session_id,
            "generation": session.interaction["generation"],
            "type": type_,
            "data": data,
        }
        await ws_manager.broadcast(session.session_id, envelope)


event_bus = EventBus()
