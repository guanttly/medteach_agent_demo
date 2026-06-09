"""阿里云智能语音交互 (NLS) 文字转语音服务。

支持两种凭据方式：
1. 直接配置 NLS AccessToken：ALIYUN_NLS_TOKEN + ALIYUN_NLS_APPKEY
2. 配置 AccessKey，由服务端调用 CreateToken 自动换取：
   ALIYUN_AK_ID + ALIYUN_AK_SECRET + ALIYUN_NLS_APPKEY

未配置时 aliyun_tts_enabled = False，前端自动回退浏览器 SpeechSynthesis。
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import logging
import re
import time
import urllib.parse
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from .config import settings

logger = logging.getLogger("tts")

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]+"),
]


def redact_sensitive(value: str) -> str:
    text = value
    for secret in (
        settings.ALIYUN_NLS_TOKEN,
        settings.ALIYUN_AK_ID,
        settings.ALIYUN_AK_SECRET,
    ):
        if secret and len(secret) >= 6:
            text = text.replace(secret, "***")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("sk-***", text)
    return text


@dataclass
class _CachedToken:
    value: str
    expire_at: float  # epoch seconds

    @property
    def valid(self) -> bool:
        return bool(self.value) and time.time() < (self.expire_at - 60)


class AliyunTTS:
    def __init__(self) -> None:
        self._token: _CachedToken | None = None
        self._warned_invalid_env_token = False

    # ----------------------------- Token ----------------------------- #
    async def _get_token(self) -> str:
        if settings.aliyun_nls_token_valid:
            return settings.ALIYUN_NLS_TOKEN
        if settings.ALIYUN_NLS_TOKEN and not self._warned_invalid_env_token:
            logger.warning(
                "ignore ALIYUN_NLS_TOKEN because it looks like a general API key, not an NLS token"
            )
            self._warned_invalid_env_token = True
        if self._token and self._token.valid:
            return self._token.value
        if not settings.aliyun_ak_configured:
            raise RuntimeError("阿里云 TTS 未启用：ALIYUN_NLS_TOKEN 不是有效 NLS Token，且未配置 AccessKey。")
        token, expire_at = await self._create_token()
        self._token = _CachedToken(value=token, expire_at=expire_at)
        return token

    async def _create_token(self) -> tuple[str, float]:
        """RPC 风格签名调用 CreateToken（HMAC-SHA1）。"""
        ak_id = settings.ALIYUN_AK_ID
        ak_secret = settings.ALIYUN_AK_SECRET
        if not (ak_id and ak_secret):
            raise RuntimeError("缺少阿里云 AccessKey，无法换取 Token。")

        params = {
            "AccessKeyId": ak_id,
            "Action": "CreateToken",
            "Format": "JSON",
            "RegionId": settings.ALIYUN_NLS_REGION,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": str(uuid.uuid4()),
            "SignatureVersion": "1.0",
            "Timestamp": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2019-02-28",
        }

        def _enc(s: str) -> str:
            return urllib.parse.quote(s, safe="~")

        canonical = "&".join(f"{_enc(k)}={_enc(v)}" for k, v in sorted(params.items()))
        string_to_sign = "GET&" + _enc("/") + "&" + _enc(canonical)
        signature = base64.b64encode(
            hmac.new((ak_secret + "&").encode(), string_to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        params["Signature"] = signature

        url = "http://nls-meta.cn-shanghai.aliyuncs.com/?" + urllib.parse.urlencode(params)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                body_text = redact_sensitive(resp.text[:500])
                raise RuntimeError(f"CreateToken 失败（HTTP {resp.status_code}）：{body_text}")
            data = resp.json()
        token_obj = data.get("Token") or {}
        token = token_obj.get("Id")
        expire = float(token_obj.get("ExpireTime", time.time() + 3600))
        if not token:
            raise RuntimeError(f"CreateToken 返回异常：{data}")
        return token, expire

    # --------------------------- Synthesis --------------------------- #
    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        """返回 (audio_bytes, content_type)。失败抛异常，由路由兜底。"""
        token = await self._get_token()
        appkey = settings.ALIYUN_NLS_APPKEY
        region = settings.ALIYUN_NLS_REGION
        url = f"https://nls-gateway-{region}.aliyuncs.com/stream/v1/tts"
        body = {
            "appkey": appkey,
            "token": token,
            "text": text,
            "format": settings.ALIYUN_NLS_FORMAT,
            "sample_rate": settings.ALIYUN_NLS_SAMPLE_RATE,
            "voice": voice or settings.ALIYUN_NLS_VOICE,
            "volume": 60,
            "speech_rate": 0,
            "pitch_rate": 0,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=body)
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("audio"):
            return resp.content, content_type
        # 失败时网关返回 JSON
        body_text = redact_sensitive(resp.text[:500])
        raise RuntimeError(f"阿里云 TTS 失败（HTTP {resp.status_code}）：{body_text}")

    # ------------------------- Streaming Synthesis ------------------------- #
    async def stream_synthesize(
        self, text: str, voice: str | None = None
    ) -> AsyncIterator[bytes]:
        """流式语音合成：建立到阿里云 NLS 的 WebSocket，边合成边产出 PCM 音频帧。

        采用 SpeechSynthesizer/StartSynthesis 协议，format=pcm（16bit 小端 单声道），
        首帧音频通常在数百毫秒内返回，避免「整句合成完才出声」的等待。

        失败（未配置 / 鉴权失败 / 任务失败 / 网络异常）抛异常，由上层回退浏览器 TTS。
        """
        text = (text or "").strip()
        if not text:
            return
        try:
            from websockets.asyncio.client import connect as ws_connect
        except Exception as exc:  # pragma: no cover - 依赖缺失
            raise RuntimeError(f"websockets 客户端不可用：{exc}") from exc

        token = await self._get_token()
        appkey = settings.ALIYUN_NLS_APPKEY
        region = settings.ALIYUN_NLS_REGION
        sample_rate = settings.ALIYUN_NLS_SAMPLE_RATE
        url = f"wss://nls-gateway-{region}.aliyuncs.com/ws/v1"
        task_id = uuid.uuid4().hex
        start_cmd = {
            "header": {
                "appkey": appkey,
                "message_id": uuid.uuid4().hex,
                "task_id": task_id,
                "namespace": "SpeechSynthesizer",
                "name": "StartSynthesis",
            },
            "payload": {
                "voice": voice or settings.ALIYUN_NLS_VOICE,
                "format": "pcm",
                "sample_rate": sample_rate,
                "volume": 60,
                "speech_rate": 0,
                "pitch_rate": 0,
                "text": text,
                "enable_subtitle": False,
            },
        }
        async with ws_connect(
            url,
            additional_headers={"X-NLS-Token": token},
            open_timeout=8,
            close_timeout=2,
            ping_interval=None,
            max_size=None,
        ) as ws:
            await ws.send(json.dumps(start_cmd, ensure_ascii=False))
            async for frame in ws:
                if isinstance(frame, (bytes, bytearray)):
                    if frame:
                        yield bytes(frame)
                    continue
                try:
                    msg = json.loads(frame)
                except (json.JSONDecodeError, TypeError):
                    continue
                name = (msg.get("header") or {}).get("name")
                if name == "SynthesisCompleted":
                    return
                if name == "TaskFailed":
                    hdr = msg.get("header") or {}
                    status = hdr.get("status")
                    detail = hdr.get("status_text") or hdr.get("status_message") or ""
                    raise RuntimeError(
                        f"阿里云流式 TTS 任务失败：{status} {redact_sensitive(str(detail))}"
                    )
                # 其它事件（SynthesisStarted / MetaInfo 等）忽略，继续读音频帧。


aliyun_tts = AliyunTTS()
