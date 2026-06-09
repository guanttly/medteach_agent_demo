"""演示主流程 REST 路由。"""
from __future__ import annotations

from fastapi import APIRouter

from ..interaction.gateway import gateway
from ..models.schemas import (
    ActionResponse,
    ConfirmRequest,
    MessageRequest,
    ModeRequest,
    PublishRequest,
    ResetRequest,
)
from ..session_store import session_store
from ..tasks import spawn

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/state")
async def get_state(session_id: str = "demo_001") -> dict:
    return session_store.get(session_id).snapshot()


@router.post("/message", response_model=ActionResponse)
async def post_message(req: MessageRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    spawn(gateway.handle_turn(s, req.message, source="text"))
    return ActionResponse(ok=True, state=s.state, message="已接收，智能体处理中。")


@router.post("/confirm", response_model=ActionResponse)
async def post_confirm(req: ConfirmRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    spawn(gateway.confirm(s, req.confirmation_type))
    return ActionResponse(ok=True, state=s.state, message="已确认。")


@router.post("/publish", response_model=ActionResponse)
async def post_publish(req: PublishRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    spawn(gateway.publish(s))
    return ActionResponse(ok=True, state=s.state, message="正在下发考试。")


@router.post("/reset", response_model=ActionResponse)
async def post_reset(req: ResetRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    await gateway.reset(s)
    return ActionResponse(ok=True, state=s.state, message="演示已重置。")


@router.post("/mode", response_model=ActionResponse)
async def post_mode(req: ModeRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    await gateway.set_mode(s, req.mode)
    return ActionResponse(ok=True, state=s.state, message=f"已切换为 {req.mode} 模式。")
