"""探针：验证语音「DeepSeek 快路径」——LLM 意图识别 + LLM 事实改写。

这是展厅默认（AGENT_ENGINE=hybrid）的体验主力：DeepSeek flash 秒级出话，
意图识别兜底正则、事实改写以确定性话术为底，杜绝编造。

用法：
    cd backend
    .venv/bin/python scripts/probe_voice_fastpath.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_brain import agent_brain  # noqa: E402


async def main() -> None:
    intent = await agent_brain.classify_voice_intent(
        message="看一下数据看板", state="idle", budget=10.0,
    )
    print("[intent] 看一下数据看板 ->", intent)

    facts = "目前平台共有 9 场考试、703 道题，平均分 15.9 分。（演示数据）"
    refined = await agent_brain.refine_answer(
        user_text="数据看板现在怎么样", facts=facts, budget=12.0,
    )
    print("[refine] ->", refined)


if __name__ == "__main__":
    asyncio.run(main())
