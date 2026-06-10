#!/usr/bin/env python3
"""medteach-agent-core MCP server：把真实教学平台只读工具暴露给 Claude Code 自主调用。

Claude Code CLI 通过 `.mcp.json`（由后端 claude_code_client 运行时生成）以 stdio 方式
启动本 server。每个工具直接调用 `adapter.TeachingPlatformClient`（real / hybrid / mock 由
TEACHING_PLATFORM_MODE / DEMO_MODE 决定），返回 `{ok, fallback, data, error}` 结构，
便于 Claude 据实总结、绝不编造；任何异常都被包成 error，保证 server 不崩。

注意：本 server 必须用「有 httpx 的解释器」启动（后端 venv），系统 python3 没有 httpx。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# 把 core 目录加入 sys.path，便于 import adapter（不依赖 cwd）。
_CORE_DIR = Path(__file__).resolve().parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("medteach")

_client: Any = None


def _get_client() -> Any:
    """惰性创建工具箱单例。real/hybrid/mock 由环境变量决定。"""
    global _client
    if _client is None:
        from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

        mode = os.getenv("TEACHING_PLATFORM_MODE") or os.getenv("DEMO_MODE") or "hybrid"
        _client = TeachingPlatformClient(mode=mode)
    return _client


def _safe(method: str, *args: Any) -> dict[str, Any]:
    """统一调用入口：异常吞掉并返回错误结构，保证 MCP server 永不崩。"""
    try:
        fn = getattr(_get_client(), method)
        result = fn(*args)
        if isinstance(result, dict):
            return result
        return {"ok": True, "fallback": False, "data": result, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "fallback": True, "data": None, "error": {"message": str(exc)}}


@mcp.tool()
def get_data_board() -> dict:
    """查询教学/考试综合数据看板：考试数、试卷数、题量、平均分、教学场次等整体概览。"""
    return _safe("get_data_board")


@mcp.tool()
def get_present_students() -> dict:
    """查询当前在科的现场学员名单（姓名、工号等）。"""
    return _safe("get_present_students")


@mcp.tool()
def search_students(keyword: str = "", scope: str = "in", page: int = 1, size: int = 20) -> dict:
    """按关键字检索学员。scope=in 在科 / out 全部。"""
    return _safe("search_students", keyword or None, page, size, scope)


@mcp.tool()
def list_exams(page: int = 1, size: int = 10) -> dict:
    """拉取我创建的考试列表与状态（用于考试列表 / 监考 / 答题进度概览）。"""
    return _safe("list_exams", page, size)


@mcp.tool()
def get_exam_result(exam_id: str = "") -> dict:
    """查询最近已结束（或指定 exam_id）考试的平均分、及格率、薄弱点等成绩分析。"""
    return _safe("get_exam_result", exam_id or None)


@mcp.tool()
def list_questions(page: int = 1, size: int = 10) -> dict:
    """拉取题库题目与题型分布。"""
    return _safe("list_questions", page, size)


@mcp.tool()
def recommend_cases() -> dict:
    """基于专题培训病例库，为薄弱点推荐复训病例。"""
    return _safe("recommend_cases")


@mcp.tool()
def list_teaching_plans(page: int = 1, size: int = 10) -> dict:
    """拉取近期教学计划 / 阅片排课安排。"""
    return _safe("list_teaching_plans", page, size)


if __name__ == "__main__":
    mcp.run()
