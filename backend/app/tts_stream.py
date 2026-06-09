"""前端 ⇄ Demo Shell 的「流式 TTS」WebSocket 代理。

前端把要朗读的句子逐句通过 WS 发来，服务端实时调用阿里云流式语音合成，
把 PCM 音频帧「边合成边」回推；前端用 Web Audio 无缝调度播放，做到边合成边出声，
避免「整句合成完才出声」带来的十几秒等待。

协议（前端 → 服务端，文本 JSON）：
    {"type": "synthesize", "id": <int>, "text": "...", "voice": "..."}
    {"type": "cancel"}          # 打断：清空队列并停止当前合成
    {"type": "ping"}            # 心跳

协议（服务端 → 前端）：
    {"type": "config",   "provider": "aliyun"|"browser", "sample_rate": 16000, "format": "pcm"}
    {"type": "start",    "id": <int>, "sample_rate": 16000, "format": "pcm"}
    <binary frames>             # PCM 16bit 小端 单声道
    {"type": "end",      "id": <int>}
    {"type": "fallback", "id": <int>, "text": "...", "reason": "..."}  # 让前端改用浏览器 TTS
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

from .config import settings
from .tts_service import aliyun_tts, redact_sensitive

logger = logging.getLogger("tts_stream")


@dataclass
class _Job:
    id: int
    text: str
    voice: str | None
    gen: int


class _Connection:
    """单条前端连接的状态机：一个顺序工作协程 + 一个读协程。"""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.queue: asyncio.Queue[_Job | None] = asyncio.Queue()
        self.gen = 0  # 每次 cancel 自增，用于丢弃过期任务/音频
        self.closed = False

    async def run(self) -> None:
        await self.ws.accept()
        await self._safe_send_json(
            {
                "type": "config",
                "provider": "aliyun" if settings.aliyun_tts_enabled else "browser",
                "sample_rate": settings.ALIYUN_NLS_SAMPLE_RATE,
                "format": "pcm",
            }
        )
        worker = asyncio.create_task(self._worker())
        try:
            await self._reader()
        finally:
            self.closed = True
            await self.queue.put(None)
            worker.cancel()
            try:
                await worker
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # ------------------------------ 读协程 ------------------------------ #
    async def _reader(self) -> None:
        while True:
            try:
                msg = await self.ws.receive_json()
            except WebSocketDisconnect:
                return
            except ValueError:
                # 非法 JSON 帧：忽略，保持连接
                continue
            except Exception:  # noqa: BLE001
                return
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            if mtype == "synthesize":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                self.queue.put_nowait(
                    _Job(
                        id=int(msg.get("id") or 0),
                        text=text,
                        voice=msg.get("voice"),
                        gen=self.gen,
                    )
                )
            elif mtype == "cancel":
                self.gen += 1
                self._drain_queue()
            elif mtype == "ping":
                continue

    def _drain_queue(self) -> None:
        try:
            while True:
                self.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    # ------------------------------ 工作协程 ------------------------------ #
    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            if job is None:
                return
            if self.closed or job.gen != self.gen:
                continue
            await self._synthesize_job(job)

    async def _synthesize_job(self, job: _Job) -> None:
        if not settings.aliyun_tts_enabled:
            await self._safe_send_json(
                {"type": "fallback", "id": job.id, "text": job.text, "reason": "disabled"}
            )
            return

        started = False
        gen = aliyun_tts.stream_synthesize(job.text, job.voice)
        try:
            async for chunk in gen:
                if self.closed or job.gen != self.gen:
                    return
                if not started:
                    started = True
                    await self._safe_send_json(
                        {
                            "type": "start",
                            "id": job.id,
                            "sample_rate": settings.ALIYUN_NLS_SAMPLE_RATE,
                            "format": "pcm",
                        }
                    )
                if chunk:
                    try:
                        await self.ws.send_bytes(chunk)
                    except Exception:  # noqa: BLE001
                        self.closed = True
                        return
            if self.closed or job.gen != self.gen:
                return
            if started:
                await self._safe_send_json({"type": "end", "id": job.id})
            else:
                # 没有产出任何音频 -> 让前端兜底
                await self._safe_send_json(
                    {"type": "fallback", "id": job.id, "text": job.text, "reason": "empty"}
                )
        except Exception as exc:  # noqa: BLE001
            err = redact_sensitive(str(exc))
            logger.warning("stream tts failed, fallback browser: %s", err)
            if not (self.closed or job.gen != self.gen):
                await self._safe_send_json(
                    {"type": "fallback", "id": job.id, "text": job.text, "reason": err}
                )
        finally:
            try:
                await gen.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def _safe_send_json(self, data: dict) -> None:
        try:
            await self.ws.send_json(data)
        except Exception:  # noqa: BLE001
            self.closed = True


async def handle_tts_stream(ws: WebSocket, session_id: str) -> None:
    conn = _Connection(ws)
    try:
        await conn.run()
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("tts stream connection error: %s", redact_sensitive(str(exc)))
