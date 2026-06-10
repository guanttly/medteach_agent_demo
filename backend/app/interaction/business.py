"""业务查询模块（语音业务 / 工具按钮 → 真实工具箱取数 → 大屏面板 + 口播话术）。

把「数据看板 / 学员名册 / 考试列表 / 成绩分析 / 题库 / 病例推荐 / 教学计划」
七大只读业务统一定义：意图识别、真实工具箱调用、大屏面板事件路由、确定性口播话术。

这一层让 interaction 网关在「问答」时真正调用 medteach-agent-core 的真实工具箱
（platform_bridge → TeachingPlatformClient），而不是只用本地确定性模板兜底。
"""
from __future__ import annotations

import re
from typing import Any

from .. import platform_bridge

# 业务查询意图集合（只读，随时可问）。
QUERY_INTENTS = {
    "data_board",
    "list_students",
    "list_exams",
    "show_grading",
    "list_questions",
    "recommend_cases",
    "list_teaching",
}

# 与「安排考试」金线 facts 重叠的业务意图：金线进行中时应回答「这一场」而非平台全局。
FACTS_BACKED_INTENTS = {"list_students", "list_exams", "show_grading", "recommend_cases"}

# 意图 → 调用规格（真实工具箱方法 + 大屏面板 + 就绪事件名）。
_DISPATCH: dict[str, dict[str, Any]] = {
    "data_board": {
        "title": "教学数据看板", "skill": "data_board Skill",
        "ready_event": "data_board_ready", "call": platform_bridge.get_data_board, "panel": None,
    },
    "list_students": {
        "title": "现场学员名册", "skill": "student_management Skill",
        "ready_event": "students_ready", "call": platform_bridge.get_present_students, "panel": "students",
    },
    "list_exams": {
        "title": "考试列表", "skill": "exam_monitoring Skill",
        "ready_event": "exam_list_ready", "call": platform_bridge.list_exams, "panel": None,
    },
    "show_grading": {
        "title": "阅卷成绩分析", "skill": "exam_grading Skill",
        "ready_event": "report_ready", "call": platform_bridge.get_exam_result, "panel": "result",
    },
    "list_questions": {
        "title": "题库", "skill": "question_bank Skill",
        "ready_event": "question_bank_ready", "call": platform_bridge.list_questions, "panel": None,
    },
    "recommend_cases": {
        "title": "复训病例推荐", "skill": "case_recommend Skill",
        "ready_event": "recommendation_ready", "call": platform_bridge.recommend_cases, "panel": "recommendation",
    },
    "list_teaching": {
        "title": "教学计划", "skill": "teaching_plan Skill",
        "ready_event": "teaching_plan_ready", "call": platform_bridge.list_teaching_plans, "panel": None,
    },
}


def spec(intent: str) -> dict[str, Any] | None:
    return _DISPATCH.get(intent)


def title(intent: str) -> str:
    return (_DISPATCH.get(intent) or {}).get("title", "这个模块")


def detect_intent(text: str) -> str | None:
    """用关键字把语音/指令匹配到业务查询模块（确定性兜底路由，无需大模型）。"""
    rules = (
        ("show_grading", r"成绩|阅卷|分数|平均分|及格率|通过率|薄弱|考得怎么样|考得如何"),
        ("recommend_cases", r"推荐病例|复训|训练病例|推荐.*病例|练什么|下一阶段"),
        ("list_questions", r"题库|多少道题|有哪些题|题目列表|题型"),
        ("list_teaching", r"教学计划|教学安排|教学阅片|排课|教学日程|谁来讲"),
        ("data_board", r"看板|数据概览|整体情况|总览|运营|多少场考试|多少套试卷|多少道题目"),
        ("list_students", r"现场.*学员|在科|学员名单|学员名册|有哪些学员|多少名?学员|有多少人"),
        ("list_exams", r"考试列表|有哪些考试|哪些考试|监考|哪些场考试"),
    )
    for intent, pattern in rules:
        if re.search(pattern, text):
            return intent
    return None


# ---- 各模块确定性口播话术（基于真实数据，低延迟、稳定可朗读） ---- #
def _fb(fallback: bool) -> str:
    return "（演示数据）" if fallback else ""


def _summary_data_board(data: dict[str, Any], fallback: bool) -> str:
    exam = (data or {}).get("exam", {})
    teaching = (data or {}).get("teaching", {})
    en = int(exam.get("exam_num") or 0)
    pn = int(exam.get("paper_num") or 0)
    qn = int(exam.get("question_num") or 0)
    avg = exam.get("exam_avg")
    edn = int(teaching.get("education_num") or 0)
    avg_txt = f"，考试平均分约 {avg} 分" if avg else ""
    edu_txt = f"；教学方面累计 {edn} 场活动" if edn else ""
    return (
        f"{_fb(fallback)}目前平台上一共有 {en} 场考试、{pn} 套试卷、{qn} 道题目{avg_txt}{edu_txt}。"
        "您可以让我直接安排一场新的考试。"
    )


