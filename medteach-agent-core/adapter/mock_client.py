"""Mock 客户端：从 medteach-agent-core/mock/*.json 读取演示数据。

所有工具脚本在 real 接口不可用或 DEMO_MODE=mock 时回退到这里，
保证展厅演示永不中断。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MOCK_DIR = Path(__file__).resolve().parent.parent / "mock"


def _load(name: str) -> dict[str, Any]:
    path = MOCK_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_present_students() -> dict[str, Any]:
    return _load("students.json")


def create_exam_draft() -> dict[str, Any]:
    return {
        "ok": True,
        "fallback": True,
        "data": {"exam_id": "exam_demo_001", "status": "draft_created_mock"},
        "error": None,
    }


def get_exam_preview() -> dict[str, Any]:
    return _load("exam_preview.json")


def publish_exam() -> dict[str, Any]:
    return {
        "ok": True,
        "fallback": True,
        "data": {
            "exam_id": "exam_demo_001",
            "status": "published_mock",
            "entry_url": "https://demo.giant-shark.local/exam/exam_demo_001",
            "qr_code": "MOCK_QR_EXAM_DEMO_001",
        },
        "error": None,
    }


def get_exam_progress() -> dict[str, Any]:
    return _load("exam_progress_steps.json")


def get_exam_result() -> dict[str, Any]:
    return _load("exam_result.json")


def recommend_cases() -> dict[str, Any]:
    return _load("recommended_cases.json")
