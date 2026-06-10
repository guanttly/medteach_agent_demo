"""真实平台 ResultBean.data → 展厅演示数据形状 的转换器。

设计原则：
- 容错：真实字段可能缺失 / 为 None，一律给安全缺省值，绝不抛异常打断演示。
- 贴合前端既有契约（frontend/src/types/index.ts 与 mock/*.json），
  让真实数据能直接驱动现有大屏组件。
- 新业务模块（数据看板 / 考试列表 / 题库 / 教学计划）定义简洁、稳定的展示形状。
"""
from __future__ import annotations

from typing import Any

# 与 mock/students.json、exam_result.json 一致的配色，保证现场观感统一。
_PALETTE = [
    "#4FD1C5", "#63B3ED", "#B794F4", "#F6AD55",
    "#FC8181", "#68D391", "#76E4F7", "#F687B3",
]


def _color(i: int) -> str:
    return _PALETTE[i % len(_PALETTE)]


def _as_list(page: Any) -> list[dict[str, Any]]:
    """从 PageInfo / 裸列表里取出 list。"""
    if isinstance(page, list):
        return [x for x in page if isinstance(x, dict)]
    if isinstance(page, dict):
        rows = page.get("list") or page.get("records") or page.get("rows") or []
        return [x for x in rows if isinstance(x, dict)]
    return []


def _total(page: Any, rows: list[dict[str, Any]]) -> int:
    if isinstance(page, dict):
        for key in ("total", "totalCount", "count"):
            if isinstance(page.get(key), int):
                return page[key]
    return len(rows)


