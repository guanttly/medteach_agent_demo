"""教学平台工具箱验证路由。

把 medteach-agent-core 里真实工具箱（TeachingPlatformClient）的能力暴露成
「可查看 + 可点击调用」的接口，供前端工具验证页直接测试真实教学平台 Agent 效果：

- GET  /api/tools         列出全部工具 + 平台接入状态
- GET  /api/tools/status  仅平台接入状态
- POST /api/tools/invoke  直接调用某个工具（可临时指定 mode），返回真实/回退、耗时与数据
- POST /api/tools/prewarm 演示前一键预热只读模块（回填缓存，现场秒开）
- GET  /api/tools/scenarios 列出可一键验证的组合演示场景
- POST /api/tools/scenario 按顺序跑通一个组合场景，逐步汇报真实/回退/空/失败
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from .. import platform_bridge
from ..models.schemas import PrewarmRequest, ScenarioRunRequest, ToolInvokeRequest

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_tools() -> dict:
    status = await asyncio.to_thread(platform_bridge.platform_status)
    return {
        "tools": platform_bridge.list_tools(),
        "scenarios": platform_bridge.list_scenarios(),
        "platform": status,
    }


@router.get("/status")
async def tools_status() -> dict:
    return await asyncio.to_thread(platform_bridge.platform_status)


@router.post("/invoke")
async def invoke_tool(req: ToolInvokeRequest) -> dict:
    return await platform_bridge.invoke_tool(req.key, req.params, req.mode)


@router.post("/prewarm")
async def prewarm(req: PrewarmRequest) -> dict:
    return await platform_bridge.prewarm(req.modules)


@router.get("/scenarios")
async def scenarios() -> dict:
    return {"scenarios": platform_bridge.list_scenarios()}


@router.post("/scenario")
async def run_scenario(req: ScenarioRunRequest) -> dict:
    return await platform_bridge.run_scenario(req.key, req.mode)
