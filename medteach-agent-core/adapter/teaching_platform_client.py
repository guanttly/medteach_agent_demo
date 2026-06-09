"""教学平台适配器：决定走真实接口还是 Mock。

DEMO_MODE:
- mock   : 全部使用本地演示数据
- real   : 仅调用真实教学平台接口
- hybrid : 优先真实接口，失败自动回退 Mock（推荐展厅使用）
"""
from __future__ import annotations

import os
from typing import Any, Callable

from . import mock_client
from .auth_client import AuthClient


class TeachingPlatformClient:
    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or os.getenv("DEMO_MODE", "hybrid")).lower()
        self.base_url = os.getenv("TEACHING_PLATFORM_BASE_URL", "")
        self._auth = AuthClient()

    # ---- 真实接口（占位，待对接平台时补全）----
    def _real_call(self, endpoint: str) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("缺少必要配置 TEACHING_PLATFORM_BASE_URL。")
        # TODO: 使用 httpx 调用真实平台，附带 self._auth.get_token()。
        raise NotImplementedError(f"真实接口 {endpoint} 尚未对接。")

    def _dispatch(self, endpoint: str, mock_fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if self.mode == "mock":
            return mock_fn()
        try:
            return self._real_call(endpoint)
        except Exception as exc:  # noqa: BLE001 - 演示需吞掉所有真实接口异常
            if self.mode == "real":
                return {
                    "ok": False,
                    "fallback": False,
                    "data": None,
                    "error": {"type": "real_api_failed", "message": str(exc)},
                }
            # hybrid：回退 Mock
            result = mock_fn()
            result["fallback"] = True
            result.setdefault("error", None)
            if result["error"] is None:
                result["error"] = {
                    "type": "real_api_failed",
                    "message": f"真实接口不可用，已切换 Mock 数据：{exc}",
                }
            return result

    # ---- 对外能力 ----
    def get_present_students(self) -> dict[str, Any]:
        return self._dispatch("get_present_students", mock_client.get_present_students)

    def create_exam_draft(self) -> dict[str, Any]:
        return self._dispatch("create_exam_draft", mock_client.create_exam_draft)

    def get_exam_preview(self) -> dict[str, Any]:
        return self._dispatch("get_exam_preview", mock_client.get_exam_preview)

    def publish_exam(self) -> dict[str, Any]:
        return self._dispatch("publish_exam", mock_client.publish_exam)

    def get_exam_progress(self) -> dict[str, Any]:
        return self._dispatch("get_exam_progress", mock_client.get_exam_progress)

    def get_exam_result(self) -> dict[str, Any]:
        return self._dispatch("get_exam_result", mock_client.get_exam_result)

    def recommend_cases(self) -> dict[str, Any]:
        return self._dispatch("recommend_cases", mock_client.recommend_cases)
