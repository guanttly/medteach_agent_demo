"""WebSocket 连接管理：按 session 维度广播大屏 / 数字形象事件。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class WSManager:
    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._conns.setdefault(session_id, set()).add(ws)
        logger.info("ws connected session=%s total=%d", session_id, len(self._conns[session_id]))

    async def disconnect(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._conns.get(session_id)
            if conns and ws in conns:
                conns.discard(ws)
                if not conns:
                    self._conns.pop(session_id, None)

    async def broadcast(self, session_id: str, event: dict[str, Any]) -> None:
        conns = list(self._conns.get(session_id, set()))
        if not conns:
            return
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.disconnect(session_id, ws)


ws_manager = WSManager()
