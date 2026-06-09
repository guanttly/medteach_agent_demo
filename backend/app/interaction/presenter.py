"""演示信息呈现层：负责把状态 / 工作流 / 业务事实推送给大屏与控制台。

这些事件保持与旧前端兼容（core_status_update / workflow_update / *_update /
screen_event / shark_state_update / user_message / snapshot / demo_reset），
同时统一带上 envelope 的 generation 字段，便于前端做 stale 校验。

业务事实更新会同时发一条新语义事件 domain.updated（带 fact_path / fact_version）。
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..constants import SharkState
from .events import Ev, event_bus

if TYPE_CHECKING:
    from ..session_store import Session


class Presenter:
    async def emit_state(self, s: "Session") -> None:
        await event_bus.emit_legacy(
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
                "generation": s.generation,
                "interaction": s.interaction,
                "active_jobs": [j.to_dict() for j in s.active_jobs()],
            },
        )

    async def set_shark(self, s: "Session", state: SharkState, text: str | None = None) -> None:
        s.shark_state = state.value
        await event_bus.emit_legacy(
            s, "shark_state_update", {"state": state.value, "text": text}
        )

    async def emit_user_message(self, s: "Session", text: str, turn_id: str | None = None) -> None:
        s.user_text = text
        await event_bus.emit_legacy(s, "user_message", {"text": text, "turn_id": turn_id})

    async def set_step(self, s: "Session", step_id: str, status: str) -> None:
        for step in s.workflow:
            if step["id"] == step_id:
                step["status"] = status
                break
        evt_type = Ev.WF_STEP_COMPLETED if status == "completed" else Ev.WF_STEP_STARTED
        await event_bus.emit(
            s, evt_type, {"workflow": s.workflow, "step_id": step_id, "status": status}
        )
        # 旧前端工作流面板
        await event_bus.emit_legacy(
            s, "workflow_update", {"workflow": s.workflow, "step_id": step_id, "status": status}
        )

    async def emit_domain(
        self,
        s: "Session",
        *,
        fact_path: str,
        legacy_type: str,
        legacy_data: dict[str, Any],
    ) -> int:
        """更新某项业务事实：bump 版本号，发 domain.updated + 旧版 *_update。"""
        version = s.bump_fact(fact_path)
        await event_bus.emit(
            s,
            Ev.DOMAIN_UPDATED,
            {"fact_path": fact_path, "fact_version": version, "value": legacy_data},
        )
        await event_bus.emit_legacy(s, legacy_type, legacy_data)
        return version

    async def emit_screen_event(self, s: "Session", payload: dict[str, Any]) -> None:
        await event_bus.emit_legacy(s, "screen_event", payload)

    async def emit_job(self, s: "Session", job: Any) -> None:
        await event_bus.emit(
            s, Ev.WF_JOB_UPDATED, {"job": job.to_dict()}, job_id=job.job_id
        )

    async def push_snapshot(self, s: "Session") -> None:
        s.updated_at = time.time()
        await event_bus.emit_legacy(s, "snapshot", s.snapshot())

    async def emit_reset(self, s: "Session") -> None:
        await event_bus.emit_legacy(s, "demo_reset", {"snapshot": s.snapshot()})


presenter = Presenter()
