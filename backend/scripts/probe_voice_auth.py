"""探针：验证「语音授权」链路（把文字授权搬到语音）。

不依赖真实 CC / 网络：monkeypatch claude_client.run_agentic_query 为假实现，
确定性地验证：开放问答触发语音授权请求 → 用户口头同意/拒绝 → 授权后继续执行。

运行：cd backend && .venv/bin/python -m scripts.probe_voice_auth
"""
from __future__ import annotations

import asyncio
import os

# 在 import app 之前固定配置：开启语音授权、hybrid 引擎、给个占位 Key 让 agentic 通道判定为可用；
# 关闭真实 LLM 意图/总结，保证路由确定（不打网络）。
os.environ["CLAUDE_VOICE_AUTH"] = "true"
os.environ["AGENT_ENGINE"] = "hybrid"
os.environ["LLM_ENABLED"] = "true"
os.environ["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "sk-probe-placeholder")
os.environ["VOICE_INTENT_LLM"] = "false"
os.environ["VOICE_SUMMARY_LLM"] = "false"
os.environ["STEP_DELAY"] = "0.02"

from app import ws_manager as ws_module  # noqa: E402
from app.claude_code_client import claude_client  # noqa: E402
from app.interaction.gateway import gateway  # noqa: E402
from app.session_store import session_store  # noqa: E402

EVENTS: list[dict] = []


async def _capture(session_id: str, payload: dict) -> None:
    EVENTS.append(dict(payload))


ws_module.ws_manager.broadcast = _capture  # type: ignore[assignment]

_CC_CALLS: list[dict] = []


async def _fake_cc(user_text: str, *, mode=None, bypass=False):
    _CC_CALLS.append({"text": user_text, "bypass": bypass})
    return {
        "assistant_text": f"（测试）我查到了关于「{user_text}」的结果。",
        "tool": "get_data_board", "fallback": True,
        "ok": True, "needs_authorization": False, "denied_tools": [], "error": None,
    }


claude_client.run_agentic_query = _fake_cc  # type: ignore[assignment]


def _spoken(since: int = 0) -> list[str]:
    out = []
    for e in EVENTS[since:]:
        if e.get("type") in ("utterance.delta", "utterance.sentence"):
            txt = (e.get("data") or {}).get("text") or e.get("text") or ""
            if txt:
                out.append(txt)
    # 也兼容 assistant_text 快照
    return out


def _assistant_texts(since: int = 0) -> str:
    txt = ""
    for e in EVENTS[since:]:
        d = e.get("data") or {}
        if isinstance(d, dict) and d.get("assistant_text"):
            txt += " | " + str(d["assistant_text"])
    return txt


async def main() -> None:
    print("=== 场景 A：开放问答 → 触发语音授权请求 ===")
    s = session_store.get("auth-test-A")
    n0 = len(EVENTS)
    turn = await gateway.handle_turn(s, "给我一些教学方面的建议吧", source="voice")
    print("  routed_as =", turn.routed_as)
    print("  pending_authorization =", bool(s.conversation.get("pending_authorization")))
    print("  CC 是否被调用（应为否）=", len(_CC_CALLS) > 0)
    print("  授权请求话术片段 =", _assistant_texts(n0)[:120])
    assert s.conversation.get("pending_authorization"), "应挂起待授权请求"
    assert not _CC_CALLS, "授权前不应调用 CC"

    print("\n=== 场景 B：用户口头同意 → 授权并继续执行 ===")
    n1 = len(EVENTS)
    turn2 = await gateway.handle_turn(s, "可以，授权你查", source="voice")
    print("  routed_as =", turn2.routed_as)
    print("  granted =", s.conversation.get("granted_authorizations"))
    print("  pending 已清空 =", not s.conversation.get("pending_authorization"))
    print("  CC 被调用次数 =", len(_CC_CALLS))
    print("  执行后话术片段 =", _assistant_texts(n1)[:160])
    assert "platform_data" in (s.conversation.get("granted_authorizations") or []), "应记录授权"
    assert len(_CC_CALLS) == 1, "授权后应继续执行 CC 一次"

    print("\n=== 场景 C：已授权 → 同类问题不再询问，直接执行 ===")
    n2 = len(EVENTS)
    _CC_CALLS.clear()
    turn3 = await gateway.handle_turn(s, "再帮我分析一下整体的训练情况", source="voice")
    print("  routed_as =", turn3.routed_as)
    print("  CC 被调用次数（应为1）=", len(_CC_CALLS))
    print("  pending（应为空）=", bool(s.conversation.get("pending_authorization")))
    assert len(_CC_CALLS) == 1, "已授权应直接执行 CC"
    assert not s.conversation.get("pending_authorization"), "已授权不应再次挂起"

    print("\n=== 场景 D：用户口头拒绝 → 优雅作罢，不执行 CC ===")
    s2 = session_store.get("auth-test-D")
    _CC_CALLS.clear()
    await gateway.handle_turn(s2, "帮我评估一下这次的整体效果和建议", source="voice")
    assert s2.conversation.get("pending_authorization"), "应先挂起授权请求"
    n3 = len(EVENTS)
    turn4 = await gateway.handle_turn(s2, "不用了，先别查", source="voice")
    print("  routed_as =", turn4.routed_as)
    print("  CC 被调用次数（应为0）=", len(_CC_CALLS))
    print("  拒绝后话术片段 =", _assistant_texts(n3)[:160])
    assert len(_CC_CALLS) == 0, "拒绝后不应执行 CC"
    assert not s2.conversation.get("pending_authorization"), "拒绝后应清空挂起"

    print("\n[probe] 语音授权链路全部通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
