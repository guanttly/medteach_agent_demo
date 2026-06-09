"""REST 请求 / 响应模型。"""
from __future__ import annotations

from pydantic import BaseModel


class MessageRequest(BaseModel):
    session_id: str = "demo_001"
    message: str


class TurnRequest(BaseModel):
    """前台 Conversation Gateway 的统一用户输入。"""

    session_id: str = "demo_001"
    text: str
    source: str = "voice"  # voice | text | control
    barge_in: bool = False
    interrupts_utterance_id: str | None = None
    interrupt_policy: str | None = None  # stop_low_priority | stop_all
    client_time: float | None = None


class InterruptRequest(BaseModel):
    """用户插话/打断（通常由语音端在检测到说话起点时上报）。"""

    session_id: str = "demo_001"
    utterance_id: str | None = None
    reason: str = "user_barge_in"
    policy: str = "stop_low_priority"  # stop_low_priority | stop_all
    job_id: str | None = None
    job_policy: str = "continue"  # continue | pause


class TurnResponse(BaseModel):
    ok: bool = True
    turn_id: str
    accepted: bool = True
    routed_as: str | None = None
    state: str | None = None



class ConfirmRequest(BaseModel):
    session_id: str = "demo_001"
    confirmation_type: str = "confirm_plan"  # confirm_plan | confirm_publish


class PublishRequest(BaseModel):
    session_id: str = "demo_001"


class ControlStepRequest(BaseModel):
    session_id: str = "demo_001"
    target_state: str


class ResetRequest(BaseModel):
    session_id: str = "demo_001"


class ModeRequest(BaseModel):
    session_id: str = "demo_001"
    mode: str  # mock | real | hybrid


class PresetRequest(BaseModel):
    session_id: str = "demo_001"
    preset: str  # arrange | confirm_plan | publish | simulate_submit


class TTSRequest(BaseModel):
    text: str
    voice: str | None = None


class ActionResponse(BaseModel):
    ok: bool = True
    state: str
    message: str | None = None
