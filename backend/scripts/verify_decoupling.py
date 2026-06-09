"""离线端到端验证脚本：直接驱动 Conversation Gateway + Workflow Engine，
捕获经 ws_manager 广播的事件，逐条校验方案第 13.2 节的验收点。

运行：cd backend && python -m scripts.verify_decoupling
不依赖网络 / LLM：未配置大模型时走确定性兜底路径，恰好验证「硬保障」。
"""
from __future__ import annotations

import asyncio
import os
import time

# 缩短各步骤延时，加速验证（必须在 import app 之前设置）
os.environ.setdefault("STEP_DELAY", "0.05")
os.environ.setdefault("PROGRESS_DELAY", "0.05")
# 关闭大模型，走确定性兜底路径：本脚本验证的是「不依赖 LLM 也成立的硬保障」。
# （LLM 增强路径需真实网络，单独在联网环境验证。）
os.environ["LLM_ENABLED"] = "false"

from app import ws_manager as ws_module  # noqa: E402
from app.interaction.gateway import gateway  # noqa: E402
from app.session_store import session_store  # noqa: E402

EVENTS: list[dict] = []
PASS = 0
FAIL = 0


async def _capture(session_id: str, payload: dict) -> None:
    payload = dict(payload)
    payload["_t"] = time.perf_counter()
    EVENTS.append(payload)


