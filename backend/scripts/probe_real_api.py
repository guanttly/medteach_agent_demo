"""真实教学平台接口全面体检（只读）。

逐个直连真实平台调用每个工具的「真实路径」，分类汇报：
- OK(有数据) / OK(空数据) / 失败(网络/鉴权/平台报错)
不依赖 hybrid 回退，直接看真实接口到底通不通、是不是只是空数据。

运行：cd backend && ./.venv/bin/python -m scripts.probe_real_api
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# 让 app.config 先 load_dotenv，再把 core 加进 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402

CORE = str(settings.CLAUDE_CORE_DIR)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from adapter.auth_client import AuthClient  # noqa: E402

GREEN, RED, YEL, DIM, RST = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"

auth = AuthClient()


def call(service: str, method: str, path: str, *, json_body=None, params=None):
    """直连真实接口，返回 (ok, data_or_err, raw_state)。"""
    import httpx

    if not auth.configured():
        return False, "凭据未配置", None
    url = f"{auth.base_url}/{service.strip('/')}{path}"
    with httpx.Client(timeout=auth.timeout, verify=auth.verify_ssl) as client:
        for attempt in range(2):
            headers = auth.auth_headers(force_refresh=(attempt == 1))
            resp = client.request(method.upper(), url, json=json_body, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, dict) and body.get("errorCode") == 401:
                auth.invalidate()
                continue
            if isinstance(body, dict) and body.get("state") is False:
                return False, f"平台报错 errorCode={body.get('errorCode')} msg={body.get('message')}", body
            return True, (body.get("data") if isinstance(body, dict) else body), body
    return False, "鉴权重试后仍失败", None


def _count(data) -> int:
    """估算返回里的记录数（PageInfo.list / 数组 / 字典）。"""
    if data is None:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for k in ("list", "records", "rows", "data", "students", "exams", "questions"):
            v = data.get(k)
            if isinstance(v, list):
                return len(v)
        if "total" in data:
            try:
                return int(data["total"])
            except (TypeError, ValueError):
                return 0
        return len(data)
    return 0


PROBES = [
    ("数据看板(考试)", "riemanExam", "POST", "/stat/mngBoard", {}, None),
    ("数据看板(教学)", "riemanEdu", "POST", "/stat/mngBoard", {}, None),
    ("在科学员", "riemanBase", "POST", "/department/in/user/search", {"pageNum": 1, "pageSize": 50}, None),
    ("学员检索(out)", "riemanBase", "POST", "/department/out/user/search", {"pageNum": 1, "pageSize": 20}, None),
    ("考试列表", "riemanExam", "POST", "/exam/my/create/list", {"pageNum": 1, "pageSize": 20}, None),
    ("题库", "riemanExam", "POST", "/question/all/list", {"pageNum": 1, "pageSize": 10}, None),
    ("教学计划", "riemanEdu", "POST", "/education/plan/search", {"pageNum": 1, "pageSize": 10}, None),
    ("复训病例", "riemanEdu", "POST", "/train/case/list", {"pageNum": 1, "pageSize": 8}, None),
]


def main() -> None:
    print(f"\n{DIM}base={auth.base_url}  configured={auth.configured()}  verify_ssl={auth.verify_ssl}{RST}")
    print(f"{DIM}{'='*78}{RST}")

    # 先单独验证登录
    try:
        t0 = time.time()
        token = auth.get_token(force_refresh=True)
        print(f"{GREEN}登录成功{RST}  token={token[:28]}…  ({(time.time()-t0)*1000:.0f}ms)\n")
    except Exception as exc:  # noqa: BLE001
        print(f"{RED}登录失败{RST}：{exc}")
        return

    results: list[tuple[str, str]] = []
    latest_exam_id = None
    for name, svc, method, path, body, params in PROBES:
        t0 = time.time()
        try:
            ok, data, _ = call(svc, method, path, json_body=body, params=params)
            ms = (time.time() - t0) * 1000
            if not ok:
                print(f"{RED}失败{RST}  {name:<14} {method} /{svc}{path}\n        {DIM}{data}{RST}  ({ms:.0f}ms)")
                results.append((name, "失败"))
                continue
            n = _count(data)
            tag = f"{GREEN}OK(有数据 {n}){RST}" if n > 0 else f"{YEL}OK(空数据){RST}"
            print(f"{tag}  {name:<14} {method} /{svc}{path}  ({ms:.0f}ms)")
            results.append((name, "有数据" if n > 0 else "空数据"))
            if name == "考试列表" and isinstance(data, dict):
                lst = data.get("list") or data.get("records") or []
                if lst:
                    latest_exam_id = lst[0].get("id") or lst[0].get("examId")
        except Exception as exc:  # noqa: BLE001
            ms = (time.time() - t0) * 1000
            print(f"{RED}异常{RST}  {name:<14} {method} /{svc}{path}\n        {DIM}{type(exc).__name__}: {exc}{RST}  ({ms:.0f}ms)")
            results.append((name, "异常"))

    # 依赖最近考试 id 的接口
    if latest_exam_id:
        print(f"\n{DIM}最近考试 examId={latest_exam_id}，探测详情/进度/成绩…{RST}")
        for name, svc, method, path, body, params in [
            ("试卷详情", "riemanExam", "GET", "/exam/detail", None, {"examId": latest_exam_id}),
            ("答题进度", "riemanExam", "POST", "/exam/my/create/look/student",
             {"examId": latest_exam_id, "finishTag": -1, "pageNum": 1, "pageSize": 1}, None),
            ("成绩总览", "riemanExam", "GET", "/exam/my/create/list/result", None, {"examId": latest_exam_id}),
        ]:
            t0 = time.time()
            try:
                ok, data, _ = call(svc, method, path, json_body=body, params=params)
                ms = (time.time() - t0) * 1000
                if not ok:
                    print(f"{RED}失败{RST}  {name:<14}  {DIM}{data}{RST}  ({ms:.0f}ms)")
                else:
                    n = _count(data)
                    tag = f"{GREEN}OK(有数据 {n}){RST}" if n else f"{YEL}OK(空/标量){RST}"
                    print(f"{tag}  {name:<14}  ({ms:.0f}ms)  {DIM}{json.dumps(data, ensure_ascii=False)[:80]}{RST}")
            except Exception as exc:  # noqa: BLE001
                print(f"{RED}异常{RST}  {name:<14}  {type(exc).__name__}: {exc}")

    print(f"\n{DIM}{'='*78}{RST}")
    fails = [n for n, s in results if s in ("失败", "异常")]
    empties = [n for n, s in results if s == "空数据"]
    print(f"汇总：{GREEN}{sum(1 for _,s in results if s=='有数据')} 有数据{RST} · "
          f"{YEL}{len(empties)} 空数据{RST} · {RED}{len(fails)} 失败/异常{RST}")
    if empties:
        print(f"  {YEL}空数据（接口通、平台无内容）：{', '.join(empties)}{RST}")
    if fails:
        print(f"  {RED}真失败（需排查）：{', '.join(fails)}{RST}")


if __name__ == "__main__":
    main()