def _num(v: Any, default: float = 0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _round(v: Any, ndigits: int = 1) -> float:
    return round(_num(v), ndigits)


# ------------------------------------------------------------------ #
# 人员 / 学员
# ------------------------------------------------------------------ #
def students_from_pageinfo(page: Any, group_name: str = "在科规培学员") -> dict[str, Any]:
    rows = _as_list(page)
    students: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        students.append(
            {
                "id": str(r.get("id") or r.get("userId") or r.get("userNo") or f"stu_{i + 1}"),
                "name": str(r.get("userName") or r.get("name") or "学员"),
                "department": str(
                    r.get("workplaceName")
                    or r.get("organName")
                    or r.get("profession")
                    or "—"
                ),
                "grade": str(r.get("studentTypeName") or r.get("proTitleName") or "规培学员"),
                "color": _color(i),
            }
        )
    return {
        "group_name": group_name,
        "total": _total(page, rows),
        "students": students,
    }


# ------------------------------------------------------------------ #
# 考试列表 / 监考
# ------------------------------------------------------------------ #
_EXAM_STATUS = {0: "未开始", 1: "进行中", 2: "已结束", 3: "已公布"}


def exams_from_pageinfo(page: Any) -> dict[str, Any]:
    rows = _as_list(page)
    exams = []
    for r in rows:
        exams.append(
            {
                "exam_id": r.get("examId") or r.get("id"),
                "name": str(r.get("name") or "未命名考试"),
                "paper_id": r.get("paperId"),
                "begin_time": r.get("beginTime"),
                "minutes": int(_num(r.get("minutes"))),
                "paper_score": _round(r.get("paperScore")),
                "pass_score": _round(r.get("passScore")),
                "published": bool(r.get("pubTag")),
                "status": _EXAM_STATUS.get(r.get("status"), "—"),
                "creator": str(r.get("createUserName") or "—"),
            }
        )
    return {"total": _total(page, rows), "exams": exams}


# ------------------------------------------------------------------ #
# 答题进度（look/student → 演示 progress 形状）
# ------------------------------------------------------------------ #
def progress_from_look(raw: Any, published: int | None = None) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    finish = int(_num(raw.get("finishNum")))
    not_finish = int(_num(raw.get("notFinishNum")))
    total = published if published is not None else finish + not_finish
    answering = max(total - finish, 0) if total else not_finish
    label = "全部提交" if total and finish >= total else "答题进行中"
    return {
        "label": label,
        "published": total or finish + not_finish,
        "entered": total or finish + not_finish,
        "answering": answering,
        "submitted": finish,
        "remaining_seconds": int(_num(raw.get("remainSeconds") or raw.get("remaining_seconds"))),
    }


# ------------------------------------------------------------------ #
# 阅卷结果（result 概览 + 成绩分布 + 学员成绩 → 演示 exam_result 形状）
# ------------------------------------------------------------------ #
def _level_for(score: float, pass_score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 80:
        return "良好"
    if score >= max(pass_score, 60):
        return "中等"
    return "待提升"


def exam_result_from_real(
    overview: Any,
    scores_page: Any = None,
    analysis: Any = None,
    *,
    exam_id: Any = None,
    exam_name: str = "",
) -> dict[str, Any]:
    o = overview if isinstance(overview, dict) else {}
    pass_score = _num(o.get("passScore"), 60)
    paper_score = _num(o.get("paperScore"), 100)
    total = int(_num(o.get("totalNum")))
    submitted = int(_num(o.get("doNum"))) or total

    rows = _as_list(scores_page)
    students = []
    score_values: list[float] = []
    for r in rows:
        score = _round(r.get("score") or r.get("totalScore"))
        score_values.append(score)
        students.append(
            {
                "id": str(r.get("studentId") or r.get("userId") or r.get("id") or ""),
                "name": str(r.get("studentName") or r.get("userName") or r.get("name") or "学员"),
                "score": score,
                "level": _level_for(score, pass_score),
            }
        )

    average = _round(o.get("avgScore")) or (
        _round(sum(score_values) / len(score_values)) if score_values else 0
    )
    highest = _round(max(score_values)) if score_values else _round(o.get("maxScore"))
    lowest = _round(min(score_values)) if score_values else _round(o.get("minScore"))
    pass_rate = _round(o.get("passRate"))
    # 平台 passRate 可能是 0~1 的比率，统一成百分数。
    if 0 < pass_rate <= 1:
        pass_rate = _round(pass_rate * 100)

    # 成绩分布：优先用 analysis.scoreDist，否则按学员成绩现算。
    distribution = _score_distribution(analysis, score_values, paper_score)
    weak_points = _weak_points_from_analysis(analysis)

    return {
        "exam_id": exam_id,
        "exam_name": exam_name or "教学考试",
        "summary": {
            "average": average,
            "highest": highest,
            "lowest": lowest,
            "pass_rate": pass_rate,
            "submitted": submitted or len(students),
            "total": total or len(students),
        },
        "score_distribution": distribution,
        "students": students,
        "weak_points": weak_points,
    }


def _score_distribution(analysis: Any, scores: list[float], paper_score: float) -> list[dict[str, Any]]:
    if isinstance(analysis, dict):
        dist = analysis.get("scoreDist") or analysis.get("scoreDistribution")
        if isinstance(dist, list) and dist:
            out = []
            for d in dist:
                if isinstance(d, dict):
                    out.append(
                        {
                            "range": str(d.get("range") or d.get("name") or d.get("label") or "—"),
                            "count": int(_num(d.get("count") or d.get("num"))),
                        }
                    )
            if out:
                return out
    # 现算：换算成百分制分段。
    buckets = [("90-100", 90, 101), ("80-89", 80, 90), ("70-79", 70, 80), ("60-69", 60, 70), ("<60", -1, 60)]
    scale = 100.0 / paper_score if paper_score else 1.0
    out = []
    for label, lo, hi in buckets:
        count = sum(1 for s in scores if lo <= s * scale < hi)
        out.append({"range": label, "count": count})
    return out


def _weak_points_from_analysis(analysis: Any) -> list[dict[str, Any]]:
    if not isinstance(analysis, dict):
        return []
    rates = (
        analysis.get("qstTypeCorrRates")
        or analysis.get("knowledgeRates")
        or analysis.get("stationRates")
        or []
    )
    weak = []
    for r in rates if isinstance(rates, list) else []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or r.get("typeName") or r.get("knowledge") or "知识点")
        corr = _num(r.get("corrRate") if r.get("corrRate") is not None else r.get("rate"))
        if 0 < corr <= 1:
            error_rate = round(1 - corr, 2)
        elif corr > 1:
            error_rate = round(max(0.0, 1 - corr / 100), 2)
        else:
            error_rate = round(_num(r.get("errorRate")), 2)
        weak.append({"name": name, "error_rate": error_rate, "comment": str(r.get("comment") or "")})
    weak.sort(key=lambda x: x["error_rate"], reverse=True)
    return weak[:3]


# ------------------------------------------------------------------ #
# 题库
# ------------------------------------------------------------------ #
_QST_TYPE = {
    1: "单选", 2: "多选", 3: "填空", 4: "判断",
    5: "问答", 6: "报告书写", 11: "不定项", 12: "共用题干",
}


def questions_from_pageinfo(page: Any) -> dict[str, Any]:
    rows = _as_list(page)
    questions = []
    for r in rows:
        questions.append(
            {
                "id": r.get("qstId") or r.get("id"),
                "content": str(r.get("contentTxt") or r.get("content") or "").strip()[:80],
                "type": _QST_TYPE.get(r.get("type"), "—"),
                "organ": str(r.get("organName") or "综合"),
                "difficulty": str(r.get("difficultyName") or "—"),
                "creator": str(r.get("createUserName") or "—"),
            }
        )
    return {"total": _total(page, rows), "questions": questions}


# ------------------------------------------------------------------ #
# 复训病例（train/case/list → 推荐病例形状）
# ------------------------------------------------------------------ #
def cases_from_pageinfo(page: Any, next_goal: str = "") -> dict[str, Any]:
    rows = _as_list(page)
    cases = []
    for i, r in enumerate(rows):
        tags = r.get("tags") or r.get("markNames") or []
        if isinstance(tags, str):
            tags = [t for t in tags.replace("，", ",").split(",") if t.strip()]
        cases.append(
            {
                "id": str(r.get("id") or r.get("caseId") or f"case_{i + 1}"),
                "title": str(r.get("title") or r.get("name") or r.get("caseName") or "复训病例"),
                "focus": str(r.get("focus") or r.get("organName") or r.get("sickName") or "综合训练"),
                "difficulty": str(r.get("difficultyName") or r.get("difficulty") or "中级"),
                "tags": [str(t) for t in tags][:4],
                "est_minutes": int(_num(r.get("estMinutes") or r.get("minutes"), 12)),
            }
        )
    return {
        "next_goal": next_goal or "结合薄弱点安排针对性复训病例，巩固诊断与报告表达能力。",
        "cases": cases,
    }


# ------------------------------------------------------------------ #
# 教学计划 / 教学回顾
# ------------------------------------------------------------------ #
def teaching_plans_from_pageinfo(page: Any) -> dict[str, Any]:
    rows = _as_list(page)
    plans = []
    for r in rows:
        plans.append(
            {
                "id": r.get("id"),
                "subject": str(r.get("subject") or r.get("title") or "教学安排"),
                "type": str(r.get("typeName") or "—"),
                "education_time": r.get("educationTime"),
                "end_time": r.get("endTime"),
                "lecturer": str(r.get("lectureNames") or r.get("teacherNames") or "—"),
                "host": str(r.get("holderNames") or "—"),
                "browse_count": int(_num(r.get("browseCount"))),
            }
        )
    return {"total": _total(page, rows), "plans": plans}


# ------------------------------------------------------------------ #
# 数据看板
# ------------------------------------------------------------------ #
def _dist(items: Any) -> list[dict[str, Any]]:
    out = []
    for d in items if isinstance(items, list) else []:
        if isinstance(d, dict):
            out.append({"name": str(d.get("name") or "—"), "num": int(_num(d.get("num")))})
    return out


def data_board_from_real(exam_board: Any, edu_board: Any = None) -> dict[str, Any]:
    e = exam_board if isinstance(exam_board, dict) else {}
    edu = edu_board if isinstance(edu_board, dict) else {}
    return {
        "exam": {
            "exam_num": int(_num(e.get("examNum"))),
            "paper_num": int(_num(e.get("paperNum"))),
            "question_num": int(_num(e.get("qstNum"))),
            "exam_avg": _round(e.get("examAvg")),
            "paper_level_dist": _dist(e.get("paperLevelList")),
            "question_type_dist": _dist(e.get("qstTypeList")),
        },
        "teaching": {
            "education_num": int(_num(edu.get("eduNum"))),
            "livestream_num": int(_num(edu.get("livestreamNum"))),
            "education_type_dist": _dist(edu.get("eduTypeDist")),
            "teach_freq_dist": _dist(edu.get("teachFreqDist")),
        },
    }
