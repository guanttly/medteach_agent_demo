"""TTS 路由：服务端调用阿里云合成语音；未配置时让前端回退浏览器 TTS。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from ..config import settings
from ..models.schemas import TTSRequest
from ..tts_service import aliyun_tts, redact_sensitive

logger = logging.getLogger("tts_route")
router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.get("/config")
async def tts_config() -> dict:
    return {
        "provider": "aliyun" if settings.aliyun_tts_enabled else "browser",
        "enabled": settings.aliyun_tts_enabled,
        "voice": settings.ALIYUN_NLS_VOICE,
    }


@router.post("")
async def synthesize(req: TTSRequest):
    text = (req.text or "").strip()
    if not text:
        return JSONResponse({"fallback": "browser", "reason": "empty_text"}, status_code=200)
    if not settings.aliyun_tts_enabled:
        # 未配置阿里云凭据 -> 通知前端使用浏览器 SpeechSynthesis
        return JSONResponse(
            {
                "fallback": "browser",
                "text": text,
                "reason": settings.aliyun_tts_disabled_reason or "disabled",
            },
            status_code=200,
        )
    try:
        audio, content_type = await aliyun_tts.synthesize(text, req.voice)
        return Response(
            content=audio,
            media_type=content_type or "audio/mpeg",
            headers={"Cache-Control": "no-store", "X-TTS-Provider": "aliyun"},
        )
    except Exception as exc:  # noqa: BLE001
        error = redact_sensitive(str(exc))
        logger.warning("aliyun tts failed, fallback browser: %s", error)
        return JSONResponse({"fallback": "browser", "text": text, "error": error}, status_code=200)
