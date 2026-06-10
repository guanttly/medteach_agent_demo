"""固定账号登录 / Token 管理（真实教学平台）。

登录流程（已对接 jushacloud 教学平台）：
1. `GET  {base}/auth-server/open/getKeys` → base64 DER RSA 公钥。
2. 用公钥对密码做 PKCS#1 v1.5 加密（见 rsa_util）。
3. `POST {base}/auth-server/open/login` body={"username":..,"password":<密文>}
   → ResultBean，data 即 token（形如 `login_tokens:<uid>:<uuid>`）。
4. 后续业务请求头携带 `Authorization: <token>` 与 `platId: <platId>`。

凭据从环境变量读取（backend/.env）：
- TEACHING_PLATFORM_BASE_URL（缺省内置演示平台地址）
- TEACHING_PLATFORM_USERNAME / TEACHING_PLATFORM_PASSWORD
- TEACHING_PLATFORM_PLAT_ID（缺省 0）

未配置用户名/密码时 `configured()` 返回 False，工具箱会在 hybrid 模式下回退 Mock，
保证展厅演示永不中断。
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from .rsa_util import rsa_encrypt_base64

DEFAULT_BASE_URL = "https://platform.jushacloud.com:9050/teach-prod-api"


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Token:
    value: str
    expires_at: float

    @property
    def valid(self) -> bool:
        return bool(self.value) and time.time() < self.expires_at


class AuthClient:
    def __init__(self) -> None:
        self.base_url = (
            os.getenv("TEACHING_PLATFORM_BASE_URL") or DEFAULT_BASE_URL
        ).strip().rstrip("/")
        self.username = os.getenv("TEACHING_PLATFORM_USERNAME", "").strip()
        self.password = os.getenv("TEACHING_PLATFORM_PASSWORD", "").strip()
        self.plat_id = os.getenv("TEACHING_PLATFORM_PLAT_ID", "0").strip() or "0"
        self.auth_prefix = (
            os.getenv("TEACHING_PLATFORM_AUTH_PREFIX", "/auth-server").strip().rstrip("/")
        )
        self.verify_ssl = _truthy(os.getenv("TEACHING_PLATFORM_VERIFY_SSL", "false"))
        self.timeout = float(os.getenv("TEACHING_PLATFORM_TIMEOUT", "20"))
        # 默认 trust_env=False：绕过系统 http(s)_proxy 直连平台。
        # 实测平台公网可直连（curl ~3s），而经代理会多一层间歇握手超时，
        # 故展厅默认直连更稳；如需强制走代理可设 TEACHING_PLATFORM_TRUST_ENV=true。
        self.trust_env = _truthy(os.getenv("TEACHING_PLATFORM_TRUST_ENV", "false"))
        # 瞬时网络错误（SSL EOF / 连接/读取超时）自动重试次数。
        self.max_retries = int(os.getenv("TEACHING_PLATFORM_MAX_RETRIES", "2"))
        # token 有效期保守取 9 小时（平台 cookie TTL 为 10 小时）。
        self._ttl = float(os.getenv("TEACHING_PLATFORM_TOKEN_TTL", str(9 * 3600)))
        self._token: Token | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def configured(self) -> bool:
        """是否具备真实登录条件（地址 + 用户名 + 密码）。"""
        return bool(self.base_url and self.username and self.password)

    def _fetch_public_key(self, client: httpx.Client) -> str:
        resp = client.get(f"{self.base_url}{self.auth_prefix}/open/getKeys")
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict) or not body.get("state") or not body.get("data"):
            raise RuntimeError(f"获取公钥失败：{(body or {}).get('message')}")
        return str(body["data"])

    def login(self) -> str:
        if not self.configured():
            raise RuntimeError(
                "教学平台凭据未配置（TEACHING_PLATFORM_USERNAME/PASSWORD），无法登录。"
            )
        import httpx  # 延迟导入：缺少 httpx 时不影响 Mock 路径

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout, verify=self.verify_ssl, trust_env=self.trust_env
                ) as client:
                    public_key = self._fetch_public_key(client)
                    encrypted_pwd = rsa_encrypt_base64(self.password, public_key)
                    resp = client.post(
                        f"{self.base_url}{self.auth_prefix}/open/login",
                        json={"username": self.username, "password": encrypted_pwd},
                    )
                    resp.raise_for_status()
                    body = resp.json()
                break
            except (httpx.TransportError, OSError) as exc:  # 瞬时网络/SSL 抖动→重试
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"教学平台登录网络异常（已重试 {attempt} 次）：{exc}") from exc
        else:  # pragma: no cover - for/break 正常路径不会到这里
            raise RuntimeError(f"教学平台登录失败：{last_exc}")
        if not isinstance(body, dict) or not body.get("state") or not body.get("data"):
            msg = (body or {}).get("message") or (body or {}).get("errorCode")
            raise RuntimeError(f"教学平台登录失败：{msg}")
        token = str(body["data"])
        self._token = Token(value=token, expires_at=time.time() + self._ttl)
        return token

    def get_token(self, force_refresh: bool = False) -> str:
        """返回有效 token；过期或强制刷新时重新登录（线程安全）。"""
        with self._lock:
            if not force_refresh and self._token and self._token.valid:
                return self._token.value
            return self.login()

    def auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        return {
            "Authorization": self.get_token(force_refresh),
            "platId": self.plat_id,
        }

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
