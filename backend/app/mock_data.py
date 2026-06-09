"""从 medteach-agent-core/mock 加载演示数据（单一数据源）。"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .config import settings

MOCK_DIR = settings.CLAUDE_CORE_DIR / "mock"


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    path = MOCK_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def students() -> dict[str, Any]:
    return _load("students.json")["data"]


def exam_preview() -> dict[str, Any]:
    return _load("exam_preview.json")["data"]


def exam_progress_steps() -> list[dict[str, Any]]:
    return _load("exam_progress_steps.json")["data"]["steps"]


def exam_result() -> dict[str, Any]:
    return _load("exam_result.json")["data"]


def recommended_cases() -> dict[str, Any]:
    return _load("recommended_cases.json")["data"]


def exam_plan_default() -> dict[str, Any]:
    """根据 skill 默认值生成考试方案。"""
    defaults_path = settings.CLAUDE_CORE_DIR / ".claude" / "skills" / "arrange_exam" / "demo_defaults.json"
    with defaults_path.open("r", encoding="utf-8") as f:
        d = json.load(f)
    q = d["question_structure"]
    return {
        "exam_name": d["exam_name"],
        "topic": d["topic"],
        "student_group": d["student_group"],
        "student_count": d["student_count"],
        "duration_minutes": d["duration_minutes"],
        "difficulty": d["difficulty"],
        "total_score": d["total_score"],
        "grading": d["grading"],
        "question_structure": q,
        "question_total": q["single_choice"] + q["multiple_choice"] + q["case_analysis"],
    }
