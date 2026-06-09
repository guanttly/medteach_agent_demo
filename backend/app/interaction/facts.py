"""事实解析器（Facts Resolver）。

对应方案 7.5「上下文问答」：任何用户问题先走确定性 facts，
facts 命中则直接回答，未命中则明确说明「还在查 / 还没到这一步」，绝不编造。

同时提供给 LLM 的结构化上下文（build_llm_context），替代旧的「只传默认方案」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..session_store import Session


class QAState(str, Enum):
    RESOLVED = "resolved"  # facts 命中，已给出确定答案
    PENDING = "pending"  # 相关 facts 尚未就绪（在查 / 没到这一步）
    UNKNOWN = "unknown"  # 不是可被 facts 回答的上下文问题


@dataclass
class QAResult:
    state: str
    topic: str | None
    text: str

    @property
    def resolved(self) -> bool:
        return self.state == QAState.RESOLVED.value

    @property
    def is_context_question(self) -> bool:
        return self.state in (QAState.RESOLVED.value, QAState.PENDING.value)


# 问题类型 -> 关键词（用于确定性识别上下文问题）
_PATTERNS: list[tuple[str, str]] = [
    ("participants_names", r"哪些人|有谁|谁参加|名单|有哪些学员|都有谁|参加的人"),
    ("participants_count", r"多少人|几个人|几位|人数|多少名|多少个学员"),
    ("exam_topic", r"考什么|考的是什么|什么内容|考试主题|考哪方面|主题是"),
    ("exam_plan", r"几道题|多少题|多长时间|多久|总分|时长|题量|难度|多少分钟"),
    ("current_step", r"到哪一?步|进行到|现在在做|什么进度|到哪了|什么阶段|现在怎么样|做到哪"),
    ("submitted", r"多少人提交|几个人交|交卷|提交了|多少人交|提交情况|答完"),
    ("result_summary", r"平均分|及格率|多少分|考得怎么样|成绩如何|分数情况"),
    ("top_student", r"谁(分数)?最高|第一名|最好的|考得最好|最高分是谁"),
    ("weak_points", r"薄弱|弱点|哪里不行|不足|薄弱点|问题在哪|掌握不好"),
    ("recommendation", r"推荐(了)?什么|复训|练习什么|下一步学|推荐病例|学习建议"),
]


class FactsResolver:
    """把用户上下文问题解析为确定性答案。"""

    def detect_topic(self, text: str) -> str | None:
        for topic, pat in _PATTERNS:
            if re.search(pat, text):
                return topic
        return None

    def looks_like_context_question(self, text: str) -> bool:
        return self.detect_topic(text) is not None

    def answer(self, session: "Session", text: str) -> QAResult:
        topic = self.detect_topic(text)
        if topic is None:
            return QAResult(QAState.UNKNOWN.value, None, "")
        handler = getattr(self, f"_ans_{topic}", None)
        if handler is None:
            return QAResult(QAState.UNKNOWN.value, None, "")
        return handler(session)

    # ------------------------------------------------------------------ #
    # 各类问题的确定性回答
    # ------------------------------------------------------------------ #
    def _ans_participants_names(self, s: "Session") -> QAResult:
        parts = s.students
        if parts and parts.get("students"):
            names = [stu["name"] for stu in parts["students"]]
            depts = sorted({stu.get("department", "") for stu in parts["students"] if stu.get("department")})
            total = parts.get("total", len(names))
            dept_text = "、".join(depts)
            text = (
                f"这场考试一共 {total} 名学员：{'、'.join(names)}。"
                + (f"主要来自{dept_text}。" if dept_text else "")
            )
            return QAResult(QAState.RESOLVED.value, "participants", text)
        plan = s.exam_plan
        count = (plan or {}).get("student_count", 8)
        return QAResult(
            QAState.PENDING.value,
            "participants",
            f"学员名单我还在查，目前方案里预计是 {count} 名现场规培学员。名单一回来，我立刻把具体姓名报给您。",
        )

    def _ans_participants_count(self, s: "Session") -> QAResult:
        parts = s.students
        if parts and parts.get("total"):
            return QAResult(
                QAState.RESOLVED.value,
                "participants",
                f"这场考试一共有 {parts['total']} 名学员参加。",
            )
        plan = s.exam_plan
        if plan and plan.get("student_count"):
            return QAResult(
                QAState.RESOLVED.value,
                "participants",
                f"按现在的方案，预计是 {plan['student_count']} 名现场规培学员参加。",
            )
        return QAResult(
            QAState.PENDING.value,
            "participants",
            "具体人数我正在确认，方案默认是 8 名现场规培学员，确认后我马上告诉您。",
        )

    def _ans_exam_topic(self, s: "Session") -> QAResult:
        plan = s.exam_plan
        if plan and plan.get("topic"):
            return QAResult(
                QAState.RESOLVED.value,
                "exam_plan",
                f"这场考的是{plan.get('exam_name', plan['topic'])}，重点是{plan['topic']}。",
            )
        return QAResult(
            QAState.PENDING.value,
            "exam_plan",
            "考试方案我正在整理，默认是一场胸部 CT 基础诊断考试，稍后给您确认细节。",
        )

    def _ans_exam_plan(self, s: "Session") -> QAResult:
        plan = s.exam_plan
        if plan:
            q = plan.get("question_structure", {})
            total_q = plan.get("question_total") or (
                q.get("single_choice", 0) + q.get("multiple_choice", 0) + q.get("case_analysis", 0)
            )
            text = (
                f"{plan.get('exam_name', '这场考试')}：共 {total_q} 道题，"
                f"时长 {plan.get('duration_minutes', 15)} 分钟，总分 {plan.get('total_score', 100)} 分，"
                f"难度{plan.get('difficulty', '中级')}。"
            )
            return QAResult(QAState.RESOLVED.value, "exam_plan", text)
        return QAResult(
            QAState.PENDING.value,
            "exam_plan",
            "考试方案我还在生成，整理好题量、时长和总分后第一时间给您看。",
        )

    def _ans_current_step(self, s: "Session") -> QAResult:
        jobs = s.active_jobs()
        if jobs:
            job = jobs[0]
            label = job.progress_label or _STEP_LABELS.get(job.current_step or "", "正在推进")
            return QAResult(
                QAState.RESOLVED.value,
                "progress",
                f"我现在正在{label}。您要的其它信息也可以随时问我。",
            )
        # 没有活跃 job：用 demo 状态兜底
        state_label = _STATE_NARRATION.get(s.state)
        if state_label:
            return QAResult(QAState.RESOLVED.value, "progress", state_label)
        return QAResult(
            QAState.PENDING.value,
            "progress",
            "目前还没有正在执行的任务，您可以对我说「安排一场胸部 CT 基础考试」。",
        )

    def _ans_submitted(self, s: "Session") -> QAResult:
        prog = s.progress
        if prog:
            total = int(prog.get("published") or (s.exam_plan or {}).get("student_count") or 8)
            submitted = int(prog.get("submitted") or 0)
            answering = int(prog.get("answering") or 0)
            if submitted >= total and total > 0:
                return QAResult(
                    QAState.RESOLVED.value,
                    "progress",
                    f"{total} 名学员已经全部交卷，我马上汇总分数和薄弱点。",
                )
            return QAResult(
                QAState.RESOLVED.value,
                "progress",
                f"目前 {total} 名学员里已经有 {submitted} 人交卷，还有 {answering} 人在答题。",
            )
        return QAResult(
            QAState.PENDING.value,
            "progress",
            "考试还没开始监控答题，下发之后我会盯着进入、答题和提交三个指标实时告诉您。",
        )

    def _ans_result_summary(self, s: "Session") -> QAResult:
        result = s.result
        if result and result.get("summary"):
            sm = result["summary"]
            return QAResult(
                QAState.RESOLVED.value,
                "result",
                f"这场考试平均分 {sm.get('average')} 分，及格率 {sm.get('pass_rate')}%，"
                f"最高 {sm.get('highest')} 分、最低 {sm.get('lowest')} 分。",
            )
        return QAResult(
            QAState.PENDING.value,
            "result",
            "成绩还在等学员交卷后自动阅卷，出分后我会第一时间把平均分和薄弱点告诉您。",
        )

    def _ans_top_student(self, s: "Session") -> QAResult:
        result = s.result
        if result and result.get("students"):
            top = max(result["students"], key=lambda x: x.get("score", 0))
            return QAResult(
                QAState.RESOLVED.value,
                "result",
                f"这场考得最好的是{top.get('name')}，{top.get('score')} 分，评级{top.get('level', '优秀')}。",
            )
        return QAResult(
            QAState.PENDING.value,
            "result",
            "成绩还没出来，等自动阅卷完成我就能告诉您谁分数最高。",
        )

    def _ans_weak_points(self, s: "Session") -> QAResult:
        result = s.result
        if result and result.get("weak_points"):
            names = [w["name"] for w in result["weak_points"][:3]]
            return QAResult(
                QAState.RESOLVED.value,
                "result",
                f"这次主要薄弱点集中在：{'、'.join(names)}。我可以据此推荐复训病例。",
            )
        return QAResult(
            QAState.PENDING.value,
            "result",
            "薄弱点要等阅卷完成后才能统计，出结果我会马上给您梳理。",
        )

    def _ans_recommendation(self, s: "Session") -> QAResult:
        rec = s.recommendation
        if rec and rec.get("cases"):
            titles = [c["title"] for c in rec["cases"][:3]]
            return QAResult(
                QAState.RESOLVED.value,
                "recommendation",
                f"我推荐了 {len(rec['cases'])} 个复训病例，重点包括：{'、'.join(titles)}。",
            )
        return QAResult(
            QAState.PENDING.value,
            "recommendation",
            "复训病例要等成绩和薄弱点出来后才能匹配，到时我会按薄弱点给您推荐。",
        )

    # ------------------------------------------------------------------ #
    # 给 LLM 的结构化上下文
    # ------------------------------------------------------------------ #
    def build_llm_context(self, s: "Session") -> dict[str, Any]:
        facts: dict[str, Any] = {}
        if s.exam_plan:
            q = s.exam_plan.get("question_structure", {})
            facts["exam_plan"] = {
                "exam_name": s.exam_plan.get("exam_name"),
                "topic": s.exam_plan.get("topic"),
                "student_count": s.exam_plan.get("student_count"),
                "duration_minutes": s.exam_plan.get("duration_minutes"),
                "question_total": s.exam_plan.get("question_total")
                or (q.get("single_choice", 0) + q.get("multiple_choice", 0) + q.get("case_analysis", 0)),
                "total_score": s.exam_plan.get("total_score"),
                "difficulty": s.exam_plan.get("difficulty"),
            }
        if s.students:
            facts["participants"] = {
                "total": s.students.get("total"),
                "names": [stu["name"] for stu in s.students.get("students", [])],
            }
        if s.exam_preview:
            facts["exam_preview"] = {"question_total": s.exam_preview.get("question_total")}
        if s.progress:
            facts["progress"] = {
                "entered": s.progress.get("entered"),
                "answering": s.progress.get("answering"),
                "submitted": s.progress.get("submitted"),
            }
        if s.result:
            facts["result"] = {"summary": s.result.get("summary")}
        if s.recommendation:
            facts["recommendation"] = {"next_goal": s.recommendation.get("next_goal")}

        active = [
            {"job_id": j.job_id, "type": j.type, "status": j.status, "current_step": j.current_step}
            for j in s.active_jobs()
        ]
        return {
            "current_state": s.state,
            "need_confirmation": s.need_user_confirmation,
            "confirmation_type": s.confirmation_type,
            "active_jobs": active,
            "facts": facts,
            "recent_turns": s.recent_turns(),
        }


_STEP_LABELS = {
    "build_exam_plan": "整理考试方案",
    "query_participants": "查现场学员名单",
    "create_exam_draft": "创建考试草稿、匹配题库",
    "fetch_exam_preview": "生成试卷预览",
    "publish_exam": "下发考试、生成入口",
    "monitor_progress": "盯答题进度",
    "grade_exam": "汇总分数和薄弱点",
    "recommend_cases": "匹配复训病例",
}

_STATE_NARRATION = {
    "WAITING_PLAN_CONFIRM": "考试方案我已经准备好了，正等您确认是否按这个方案准备。",
    "WAITING_PUBLISH_CONFIRM": "试卷预览已经就绪，正等您确认是否下发考试。",
    "MONITORING_PROGRESS": "我正在盯答题进度，按进入、答题、提交三个指标同步给您。",
    "GRADING": "学员已经提交，我正在自动阅卷、汇总分数。",
    "REPORT_READY": "成绩分析已经出来了，您可以问我平均分、薄弱点或谁分数最高。",
    "DONE": "这一轮考试安排已经完整走完，您可以再安排一场或问我刚才的结果。",
}


facts_resolver = FactsResolver()
