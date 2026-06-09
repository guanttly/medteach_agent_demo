"""会话内省路由：job 列表与完整快照（断线重连/调试用）。

对应方案第 11 章的状态查询接口。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..session_store import session_store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/{session_id}/snapshot")
async def get_snapshot(session_id: str) -> dict:
    return session_store.get(session_id).snapshot()


@router.get("/{session_id}/jobs")
async def get_jobs(session_id: str) -> dict:
    s = session_store.get(session_id)
    return {
        "session_id": session_id,
        "jobs": [j.to_dict() for j in s.jobs.values()],
        "active_jobs": [j.job_id for j in s.active_jobs()],
    }


@router.get("/{session_id}/turns")
async def get_turns(session_id: str, limit: int = 20) -> dict:
    s = session_store.get(session_id)
    turns = s.turns[-limit:] if limit > 0 else s.turns
    return {"session_id": session_id, "turns": [t.to_dict() for t in turns]}
