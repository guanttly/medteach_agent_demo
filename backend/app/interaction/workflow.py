"""后台工作流引擎（Workflow Engine）。

对应方案第 8 章：以 job 为单位运行「安排考试」黄金路径，
每步更新 job、发 workflow/domain 事件、写 facts、慢任务 heartbeat 安抚，
确认点改为 waiting_user（不占用执行线程），并支持 cancel / pause / replan。

任何步骤都不阻塞前台 Conversation Gateway：Gateway 只负责接话，
job 通过 asyncio 信号在确认点挂起，由 Gateway 在收到确认/下发后唤醒。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .. import mock_data
from ..agent_brain import agent_brain
from ..config import settings
from ..constants import DemoState, SharkState
from .events import event_bus
from .models import Job, JobStatus, Priority, next_job_id
from .narration import narration
from .presenter import presenter
from .speaker import speaker

if TYPE_CHECKING:
    from ..session_store import Session

logger = logging.getLogger("interaction.workflow")


# job step -> 旧前端大屏工作流 step id
_STEP_TO_LEGACY = {
    "recognize_intent": "intent",
    "build_exam_plan": "plan",
    "wait_plan_confirm": "confirm_plan",
    "query_participants": "students",
    "create_exam_draft": "create",
    "fetch_exam_preview": "preview",
    "publish_exam": "publish",
    "monitor_progress": "progress",
    "grade_exam": "grading",
    "recommend_cases": "recommend",
}

# 慢任务 heartbeat 安抚句（按 step 轮播，避免重复读同一句）
_HEARTBEAT = {
    "build_exam_plan": [
        "我已经识别到考试主题，正在整理题量、时长和评分方案。",
        "方案细节我还在打磨，马上把单选、多选和病例分析的配比定下来。",
        "评分标准我也一并准备，稍等就给您完整方案。",
        "我正在按胸部 CT 基础诊断的重点来配题，让难度更贴合规培学员。",
        "方案快好了，我再核对一下时长和总分。",
    ],
    "create_exam_draft": [
        "题库匹配还在进行，我会先把草稿状态同步到大屏。",
        "我正在从胸部 CT 题库里挑合适的题目组卷。",
        "草稿快建好了，我再确认一下题目顺序。",
    ],
}


class _JobSignals:
    def __init__(self) -> None:
        self.confirm = asyncio.Event()
        self.cancel = asyncio.Event()
        self.resume = asyncio.Event()


class WorkflowEngine:
    def __init__(self) -> None:
        self._signals: dict[str, _JobSignals] = {}

    # ------------------------------------------------------------------ #
    # job 生命周期
    # ------------------------------------------------------------------ #
    def create_job(self, s: "Session", job_type: str, turn_id: str | None = None) -> Job:
        job = Job(
            job_id=next_job_id(),
            session_id=s.session_id,
            type=job_type,
            status=JobStatus.QUEUED.value,
            related_turn_id=turn_id,
        )
        s.jobs[job.job_id] = job
        self._signals[job.job_id] = _JobSignals()
        return job

    def signals(self, job_id: str) -> _JobSignals | None:
        return self._signals.get(job_id)

    async def _set_step(self, s: "Session", job: Job, step: str, *, percent: int, label: str) -> None:
        job.current_step = step
        job.set_progress(percent, label)
        job.status = JobStatus.RUNNING.value
        legacy = _STEP_TO_LEGACY.get(step)
        if legacy:
            await presenter.set_step(s, legacy, "running")
        await presenter.emit_job(s, job)
        job.mark_user_visible()

    async def _complete_step(self, s: "Session", job: Job, step: str) -> None:
        legacy = _STEP_TO_LEGACY.get(step)
        if legacy:
            await presenter.set_step(s, legacy, "completed")
        await presenter.emit_job(s, job)

    def _check_interrupt(self, s: "Session", job: Job) -> str | None:
        if job.cancel_requested:
            return "cancel"
        if job.pause_requested:
            return "pause"
        return None

    # ------------------------------------------------------------------ #
    # 主入口：运行 arrange_exam job
    # ------------------------------------------------------------------ #
    async def run_arrange_exam(self, s: "Session", job: Job) -> None:
        try:
            s.busy = True
            await self._step_recognize_intent(s, job)
            if self._aborted(s, job):
                return
            await self._step_build_plan(s, job)
            if self._aborted(s, job):
                return

            # 等待方案确认
            ok = await self._wait_confirmation(s, job, "confirm_plan", "wait_plan_confirm")
            if not ok:
                return

            await self._step_query_participants(s, job)
            if self._aborted(s, job):
                return
            await self._step_create_draft(s, job)
            if self._aborted(s, job):
                return
            await self._step_fetch_preview(s, job)
            if self._aborted(s, job):
                return

            # 等待下发确认
            ok = await self._wait_confirmation(s, job, "confirm_publish", "wait_publish_confirm")
            if not ok:
                return

            await self._step_publish(s, job)
            if self._aborted(s, job):
                return
            await self._step_monitor_progress(s, job)
            if self._aborted(s, job):
                return
            await self._step_grade(s, job)
            if self._aborted(s, job):
                return
            await self._step_recommend(s, job)

            job.status = JobStatus.SUCCEEDED.value
            await presenter.emit_job(s, job)
        except Exception as exc:  # noqa: BLE001
            logger.exception("arrange_exam job failed: %s", exc)
            job.status = JobStatus.FAILED.value
            job.error = str(exc)
            await presenter.emit_job(s, job)
            await narration.enqueue(
                s,
                kind="error",
                summary_key=f"error:{job.job_id}",
                priority=Priority.HIGH.value,
                job_id=job.job_id,
                requires_verbatim=True,
                payload={"text": "刚才这一步我没能顺利完成，我先停在这里，您可以让我重试或换个方案。"},
            )
            await narration.flush(s, job_id=job.job_id, force=True)
        finally:
            if not s.active_jobs():
                s.busy = False
            await presenter.emit_state(s)
            self._signals.pop(job.job_id, None)

    def _aborted(self, s: "Session", job: Job) -> bool:
        return job.status in (JobStatus.CANCELLED.value, JobStatus.FAILED.value, JobStatus.PAUSED.value)

    # ------------------------------------------------------------------ #
    # 各步骤
    # ------------------------------------------------------------------ #
    async def _step_recognize_intent(self, s: "Session", job: Job) -> None:
        s.state = DemoState.INTENT_RECOGNIZED.value
        await presenter.emit_state(s)
        await self._set_step(s, job, "recognize_intent", percent=8, label="识别教学任务")
        await asyncio.sleep(min(settings.STEP_DELAY, 0.6))
        await self._complete_step(s, job, "recognize_intent")
        await presenter.emit_screen_event(
            s,
            {"type": "intent_recognized", "title": "已识别教学任务",
             "message": "安排一场胸部 CT 基础诊断考试", "status": "completed"},
        )

    async def _step_build_plan(self, s: "Session", job: Job) -> None:
        await self._set_step(s, job, "build_exam_plan", percent=18, label="生成考试方案")
        plan = mock_data.exam_plan_default()
        s.exam_plan = plan
        await presenter.emit_domain(
            s, fact_path="exam_plan", legacy_type="exam_plan_update", legacy_data={"exam_plan": plan}
        )
        await asyncio.sleep(min(settings.STEP_DELAY, 0.6))
        await self._complete_step(s, job, "build_exam_plan")

    async def _step_query_participants(self, s: "Session", job: Job) -> None:
        s.state = DemoState.CREATING_EXAM.value
        await presenter.emit_state(s)
        await self._set_step(s, job, "query_participants", percent=38, label="正在查询现场学员")
        await asyncio.sleep(settings.STEP_DELAY)
        students = mock_data.students()
        s.students = students
        await presenter.emit_domain(
            s, fact_path="participants", legacy_type="students_update",
            legacy_data={"students": students},
        )
        await self._complete_step(s, job, "query_participants")
        await narration.enqueue(
            s, kind="result", summary_key="participants", priority=Priority.NORMAL.value,
            fact_path="participants", fact_version=s.fact_version("participants"), job_id=job.job_id,
        )

    async def _step_create_draft(self, s: "Session", job: Job) -> None:
        await self._set_step(s, job, "create_exam_draft", percent=55, label="创建考试草稿")
        await self._run_with_heartbeat(s, job, asyncio.sleep(settings.STEP_DELAY), "create_exam_draft")
        s.bump_fact("exam_draft")
        await self._complete_step(s, job, "create_exam_draft")
        await presenter.emit_screen_event(
            s,
            {"type": "tool_call_succeeded", "title": "考试草稿已创建",
             "message": "exam_demo_001", "status": "completed"},
        )
        await narration.enqueue(
            s, kind="result", summary_key="exam_draft", priority=Priority.NORMAL.value,
            fact_path="exam_draft", fact_version=s.fact_version("exam_draft"), job_id=job.job_id,
        )

    async def _step_fetch_preview(self, s: "Session", job: Job) -> None:
        await self._set_step(s, job, "fetch_exam_preview", percent=68, label="生成试卷预览")
        await asyncio.sleep(min(settings.STEP_DELAY, 0.7))
        preview = mock_data.exam_preview()
        s.exam_preview = preview
        await presenter.emit_domain(
            s, fact_path="exam_preview", legacy_type="exam_preview_update",
            legacy_data={"exam_preview": preview},
        )
        await self._complete_step(s, job, "fetch_exam_preview")
        await narration.enqueue(
            s, kind="result", summary_key="exam_preview", priority=Priority.NORMAL.value,
            fact_path="exam_preview", fact_version=s.fact_version("exam_preview"), job_id=job.job_id,
        )

    async def _step_publish(self, s: "Session", job: Job) -> None:
        s.state = DemoState.PUBLISHING_EXAM.value
        await presenter.emit_state(s)
        await self._set_step(s, job, "publish_exam", percent=78, label="下发考试")
        await asyncio.sleep(min(settings.STEP_DELAY, 0.7))
        s.publish_info = {
            "exam_id": "exam_demo_001",
            "entry_url": "https://demo.giant-shark.local/exam/exam_demo_001",
            "published_at": time.time(),
        }
        s.bump_fact("publish_info")
        s.state = DemoState.EXAM_PUBLISHED.value
        await presenter.emit_state(s)
        await self._complete_step(s, job, "publish_exam")
        await presenter.emit_screen_event(
            s,
            {"type": "exam_published", "title": "考试已下发",
             "message": "已开启答题入口，二维码已生成。", "status": "completed",
             "payload": {"entry_url": s.publish_info["entry_url"]}},
        )
        count = (s.exam_plan or {}).get("student_count", 8)
        await speaker.say(
            s, f"考试已经下发，{count} 名学员都能扫码进入。我开始盯答题进度，有变化随时同步给您。",
            priority=Priority.NORMAL.value, job_id=job.job_id, source="workflow",
        )

    async def _step_monitor_progress(self, s: "Session", job: Job) -> None:
        s.state = DemoState.MONITORING_PROGRESS.value
        await presenter.emit_state(s)
        await self._set_step(s, job, "monitor_progress", percent=85, label="监控答题进度")
        announced_partial = False
        steps = mock_data.exam_progress_steps()
        for snap in steps:
            if self._check_interrupt(s, job):
                return
            s.progress = snap
            ver = await presenter.emit_domain(
                s, fact_path="progress", legacy_type="exam_progress_update",
                legacy_data={"progress": snap},
            )
            job.mark_user_visible()
            await narration.enqueue(
                s, kind="progress", summary_key="exam_progress", priority=Priority.NORMAL.value,
                fact_path="progress", fact_version=ver, job_id=job.job_id,
            )
            submitted = int(snap.get("submitted") or 0)
            answering = int(snap.get("answering") or 0)
            if not announced_partial and submitted > 0 and answering > 0:
                announced_partial = True
                await narration.flush(s, focus_topic="progress", job_id=job.job_id, force=True)
            await asyncio.sleep(settings.PROGRESS_DELAY)
        await self._complete_step(s, job, "monitor_progress")

    async def _step_grade(self, s: "Session", job: Job) -> None:
        s.state = DemoState.GRADING.value
        await presenter.emit_state(s)
        await self._set_step(s, job, "grade_exam", percent=92, label="自动阅卷分析")
        # 结果到达 -> 之前的过程类进度过期
        self._expire_pending(s, "exam_progress")
        await self._run_with_heartbeat(s, job, asyncio.sleep(settings.PROGRESS_DELAY), "build_exam_plan")
        result = mock_data.exam_result()
        s.result = result
        ver = await presenter.emit_domain(
            s, fact_path="result", legacy_type="exam_result_update", legacy_data={"result": result}
        )
        await self._complete_step(s, job, "grade_exam")
        s.state = DemoState.REPORT_READY.value
        await presenter.emit_state(s)
        sm = result["summary"]
        await presenter.emit_screen_event(
            s,
            {"type": "report_ready", "title": "阅卷分析已完成",
             "message": f"平均分 {sm['average']}，及格率 {sm['pass_rate']}%", "status": "completed"},
        )
        await narration.enqueue(
            s, kind="result", summary_key="exam_result", priority=Priority.HIGH.value,
            fact_path="result", fact_version=ver, job_id=job.job_id,
        )

    async def _step_recommend(self, s: "Session", job: Job) -> None:
        s.state = DemoState.RECOMMENDING.value
        await presenter.emit_state(s)
        await self._set_step(s, job, "recommend_cases", percent=98, label="推荐学习病例")
        await asyncio.sleep(min(settings.STEP_DELAY, 0.7))
        rec = mock_data.recommended_cases()
        s.recommendation = rec
        ver = await presenter.emit_domain(
            s, fact_path="recommendation", legacy_type="case_recommendation_update",
            legacy_data={"recommendation": rec},
        )
        await self._complete_step(s, job, "recommend_cases")
        s.state = DemoState.DONE.value
        s.core_status = "idle"
        await presenter.emit_state(s)
        await narration.enqueue(
            s, kind="result", summary_key="recommendation", priority=Priority.HIGH.value,
            fact_path="recommendation", fact_version=ver, job_id=job.job_id,
        )
        # 收尾：把阅卷 + 推荐合并成一段总结播报
        await narration.flush(s, focus_topic="result", job_id=job.job_id, force=True)
        await presenter.set_shark(s, SharkState.SUCCESS)
        await presenter.emit_screen_event(
            s,
            {"type": "demo_done", "title": "演示完成",
             "message": "考试安排闭环已完整演示。", "status": "completed"},
        )

    # ------------------------------------------------------------------ #
    # 确认点：挂起 job，不占用执行线程
    # ------------------------------------------------------------------ #
    async def _wait_confirmation(
        self, s: "Session", job: Job, ctype: str, step: str
    ) -> bool:
        await self._set_step(s, job, step, percent=job.progress_percent, label="等待讲师确认")
        job.status = JobStatus.WAITING_USER.value
        job.waiting_confirmation_type = ctype
        s.set_confirmation(True, ctype)
        if ctype == "confirm_plan":
            s.state = DemoState.WAITING_PLAN_CONFIRM.value
        else:
            s.state = DemoState.EXAM_PREVIEW_READY.value
        await presenter.emit_state(s)
        await presenter.emit_job(s, job)
        await presenter.set_shark(s, SharkState.WAITING_CONFIRM)

        # 确认请求口播（verbatim）：优先用执行层话术，慢则 heartbeat 兜底
        await self._speak_confirmation_request(s, job, ctype)

        sig = self._signals.get(job.job_id)
        if sig is None:
            return False
        confirm_task = asyncio.create_task(sig.confirm.wait())
        cancel_task = asyncio.create_task(sig.cancel.wait())
        done, pending = await asyncio.wait(
            {confirm_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        sig.confirm.clear()

        if job.cancel_requested:
            job.status = JobStatus.CANCELLED.value
            await presenter.emit_job(s, job)
            return False
        # 确认通过
        job.status = JobStatus.RUNNING.value
        job.waiting_confirmation_type = None
        s.set_confirmation(False, None)
        legacy = _STEP_TO_LEGACY.get(step)
        if legacy:
            await presenter.set_step(s, legacy, "completed")
        return True

    async def _speak_confirmation_request(self, s: "Session", job: Job, ctype: str) -> None:
        if ctype == "confirm_plan":
            plan = s.exam_plan or {}
            q = plan.get("question_structure", {})
            total_q = plan.get("question_total") or (
                q.get("single_choice", 0) + q.get("multiple_choice", 0) + q.get("case_analysis", 0)
            )
            fallback = (
                f"我已经把{plan.get('exam_name', '胸部 CT 基础诊断考试')}的方案准备好了："
                f"{plan.get('student_count', 8)} 名学员、{plan.get('duration_minutes', 15)} 分钟、"
                f"{total_q} 道题、总分 {plan.get('total_score', 100)} 分。您看可以的话，我就按这个方案准备。"
            )
            text = await self._arrange_text_with_heartbeat(s, job, fallback)
        else:
            q_total = (s.exam_plan or {}).get("question_total", 17)
            text = f"试卷我已经生成好了，一共 {q_total} 道题。您确认后，我就可以下发考试。"
        await speaker.say(
            s, text, priority=Priority.HIGH.value, job_id=job.job_id,
            source="confirmation", interruptible=False, shark_state=SharkState.WAITING_CONFIRM,
        )

    async def _arrange_text_with_heartbeat(self, s: "Session", job: Job, fallback: str) -> str:
        """语音关键路径话术生成。

        外部 LLM 只能使用极短预算；超时立即走确定性模板。Claude CLI 这类秒级调用
        不进入语音首响路径，避免用户听到多轮 heartbeat 才等来确认请求。
        """
        budget = max(0.0, settings.VOICE_LLM_BUDGET_SECONDS)
        if (
            not settings.chat_llm_configured
            or budget <= 0
            or settings.LLM_PROVIDER == "claude_cli"
        ):
            return fallback

        task = asyncio.create_task(
            agent_brain.generate_arrange_text(
                message=s.conversation.get("last_user_text") or "安排考试",
                state=s.state,
                default_plan=s.exam_plan,
            )
        )
        try:
            text = await asyncio.wait_for(task, timeout=budget)
            if text and text.strip():
                return text.strip()
        except asyncio.TimeoutError:
            task.cancel()
            logger.info("arrange confirmation text hit voice budget %.2fs; using fallback", budget)
        except Exception:  # noqa: BLE001
            logger.warning("arrange confirmation text fallback", exc_info=True)
        return fallback

    # ------------------------------------------------------------------ #
    # 慢任务 heartbeat
    # ------------------------------------------------------------------ #
    async def _run_with_heartbeat(self, s: "Session", job: Job, coro, step_key: str) -> None:
        task = asyncio.ensure_future(coro)
        tick = 0
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.5)
            except asyncio.TimeoutError:
                await self._heartbeat(s, job, step_key, tick)
                tick += 1
            except Exception:  # noqa: BLE001
                break

    async def _heartbeat(self, s: "Session", job: Job, step_key: str, tick: int) -> None:
        lines = _HEARTBEAT.get(step_key) or _HEARTBEAT["build_exam_plan"]
        text = lines[tick % len(lines)]
        job.mark_user_visible()
        await narration.enqueue(
            s, kind="progress", summary_key=f"heartbeat:{job.job_id}", priority=Priority.NORMAL.value,
            job_id=job.job_id, payload={"text": text},
        )
        await narration.flush(s, job_id=job.job_id, force=True)

    def _expire_pending(self, s: "Session", summary_key: str) -> None:
        now = time.time()
        for it in s.pending_narration:
            if it.summary_key == summary_key and not it.requires_verbatim:
                it.expires_at = now - 1

    # ------------------------------------------------------------------ #
    # 导演台：模拟全部提交（跳过进度等待）
    # ------------------------------------------------------------------ #
    async def simulate_submit(self, s: "Session", job: Job) -> None:
        steps = mock_data.exam_progress_steps()
        s.progress = steps[-1]
        await presenter.emit_domain(
            s, fact_path="progress", legacy_type="exam_progress_update",
            legacy_data={"progress": steps[-1]},
        )
        await presenter.set_step(s, "progress", "completed")
        await self._step_grade(s, job)
        await self._step_recommend(s, job)
        job.status = JobStatus.SUCCEEDED.value
        await presenter.emit_job(s, job)


workflow_engine = WorkflowEngine()
