"""演示状态机常量与工作流定义。"""
from __future__ import annotations

from enum import Enum


class DemoState(str, Enum):
    IDLE = "IDLE"
    INTENT_RECOGNIZED = "INTENT_RECOGNIZED"
    PLAN_PROPOSED = "PLAN_PROPOSED"
    WAITING_PLAN_CONFIRM = "WAITING_PLAN_CONFIRM"
    CREATING_EXAM = "CREATING_EXAM"
    EXAM_PREVIEW_READY = "EXAM_PREVIEW_READY"
    WAITING_PUBLISH_CONFIRM = "WAITING_PUBLISH_CONFIRM"
    PUBLISHING_EXAM = "PUBLISHING_EXAM"
    EXAM_PUBLISHED = "EXAM_PUBLISHED"
    MONITORING_PROGRESS = "MONITORING_PROGRESS"
    GRADING = "GRADING"
    REPORT_READY = "REPORT_READY"
    RECOMMENDING = "RECOMMENDING"
    DONE = "DONE"


class SharkState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WORKING = "working"
    WAITING_CONFIRM = "waiting_confirm"
    SUCCESS = "success"
    SOFT_WARNING = "soft_warning"


# 大屏固定展示的 10 个工作流步骤
WORKFLOW_STEPS: list[tuple[str, str]] = [
    ("intent", "识别教学任务"),
    ("plan", "生成考试方案"),
    ("confirm_plan", "等待讲师确认"),
    ("students", "查询学员列表"),
    ("create", "创建考试草稿"),
    ("preview", "展示试卷预览"),
    ("publish", "下发考试"),
    ("progress", "监控答题进度"),
    ("grading", "自动阅卷分析"),
    ("recommend", "推荐学习病例"),
]


def initial_workflow() -> list[dict]:
    return [{"id": sid, "label": label, "status": "pending"} for sid, label in WORKFLOW_STEPS]
