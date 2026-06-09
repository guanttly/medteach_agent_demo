"""前台交互通道 REST 路由：统一用户输入 + 打断。

对应方案第 7、11 章。所有用户语音/文本输入都经 /api/conversation/turn 进入
Conversation Gateway，立即返回 turn_id（不等待业务执行）；真正的回应通过
WebSocket 的 utterance.* / interaction.* / narration.* 事件流式下发。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..interaction.gateway import gateway
from ..models.schemas import InterruptRequest, TurnRequest, TurnResponse
from ..session_store import session_store
from ..tasks import spawn

router = APIRouter(prefix="/api/conversation", tags=["conversation"])


@router.post("/turn", response_model=TurnResponse)
async def post_turn(req: TurnRequest) -> TurnResponse:
    s = session_store.get(req.session_id)
    # 立即创建 turn 并返回；路由/回应在后台协程里推进，前台永不阻塞。
    from ..interaction.models import next_turn_id

    turn_id = next_turn_id()

    async def _run() -> None:
        await gateway.handle_turn(
            s,
            req.text,
            source=req.source,
            barge_in=req.barge_in,
            interrupts_utterance_id=req.interrupts_utterance_id,
            interrupt_policy=req.interrupt_policy,
            preassigned_turn_id=turn_id,
        )

    spawn(_run())
    return TurnResponse(ok=True, turn_id=turn_id, accepted=True, state=s.state)


@router.post("/interrupt", response_model=TurnResponse)
async def post_interrupt(req: InterruptRequest) -> TurnResponse:
    s = session_store.get(req.session_id)
    await gateway.handle_interrupt(
        s,
        policy=req.policy,
        reason=req.reason,
        utterance_id=req.utterance_id,
        job_policy=req.job_policy,
    )
    return TurnResponse(ok=True, turn_id="-", accepted=True, state=s.state)
