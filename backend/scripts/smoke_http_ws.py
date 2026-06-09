"""HTTP 路由烟雾测试：通过真实 FastAPI 应用走前端实际调用的接口，并捕获广播事件。

与 verify_decoupling 不同，这里经由真实 HTTP 路由（TestClient）驱动，
重点校验「路由层序列化 + 端到端事件流」：
- POST /api/conversation/turn 非阻塞，返回 TurnResponse 形状
- 广播出带 generation 的 utterance.* 语义事件（字段与前端 store 对齐）
- 确认后工作流推进、产出 domain/legacy 事件
- GET /api/sessions/{id}/snapshot / jobs 正常返回
- POST /api/conversation/interrupt 触发 generation 递增

事件捕获通过 monkeypatch ws_manager.broadcast 完成，避免 TestClient WS 阻塞。
离线安全（LLM/TTS 关闭，走确定性兜底）。
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("STEP_DELAY", "0.05")
os.environ.setdefault("PROGRESS_DELAY", "0.05")
os.environ["LLM_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import ws_manager as ws_module  # noqa: E402
from app.main import app  # noqa: E402

SID = "smoke_http_1"
PASS = 0
FAIL = 0
EVENTS: list[dict] = []


async def _capture(session_id: str, event: dict) -> None:
    if session_id == SID:
        EVENTS.append(event)


ws_module.ws_manager.broadcast = _capture  # type: ignore[assignment]


def check(name: str, ok: bool) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def types_of() -> list[str]:
    return [e.get("type") for e in EVENTS]


def wait_for(pred, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def main() -> int:
    # 用 context manager 保持单一持久事件循环，使非阻塞后台 job 任务在多次请求间存活。
    with TestClient(app) as client:
        return _run(client)


def _run(client: TestClient) -> int:
    # 连接快照：通过真实 WS 建链触发 push_snapshot（随后立即断开，仅取首帧）
    try:
        with client.websocket_connect(f"/ws/demo/{SID}"):
            pass
    except Exception:
        pass
    check("连接即广播 snapshot", "snapshot" in types_of())

    # 1) 安排考试（非阻塞）
    EVENTS.clear()
    t0 = time.time()
    r = client.post(
        "/api/conversation/turn",
        json={"session_id": SID, "text": "安排一场胸部CT基础考试", "source": "voice"},
    )
    dt = (time.time() - t0) * 1000
    check("turn 返回 200", r.status_code == 200)
    body = r.json()
    check("TurnResponse.ok", body.get("ok") is True)
    check("TurnResponse 含 turn_id", bool(body.get("turn_id")))
    check("turn 接口快速返回(<800ms)", dt < 800)

    wait_for(lambda: "utterance.completed" in types_of(), 3.0)
    t = types_of()
    check("收到 user_message", "user_message" in t)
    check("收到 utterance.started", "utterance.started" in t)
    check("收到 utterance.delta", "utterance.delta" in t)
    check("收到 utterance.completed", "utterance.completed" in t)
    delta = next((e for e in EVENTS if e.get("type") == "utterance.delta"), None)
    check("utterance 事件带 generation", isinstance((delta or {}).get("generation"), int))
    check("utterance 事件带 utterance_id", bool((delta or {}).get("utterance_id")))
    check("utterance.delta.data 含 text", "text" in (delta or {}).get("data", {}))
    started = next((e for e in EVENTS if e.get("type") == "utterance.started"), None)
    check("utterance.started.data 含 shark_state", "shark_state" in (started or {}).get("data", {}))
    check("utterance.started.data 含 tts", "tts" in (started or {}).get("data", {}))
    sent = next((e for e in EVENTS if e.get("type") == "utterance.sentence"), None)
    check("utterance.sentence.data 含 sentence", "sentence" in (sent or {}).get("data", {}))

    # 等待后台 job 到达「等待确认」
    wait_for(
        lambda: any(
            e.get("type") == "core_status_update"
            and e.get("data", {}).get("need_user_confirmation")
            for e in EVENTS
        ),
        5.0,
    )
    check("到达方案确认(need_user_confirmation)", any(
        e.get("type") == "core_status_update" and e.get("data", {}).get("need_user_confirmation")
        for e in EVENTS
    ))

    # 2) 自然确认表达 → 意图识别后工作流推进
    EVENTS.clear()
    r2 = client.post(
        "/api/conversation/turn",
        json={"session_id": SID, "text": "就按这个方案往下走", "source": "voice"},
    )
    check("确认 turn 返回 200", r2.status_code == 200)
    wait_for(lambda: "workflow_update" in types_of(), 6.0)
    t3 = types_of()
    check("确认后有 legacy workflow_update", "workflow_update" in t3)
    wait_for(
        lambda: any(
            x in types_of() for x in ("domain.updated", "exam_preview_update", "students_update")
        ),
        8.0,
    )
    t3b = types_of()
    check("确认后有 domain.updated 或 *_update", (
        "domain.updated" in t3b
        or "exam_preview_update" in t3b
        or "students_update" in t3b
    ))

    # 3) 快照 / jobs 接口
    snap = client.get(f"/api/sessions/{SID}/snapshot")
    check("snapshot 接口 200", snap.status_code == 200)
    sj = snap.json()
    check("snapshot 含 generation", isinstance(sj.get("generation"), int))
    check("snapshot 含 facts", "facts" in sj)
    jobs = client.get(f"/api/sessions/{SID}/jobs")
    check("jobs 接口 200", jobs.status_code == 200)

    # 4) 打断接口
    EVENTS.clear()
    gen_before = sj.get("generation", 0)
    ri = client.post(
        "/api/conversation/interrupt",
        json={"session_id": SID, "reason": "user_barge_in", "policy": "stop_low_priority"},
    )
    check("interrupt 接口 200", ri.status_code == 200)
    time.sleep(0.4)
    snap2 = client.get(f"/api/sessions/{SID}/snapshot").json()
    check("打断后 generation 单调不减", snap2.get("generation", 0) >= gen_before)

    print("=" * 56)
    print(f" 结果：PASS={PASS}  FAIL={FAIL}")
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
