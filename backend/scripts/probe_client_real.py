"""直接驱动真实 TeachingPlatformClient（real 模式），逐个工具看真实返回。

这是最贴近线上的端到端体检：跟数字人问答 / 工具页走同一套代码。
运行：cd backend && NO_PROXY=platform.jushacloud.com ./.venv/bin/python -m scripts.probe_client_real
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402

CORE = str(settings.CLAUDE_CORE_DIR)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

GREEN, RED, YEL, DIM, RST = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"

client = TeachingPlatformClient(mode="real")

CASES = [
    ("get_data_board", {}),
    ("get_present_students", {}),
    ("search_students", {"keyword": "马", "scope": "in"}),
    ("list_exams", {}),
    ("list_questions", {}),
    ("list_teaching_plans", {}),
    ("recommend_cases", {}),
    ("get_exam_preview", {}),
    ("get_exam_progress", {}),
    ("get_exam_result", {}),
]


def brief(data) -> str:
    if isinstance(data, dict):
        if "students" in data:
            return f"total={data.get('total')} 名册={len(data['students'])} 例：{[s['name'] for s in data['students'][:3]]}"
        if "exams" in data:
            return f"total={data.get('total')} 考试={len(data['exams'])} 例：{[e['name'] for e in data['exams'][:2]]}"
        if "questions" in data:
            return f"total={data.get('total')} 题目={len(data['questions'])}"
        if "plans" in data:
            return f"total={data.get('total')} 计划={len(data['plans'])}"
        if "cases" in data:
            return f"病例={len(data['cases'])}"
        if "summary" in data:
            s = data["summary"]
            return f"{data.get('exam_name')} 平均{s.get('average')} 及格率{s.get('pass_rate')}% 交卷{s.get('submitted')}/{s.get('total')}"
        if "exam" in data:
            e = data["exam"]
            return f"考试{e.get('exam_num')} 试卷{e.get('paper_num')} 题目{e.get('question_num')}"
        if "label" in data:
            return f"{data.get('label')} 交卷{data.get('submitted')}/{data.get('published')}"
        return json.dumps(data, ensure_ascii=False)[:90]
    return str(data)[:90]


def main() -> None:
    print(f"\n{DIM}mode=real base={client.base_url}{RST}\n{DIM}{'='*80}{RST}")
    for method, kwargs in CASES:
        t0 = time.time()
        try:
            res = getattr(client, method)(**kwargs)
            ms = (time.time() - t0) * 1000
            ok = res.get("ok")
            fb = res.get("fallback")
            err = res.get("error")
            if ok and not fb:
                print(f"{GREEN}真实OK{RST}  {method:<22} ({ms:.0f}ms)  {DIM}{brief(res.get('data'))}{RST}")
            elif err:
                msg = err.get("message") if isinstance(err, dict) else err
                print(f"{RED}失败  {RST}  {method:<22} ({ms:.0f}ms)  {YEL}{msg}{RST}")
            else:
                print(f"{YEL}回退  {RST}  {method:<22} ({ms:.0f}ms)")
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}异常  {RST}  {method:<22}  {type(exc).__name__}: {exc}")
    print(f"{DIM}{'='*80}{RST}")


if __name__ == "__main__":
    main()
