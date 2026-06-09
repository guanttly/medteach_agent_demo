"""巨鲨医用教学智能体展厅 Demo —— Demo Shell 入口 (FastAPI)。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .interaction.presenter import presenter
from .routes import control, conversation, demo, sessions, tts
from .session_store import session_store
from .tts_stream import handle_tts_stream
from .ws_manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(title="巨鲨医用教学智能体展厅 Demo Shell", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(demo.router)
app.include_router(control.router)
app.include_router(conversation.router)
app.include_router(sessions.router)
app.include_router(tts.router)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "demo_mode": settings.DEMO_MODE,
        "agent_mode": settings.AGENT_MODE,
        "aliyun_tts": settings.aliyun_tts_enabled,
        "llm_configured": settings.llm_configured,
        "llm_provider": settings.llm_provider_label,
        "agent_source": "llm" if settings.llm_configured else "local",
    }


@app.websocket("/ws/demo/{session_id}")
async def ws_demo(websocket: WebSocket, session_id: str) -> None:
    await ws_manager.connect(session_id, websocket)
    session = session_store.get(session_id)
    # 新连接立即同步当前完整快照（两个前端断线重连也能对齐）
    await presenter.push_snapshot(session)
    try:
        while True:
            # 客户端心跳 / ping，保持连接
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(session_id, websocket)
    except Exception:  # noqa: BLE001
        await ws_manager.disconnect(session_id, websocket)


@app.websocket("/ws/tts/{session_id}")
async def ws_tts(websocket: WebSocket, session_id: str) -> None:
    """流式 TTS 通道：前端逐句发文本，服务端边合成边回推 PCM 音频帧。"""
    await handle_tts_stream(websocket, session_id)


# ----------------------------------------------------------------------------
# 生产部署：若已构建前端，则由 Demo Shell 直接托管两个网页端（单端口）。
# 开发阶段使用 Vite dev server（已开启 CORS），此处仅作为可选回退。
# ----------------------------------------------------------------------------
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api", "ws")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root() -> dict:
        return {
            "service": "巨鲨医用教学智能体展厅 Demo Shell",
            "hint": "前端尚未构建。开发模式请启动 Vite：cd frontend && npm run dev",
            "frontends": {
                "big_screen": "/screen",
                "avatar": "/avatar",
                "control": "/control",
            },
        }
