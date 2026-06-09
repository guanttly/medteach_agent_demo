"""导演控制台 REST 路由（展厅保命工具）。"""
from __future__ import annotations

from fastapi import APIRouter

from ..constants import DemoState
from ..interaction.gateway import gateway
from ..models.schemas import ActionResponse, ControlStepRequest, PresetRequest
from ..session_store import session_store
from ..tasks import spawn

router = APIRouter(prefix="/api/demo/control", tags=["control"])

# 预设演示话术 / 动作
PRESET_MESSAGES = {
    "arrange": "帮我给今天现场的规培学员安排一场胸部 CT 基础考试，时间控制在 15 分钟。",
}


@router.post("/step", response_model=ActionResponse)
async def control_step(req: ControlStepRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    spawn(gateway.control_step(s, req.target_state))
    return ActionResponse(ok=True, state=s.state, message=f"强制推进到 {req.target_state}。")


@router.post("/preset", response_model=ActionResponse)
async def control_preset(req: PresetRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    preset = req.preset
    if preset == "arrange":
        spawn(gateway.start_arrange(s, PRESET_MESSAGES["arrange"]))
    elif preset == "confirm_plan":
        spawn(gateway.confirm(s, "confirm_plan"))
    elif preset == "publish":
        spawn(gateway.publish(s))
    elif preset == "simulate_submit":
        spawn(gateway.simulate_submit(s))
    else:
        return ActionResponse(ok=False, state=s.state, message=f"未知预设：{preset}")
    return ActionResponse(ok=True, state=s.state, message=f"已触发预设：{preset}")


@router.post("/simulate-submit", response_model=ActionResponse)
async def simulate_submit(req: PresetRequest) -> ActionResponse:
    s = session_store.get(req.session_id)
    spawn(gateway.simulate_submit(s))
    return ActionResponse(ok=True, state=s.state, message="模拟全部提交。")


@router.get("/states")
async def list_states() -> dict:
    return {"states": [st.value for st in DemoState]}