def _summary_students(data: dict[str, Any], fallback: bool) -> str:
    total = int(data.get("total") or len(data.get("students") or []))
    students = data.get("students") or []
    names = "、".join(str(x.get("name")) for x in students[:3] if x.get("name"))
    group = data.get("group_name") or "现场学员"
    sample = f"，比如{names}等" if names else ""
    return (
        f"{_fb(fallback)}{group}一共 {total} 位{sample}。"
        "需要的话，我可以直接给他们安排一场胸部 CT 基础考试。"
    )


def _summary_exams(data: dict[str, Any], fallback: bool) -> str:
    total = int(data.get("total") or len(data.get("exams") or []))
    exams = data.get("exams") or []
    if not exams:
        return f"{_fb(fallback)}目前还没有已创建的考试，要不要我现在安排一场？"
    first = exams[0]
    name = first.get("name") or "未命名考试"
    minutes = first.get("minutes") or 0
    status = first.get("status") or ""
    return (
        f"{_fb(fallback)}最近一共有 {total} 场考试，最新的是「{name}」，"
        f"时长 {minutes} 分钟、当前状态{status}。要不要看某一场的答题进度或成绩？"
    )


def _summary_grading(data: dict[str, Any], fallback: bool) -> str:
    summary = data.get("summary") or {}
    weak = data.get("weak_points") or []
    name = data.get("exam_name") or "这场考试"
    avg = summary.get("average", 0)
    pass_rate = summary.get("pass_rate", 0)
    weak_txt = "、".join(str(w.get("name")) for w in weak[:3] if w.get("name"))
    weak_part = f"；薄弱点主要集中在{weak_txt}" if weak_txt else ""
    return (
        f"{_fb(fallback)}「{name}」平均分 {avg} 分、及格率 {pass_rate}%{weak_part}。"
        "我可以据此为学员推荐复训病例。"
    )


def _summary_questions(data: dict[str, Any], fallback: bool) -> str:
    total = int(data.get("total") or len(data.get("questions") or []))
    questions = data.get("questions") or []
    types: list[str] = []
    for q in questions:
        t = q.get("type")
        if t and t != "—" and t not in types:
            types.append(t)
    type_txt = "、".join(types[:4]) if types else "多种题型"
    return (
        f"{_fb(fallback)}题库里目前一共有 {total} 道题，涵盖{type_txt}等题型。"
        "组卷时我会从这里挑选合适的题目。"
    )


def _summary_recommend(data: dict[str, Any], fallback: bool) -> str:
    cases = data.get("cases") or []
    next_goal = data.get("next_goal") or ""
    if not cases:
        return f"{_fb(fallback)}{next_goal}".strip() or f"{_fb(fallback)}暂时没有匹配到合适的复训病例。"
    first = cases[0].get("title") or "典型病例"
    return (
        f"{_fb(fallback)}针对薄弱点，我推荐了 {len(cases)} 个复训病例，"
        f"比如「{first}」。{next_goal}"
    )


def _summary_teaching(data: dict[str, Any], fallback: bool) -> str:
    total = int(data.get("total") or len(data.get("plans") or []))
    plans = data.get("plans") or []
    if not plans:
        return f"{_fb(fallback)}近期暂时没有教学安排。"
    first = plans[0]
    subject = first.get("subject") or "教学安排"
    when = first.get("education_time") or ""
    lecturer = first.get("lecturer") or ""
    who = f"，由{lecturer}主讲" if lecturer and lecturer != "—" else ""
    return (
        f"{_fb(fallback)}近期教学安排一共有 {total} 项，最新的是「{subject}」"
        f"（{when}）{who}。"
    )


_SUMMARY = {
    "data_board": _summary_data_board,
    "list_students": _summary_students,
    "list_exams": _summary_exams,
    "show_grading": _summary_grading,
    "list_questions": _summary_questions,
    "recommend_cases": _summary_recommend,
    "list_teaching": _summary_teaching,
}


def summarize(intent: str, data: Any, fallback: bool) -> str:
    fn = _SUMMARY.get(intent)
    if fn is None or not isinstance(data, dict):
        return f"{title(intent)}这边暂时没取到数据，我先用演示数据顶上，咱们继续。"
    try:
        return fn(data, fallback)
    except Exception:  # noqa: BLE001 - 话术兜底，任何字段异常都不应中断口播
        return f"{_fb(fallback)}{title(intent)}的数据我已经拿到，详情请看大屏。"
