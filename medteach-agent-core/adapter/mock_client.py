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


# ------------------------------------------------------------------ #
# 新业务线 Mock 回退（hybrid 下真实接口不可用时使用，保证演示不中断）
# ------------------------------------------------------------------ #
def _wrap(data: Any) -> dict[str, Any]:
    return {"ok": True, "fallback": True, "data": data, "error": None}


def get_data_board() -> dict[str, Any]:
    return _wrap(
        {
            "exam": {
                "exam_num": 9,
                "paper_num": 11,
                "question_num": 703,
                "exam_avg": 15.9,
                "paper_level_dist": [
                    {"name": "简单", "num": 5},
                    {"name": "中等", "num": 5},
                    {"name": "困难", "num": 1},
                ],
                "question_type_dist": [
                    {"name": "单选", "num": 393},
                    {"name": "多选", "num": 120},
                    {"name": "问答", "num": 96},
                    {"name": "报告书写", "num": 94},
                ],
            },
            "teaching": {
                "education_num": 24,
                "livestream_num": 6,
                "education_type_dist": [
                    {"name": "教学阅片", "num": 12},
                    {"name": "专题讲座", "num": 8},
                    {"name": "疑难病例", "num": 4},
                ],
                "teach_freq_dist": [
                    {"name": "朱达伟", "num": 9},
                    {"name": "李赟", "num": 7},
                    {"name": "刘梦帆", "num": 5},
                ],
            },
        }
    )


def get_student_roster() -> dict[str, Any]:
    data = dict(_load("students.json")["data"])
    data["group_name"] = "学员名册"
    return _wrap(data)


def list_exams() -> dict[str, Any]:
    return _wrap(
        {
            "total": 9,
            "exams": [
                {"exam_id": "demo_ex_1", "name": "胸部 CT 基础诊断测评", "paper_id": "p1",
                 "begin_time": "2026-06-08 14:14", "minutes": 15, "paper_score": 100.0,
                 "pass_score": 60.0, "published": True, "status": "已结束", "creator": "科室管理员"},
                {"exam_id": "demo_ex_2", "name": "腹部 CT 读片测评", "paper_id": "p2",
                 "begin_time": "2026-06-05 09:30", "minutes": 20, "paper_score": 100.0,
                 "pass_score": 60.0, "published": True, "status": "已公布", "creator": "科室管理员"},
                {"exam_id": "demo_ex_3", "name": "头颅 MRI 基础测评", "paper_id": "p3",
                 "begin_time": "2026-06-01 10:00", "minutes": 25, "paper_score": 100.0,
                 "pass_score": 60.0, "published": False, "status": "未开始", "creator": "科室管理员"},
            ],
        }
    )


def list_questions() -> dict[str, Any]:
    return _wrap(
        {
            "total": 703,
            "questions": [
                {"id": "q1", "content": "胸部 CT 肺窗下典型磨玻璃影的表现是？", "type": "单选",
                 "organ": "胸部", "difficulty": "简单", "creator": "朱强"},
                {"id": "q2", "content": "提示肺结节倾向恶性的 CT 征象包括？", "type": "多选",
                 "organ": "胸部", "difficulty": "中等", "creator": "李赟"},
                {"id": "q3", "content": "请书写一份规范的胸部 CT 结构化报告。", "type": "报告书写",
                 "organ": "胸部", "difficulty": "困难", "creator": "刘梦帆"},
            ],
        }
    )


def list_teaching_plans() -> dict[str, Any]:
    return _wrap(
        {
            "total": 24,
            "plans": [
                {"id": "tp1", "subject": "2026年教学阅片：胸部疑难病例", "type": "教学阅片",
                 "education_time": "2026-06-07 08:00", "end_time": "2026-06-07 23:59",
                 "lecturer": "刘梦帆", "host": "朱达伟", "browse_count": 36},
                {"id": "tp2", "subject": "专题讲座：肺结节随访策略", "type": "专题讲座",
                 "education_time": "2026-06-03 14:00", "end_time": "2026-06-03 16:00",
                 "lecturer": "李赟", "host": "朱达伟", "browse_count": 52},
            ],
        }
    )


def build_exam_save_dto(plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """据方案构造 ExamSaveDto 草稿（仅 ALLOW_WRITE 时真实写入使用）。"""
    plan = plan or {}
    return {
        "name": plan.get("exam_name") or "胸部 CT 基础诊断测评",
        "minutes": int(plan.get("duration_minutes") or 15),
        "passScore": float(plan.get("pass_score") or 60),
        "pubTag": 0,
        "readType": 2,
        "studentList": [],
        "teacherList": [],
        "roomList": [],
    }

