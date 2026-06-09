"""口播器（Speaker / Utterance Emitter）。

负责把「要朗读给现场观众听的话」以流式方式发给前端：
- 逐字推 utterance.delta（字幕即时显现）
- 按句推 utterance.sentence（前端据此做句级流式 TTS）
- 每条 utterance 带 priority / generation / interruptible / source

barge-in 感知：开播时捕获当前 generation；流式过程中若 generation 被推进
（用户打断 / 重置），立即中止本条 utterance，旧字幕与音频不再继续。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from ..constants import SharkState
from .events import Ev, event_bus
from .models import Priority, next_utterance_id

if TYPE_CHECKING:
    from ..session_store import Session

logger = logging.getLogger("interaction.speaker")

_SENTENCE_END = "。！？!?；;…\n"


def _find_sentence_cut(buf: str, min_len: int = 4) -> int:
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_END and i + 1 >= min_len:
            return i
    return -1


class Speaker:
    async def say(
        self,
        s: "Session",
        text: str,
        *,
        priority: str = Priority.NORMAL.value,
        turn_id: str | None = None,
        job_id: str | None = None,
        source: str = "dialogue",
        interruptible: bool = True,
        tts: bool = True,
        shark_state: SharkState = SharkState.SPEAKING,
    ) -> bool:
        """把一段已知文本以流式方式播报。返回 True 表示完整播完，False 表示中途被打断。"""
        async def _gen() -> AsyncIterator[str]:
            step = 8
            for i in range(0, len(text), step):
                yield text[i : i + step]
                await asyncio.sleep(0.016)

        return await self.say_stream(
            s,
            _gen(),
            priority=priority,
            turn_id=turn_id,
            job_id=job_id,
            source=source,
            interruptible=interruptible,
            tts=tts,
            shark_state=shark_state,
        )

    async def say_stream(
        self,
        s: "Session",
        pieces: AsyncIterator[str],
        *,
        priority: str = Priority.NORMAL.value,
        turn_id: str | None = None,
        job_id: str | None = None,
        source: str = "dialogue",
        interruptible: bool = True,
        tts: bool = True,
        shark_state: SharkState = SharkState.SPEAKING,
    ) -> bool:
        gen = s.generation
        utterance_id = next_utterance_id()
        s.interaction["speaking"] = True
        s.interaction["current_utterance_id"] = utterance_id
        s.interaction["current_utterance_priority"] = priority
        s.interaction["foreground_state"] = "speaking"
        s.shark_state = shark_state.value

        await event_bus.emit(
            s,
            Ev.UTT_STARTED,
            {
                "utterance_id": utterance_id,
                "priority": priority,
                "interruptible": interruptible,
                "source": source,
                "tts": tts,
                "shark_state": shark_state.value,
            },
            turn_id=turn_id,
            job_id=job_id,
            utterance_id=utterance_id,
            priority=priority,
        )

        full = ""
        buf = ""
        idx = 0
        interrupted = False
        try:
            async for piece in pieces:
                if interruptible and s.generation != gen:
                    interrupted = True
                    break
                if not piece:
                    continue
                full += piece
                buf += piece
                s.assistant_text = full
                await event_bus.emit(
                    s,
                    Ev.UTT_DELTA,
                    {"utterance_id": utterance_id, "delta": piece, "text": full},
                    turn_id=turn_id,
                    job_id=job_id,
                    utterance_id=utterance_id,
                    priority=priority,
                    generation=gen,
                )
                while True:
                    cut = _find_sentence_cut(buf)
                    if cut == -1:
                        break
                    sentence = buf[: cut + 1].strip()
                    buf = buf[cut + 1 :]
                    if sentence:
                        await event_bus.emit(
                            s,
                            Ev.UTT_SENTENCE,
                            {"utterance_id": utterance_id, "sentence": sentence, "index": idx, "tts": tts},
                            turn_id=turn_id,
                            job_id=job_id,
                            utterance_id=utterance_id,
                            priority=priority,
                            generation=gen,
                        )
                        idx += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("utterance stream error: %s", exc)

        if interruptible and s.generation != gen:
            interrupted = True

        if not interrupted:
            tail = buf.strip()
            if tail:
                await event_bus.emit(
                    s,
                    Ev.UTT_SENTENCE,
                    {"utterance_id": utterance_id, "sentence": tail, "index": idx, "tts": tts},
                    turn_id=turn_id,
                    job_id=job_id,
                    utterance_id=utterance_id,
                    priority=priority,
                    generation=gen,
                )
            if full.strip():
                s.assistant_text = full
                s.record_assistant_utterance(full)
            await event_bus.emit(
                s,
                Ev.UTT_COMPLETED,
                {"utterance_id": utterance_id, "text": full},
                turn_id=turn_id,
                job_id=job_id,
                utterance_id=utterance_id,
                priority=priority,
                generation=gen,
            )

        # 仅当自己仍是当前 utterance 时才清理 speaking 状态
        if s.interaction.get("current_utterance_id") == utterance_id:
            s.interaction["speaking"] = False
            s.interaction["current_utterance_id"] = None
            s.interaction["current_utterance_priority"] = None
            if s.interaction.get("foreground_state") == "speaking":
                s.interaction["foreground_state"] = "idle"
        return not interrupted


speaker = Speaker()