# 劫持广播，离线捕获所有事件。event_bus / presenter 都复用同一个 ws_manager 单例，
# 因此在实例上打补丁即可覆盖全部出口。
ws_module.ws_manager.broadcast = _capture  # type: ignore[assignment]


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \033[92mPASS\033[0m  {name}")
    else:
        FAIL += 1
        print(f"  \033[91mFAIL\033[0m  {name}  {detail}")


def types_of(start: int = 0) -> list[str]:
    return [e.get("type") for e in EVENTS[start:]]


def find(type_: str, start: int = 0):
    for e in EVENTS[start:]:
        if e.get("type") == type_:
            return e
    return None


def find_all(type_: str, start: int = 0):
    return [e for e in EVENTS[start:] if e.get("type") == type_]


async def wait_state(s, target: str, timeout: float = 8.0) -> bool:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        if s.state == target:
            return True
        await asyncio.sleep(0.02)
    return False


async def wait_confirm(s, ctype: str, timeout: float = 8.0) -> bool:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        if s.need_user_confirmation and s.confirmation_type == ctype:
            return True
        await asyncio.sleep(0.02)
    return False


async def scenario_immediate_and_nonblocking():
    print("\n[1] 即时响应 + 后台非阻塞")
    s = session_store.get("verify_1")
    s.reset()
    EVENTS.clear()

    t0 = time.perf_counter()
    turn = await gateway.handle_turn(s, "帮我安排一场胸部 CT 基础考试", source="voice")
    # 立即响应：首个 utterance.started 应在 800ms 内
    first = find("utterance.started")
    latency_ms = (first["_t"] - t0) * 1000 if first else 9999
    check("收到安排请求后 <800ms 给出即时口播", latency_ms < 800, f"latency={latency_ms:.0f}ms")
    check("turn 记录了首响延迟", turn.first_response_latency_ms is not None
          and turn.first_response_latency_ms < 800,
          f"turn.latency={turn.first_response_latency_ms}")
    check("即时回应为 ack 来源", (first or {}).get("data", {}).get("source") == "ack")

    # 后台 job 已创建并在推进（非阻塞）
    await asyncio.sleep(0.1)
    check("已创建后台 job", len(s.jobs) == 1 and len(s.active_jobs()) == 1)

    # job 应自行推进到「方案确认」点（前台没有再发任何输入）
    ok = await wait_confirm(s, "confirm_plan")
    check("后台 job 自行推进到方案确认点", ok, f"state={s.state}")
    await asyncio.sleep(0.3)  # 等确认口播发出
    check("方案确认请求已口播",
          any(e.get("data", {}).get("source") == "confirmation"
              for e in find_all("utterance.started")))
    return s


async def scenario_context_qa_no_fabrication(s):
    print("\n[2] 上下文问答（先无名单→不编造；确认后→有名单）")
    # 此刻在 confirm_plan，participants 尚未查询
    mark = len(EVENTS)
    await gateway.handle_turn(s, "今天有哪些学员参加？", source="voice")
    started = [e for e in EVENTS[mark:] if e.get("type") == "utterance.started"]
    qa_text = ""
    for e in find_all("utterance.completed", mark):
        qa_text += e.get("data", {}).get("text", "")
    check("名单未就绪时仍即时回应（不静默）", len(started) >= 1)
    check("名单未就绪时不编造姓名",
          ("张伟" not in qa_text) and ("李静" not in qa_text),
          f"text={qa_text[:40]}")
    check("确认点未被问答破坏（仍等待确认）", s.need_user_confirmation
          and s.confirmation_type == "confirm_plan")

    # 自然确认表达 → 意图识别后推进到名单查询
    await gateway.handle_turn(s, "就按这个方案往下走", source="voice")
    # 等待 participants fact 出现
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 8 and not s.students:
        await asyncio.sleep(0.02)
    check("确认后查询到现场学员名单", bool(s.students), f"students={len(s.students or [])}")

    mark2 = len(EVENTS)
    await gateway.handle_turn(s, "现在有哪些学员？", source="voice")
    ans = ""
    for e in find_all("utterance.completed", mark2):
        ans += e.get("data", {}).get("text", "")
    names_hit = sum(1 for n in ("张伟", "李静", "王磊") if n in ans)
    check("名单就绪后能报出真实姓名", names_hit >= 2, f"ans={ans[:60]}")


async def scenario_barge_in():
    print("\n[3] 打断 / generation 失效")
    s = session_store.get("verify_bargein")
    s.reset()
    EVENTS.clear()
    from app.interaction.speaker import speaker

    gen0 = s.generation
    long_text = "这是一段比较长的播报内容，用来模拟数字人正在讲话时被用户打断的场景，" * 3
    say_task = asyncio.create_task(
        speaker.say(s, long_text, priority="normal", source="smalltalk")
    )
    await asyncio.sleep(0.08)  # 让它开始播
    check("播报中 speaking=True", s.interaction.get("speaking") is True)
    await gateway.handle_interrupt(s, policy="stop_low_priority", reason="user_barge_in")
    check("打断后 generation 自增", s.generation == gen0 + 1, f"{gen0}->{s.generation}")
    check("打断广播了 interaction.interrupted", find("interaction.interrupted") is not None)
    await say_task
    completed = [e for e in find_all("utterance.completed")
                 if e.get("session_id") == s.session_id]
    interrupted_completes = [e for e in completed
                             if e.get("data", {}).get("interrupted")]
    check("被打断的播报不产生「正常完成」",
          all(e.get("data", {}).get("interrupted") for e in completed) or not completed,
          f"completed={len(completed)}, interrupted={len(interrupted_completes)}")
    check("打断后 speaking 复位", s.interaction.get("speaking") is False)


async def scenario_high_priority_not_interrupted():
    print("\n[4] 高优先级播报不被普通插话打断")
    s = session_store.get("verify_prio")
    s.reset()
    EVENTS.clear()
    from app.interaction.speaker import speaker

    gen0 = s.generation
    task = asyncio.create_task(
        speaker.say(s, "这是确认请求，请讲师确认后我再继续。" * 3,
                    priority="high", source="confirmation", interruptible=False)
    )
    await asyncio.sleep(0.06)
    await gateway.handle_interrupt(s, policy="stop_low_priority")
    check("普通插话未推进 generation（高优先级受保护）", s.generation == gen0,
          f"{gen0}->{s.generation}")
    await task


async def scenario_narration_coalescing():
    print("\n[5] 播报聚合（多条进度合并为一段）")
    s = session_store.get("verify_nar")
    s.reset()
    EVENTS.clear()
    from app.interaction.models import Priority
    from app.interaction.narration import narration

    for i in range(4):
        await narration.enqueue(
            s, kind="progress", summary_key="exam_progress",
            priority=Priority.NORMAL.value, job_id="job_x",
            payload={"text": f"进度更新 {i}"},
        )
    pending = len(s.pending_narration)
    check("同类进度被合并（pending<=入队次数）", pending <= 2, f"pending={pending}")
    await narration.flush(s, force=True)
    summaries = find_all("narration.summary_emitted")
    check("聚合后只播一段总结", len(summaries) == 1, f"summaries={len(summaries)}")
    check("总结后清空待播队列", len(s.pending_narration) == 0)


async def scenario_snapshot_recovery():
    print("\n[6] 快照恢复（断线重连对齐）")
    s = session_store.get("verify_1")  # 复用已推进到中段的会话
    snap = s.snapshot()
    for key in ("generation", "facts", "fact_versions", "jobs", "active_jobs",
                "interaction", "state"):
        check(f"快照包含 {key}", key in snap, f"keys={list(snap.keys())}")
    check("快照 facts 含已知 participants", "participants" in snap.get("facts", {}))


async def scenario_full_golden_path():
    print("\n[7] 完整黄金路径（安排→确认→下发→阅卷→推荐→完成）")
    s = session_store.get("verify_golden")
    s.reset()
    EVENTS.clear()

    await gateway.handle_turn(s, "安排一场胸部 CT 基础考试", source="voice")
    check("到达方案确认", await wait_confirm(s, "confirm_plan"), f"state={s.state}")
    await gateway.handle_turn(s, "就按这个来", source="voice")
    check("到达下发确认", await wait_confirm(s, "confirm_publish"), f"state={s.state}")
    await gateway.handle_turn(s, "可以下发给学员了", source="voice")
    check("流程跑到 DONE", await wait_state(s, "DONE", timeout=12), f"state={s.state}")

    # 关键 domain 事件齐全
    domains = [e.get("data", {}).get("fact_path") for e in find_all("domain.updated")]
    for fact in ("exam_plan", "participants", "exam_preview", "result", "recommendation"):
        check(f"domain 事件含 {fact}", fact in domains, f"domains={domains}")
    check("产出阅卷结果 fact", bool(s.result))
    check("产出推荐病例 fact", bool(s.recommendation))

    # 旧前端兼容事件仍在广播
    legacy = set(types_of())
    for lt in ("workflow_update", "exam_plan_update", "students_update",
               "exam_result_update", "case_recommendation_update"):
        check(f"保留旧兼容事件 {lt}", lt in legacy)


async def scenario_reset_and_cancel():
    print("\n[8] 取消 / 重置")
    s = session_store.get("verify_cancel")
    s.reset()
    EVENTS.clear()
    await gateway.handle_turn(s, "安排一场胸部 CT 基础考试", source="voice")
    await wait_confirm(s, "confirm_plan")
    await gateway.handle_turn(s, "先停一下", source="voice")
    # 取消会在当前确认口播/步骤的下一个 await 点被观测到
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 4 and s.active_jobs():
        await asyncio.sleep(0.05)
    check("取消后没有活跃 job", len(s.active_jobs()) == 0, f"active={len(s.active_jobs())}")

    EVENTS.clear()
    await gateway.handle_turn(s, "重新开始", source="voice")
    await asyncio.sleep(0.2)
    check("重置广播 demo_reset", find("demo_reset") is not None)
    check("重置后回到 IDLE/初始", s.state in ("IDLE", "GREETING", "idle"), f"state={s.state}")


async def main():
    print("=" * 64)
    print(" 交互/工作流解耦 —— 端到端验证")
    print("=" * 64)
    s = await scenario_immediate_and_nonblocking()
    await scenario_context_qa_no_fabrication(s)
    await scenario_barge_in()
    await scenario_high_priority_not_interrupted()
    await scenario_narration_coalescing()
    await scenario_snapshot_recovery()
    await scenario_full_golden_path()
    await scenario_reset_and_cancel()

    print("\n" + "=" * 64)
    print(f" 结果：PASS={PASS}  FAIL={FAIL}")
    print("=" * 64)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
