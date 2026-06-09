"""固定账号登录 / Token 管理（真实教学平台）。

MVP 阶段为占位实现：从环境变量读取凭据，真实接口接入时在此补全登录逻辑。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass
class Token:
    value: str
    expires_at: float

    @property
    def valid(self) -> bool:
        return bool(self.value) and time.time() < self.expires_at


class AuthClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("TEACHING_PLATFORM_BASE_URL", "")
        self.username = os.getenv("TEACHING_PLATFORM_USERNAME", "")
        self.password = os.getenv("TEACHING_PLATFORM_PASSWORD", "")
        self._token: Token | None = None

    def get_token(self) -> str:
        """返回有效 token。真实接入时在此调用平台登录接口。"""
        if self._token and self._token.valid:
            return self._token.value
        if not self.base_url:
            raise RuntimeError("缺少必要配置 TEACHING_PLATFORM_BASE_URL。")
        # TODO: 接入真实平台登录接口，换取 token。
        self._token = Token(value="REAL_TOKEN_PLACEHOLDER", expires_at=time.time() + 1800)
        return self._token.value
