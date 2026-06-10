"""探针：验证 Claude 自主调 MCP 工具（真实工具箱）链路是否打通。

这是接入语音网关前的关键验证点：确认本机 claude CLI + DeepSeek 后端能否
真正完成 MCP tool_use（自己选工具 → 调真实工具箱 → 拿数据 → 总结）。

用法：
    cd backend
    .venv/bin/python scripts/probe_agentic.py [query] [mode]

mode 默认 mock（不依赖真实平台网络，验证 tool_use 链路本身）；
可传 hybrid / real 测真实平台直连。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.claude_code_client import claude_client  # noqa: E402


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "看一下数据看板"
    mode = sys.argv[2] if len(sys.argv) > 2 else "mock"
    print(f"[probe] query={query!r} mode={mode}")
    try:
        result = await claude_client.run_agentic_query(query, mode=mode)
        print("[probe] OK ->", result)
    except Exception as exc:  # noqa: BLE001
        print(f"[probe] FAIL: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
