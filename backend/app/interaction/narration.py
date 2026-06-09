"""播报聚合器（Narration Aggregator）。

对应方案 8.3 / 9.5 / 10：后台产生的可播报信息先进入 pending_narration，
按 summary_key 合并、按 fact_version 去旧、丢弃过期项、保留 requires_verbatim 项，
再合成「一段」自然口播交给 Speaker，而不是逐条 FIFO 补播。

合成优先用 LLM（Narration Summarizer），超时/失败回退确定性模板。
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ..config import settings
from .events import Ev, event_bus
from .models import NarrationItem, Priority, PRIORITY_RANK, next_narration_id
from .speaker import speaker

if TYPE_CHECKING:
    from ..session_store import Session

logger = logging.getLogger("interaction.narration")


class NarrationAggregator:
    async def enqueue(
        self,
        s: "Session",
        *,
        kind: str,
        summary_key: str,
        priority: str = Priority.NORMAL.value,
        fact_path: str | None = None,
        fact_version: int = 0,
        job_id: str | None = None,
        requires_verbatim: bool = False,
        payload: dict[str, Any] | None = None,
        expires_at: float = 0.0,
    ) -> NarrationItem:
        item = NarrationItem(
            item_id=next_narration_id(),
            session_id=s.session_id,
            kind=kind,
            priority=priority,
            summary_key=summary_key,
            fact_path=fact_path,
            fact_version=fact_version,
            job_id=job_id,
            requires_verbatim=requires_verbatim,
            payload=payload or {},
            expires_at=expires_at,
        )
        # 合并：同 summary_key 的旧非 verbatim 项被新项取代（去旧版本）
        dropped: list[str] = []
        kept: list[NarrationItem] = []
        for old in s.pending_narration:
            if (
                old.summary_key == item.summary_key
                and not old.requires_verbatim
                and old.fact_version <= item.fact_version
            ):
                dropped.append(old.item_id)
                s.metrics["narration_coalesced_count"] += 1
            else:
                kept.append(old)
        kept.append(item)
        s.pending_narration = kept
        await event_bus.emit(
            s,
            Ev.NAR_ITEM_QUEUED,
            {
                "item_id": item.item_id,
                "kind": kind,
                "priority": priority,
                "summary_key": summary_key,
                "fact_path": fact_path,
                "fact_version": fact_version,
                "dropped_item_ids": dropped,
            },
            job_id=job_id,
            priority=priority,
        )
        return item

    def has_pending(self, s: "Session") -> bool:
        return any(not it.expired for it in s.pending_narration)

    def _purge_stale(self, s: "Session") -> list[NarrationItem]:
        live: list[NarrationItem] = []
        for it in s.pending_narration:
            if it.expired and not it.requires_verbatim:
                s.metrics["narration_dropped_stale_count"] += 1
            else:
                live.append(it)
        s.pending_narration = live
        return live

    async def flush(
        self,
        s: "Session",
        *,
        focus_topic: str | None = None,
        turn_id: str | None = None,
        job_id: str | None = None,
        force: bool = False,
        respect_user_active: bool = True,
    ) -> bool:
        """合并 pending 项并播报一段总结。返回是否播报。"""
        items = self._purge_stale(s)
        if not items:
            return False

        top_rank = max(PRIORITY_RANK.get(it.priority, 1) for it in items)

        # 语音交互即 UI：用户刚说话/正在交互时，后台「过程类」播报（进度 / 安抚）主动让路，
        # 不抢占语音通道、也不消费 pending（待用户交互窗口过后再合并补播）；
        # 仅「结果 / 错误」这类必须送达的高优先级信息照常播报（仍可被用户打断）。
        if respect_user_active and s.user_active and top_rank < PRIORITY_RANK[Priority.HIGH.value]:
            return False

        # 正在播报且只有普通/低优先级信息时，先不抢；等下一次安全点再合并
        if not force and s.interaction.get("speaking") and top_rank < PRIORITY_RANK[Priority.HIGH.value]:
            return False

        consumed_ids = [it.item_id for it in items]
        verbatim_items = [it for it in items if it.requires_verbatim]
        s.metrics["verbatim_item_preserved_count"] += len(verbatim_items)

        text = await self._summarize(s, items, focus_topic)
        if not text:
            s.pending_narration = []
            return False

        await event_bus.emit(
            s,
            Ev.NAR_SUMMARY_EMITTED,
            {
                "source_item_ids": consumed_ids,
                "text": text,
                "reason": "coalesced_narration",
            },
            job_id=job_id,
            priority=Priority.NORMAL.value,
        )

        # 消费掉本次聚合的条目
        s.pending_narration = []
        s.conversation["last_answer_topic"] = focus_topic or s.conversation.get("last_answer_topic")

        out_priority = Priority.HIGH.value if top_rank >= PRIORITY_RANK[Priority.HIGH.value] else Priority.NORMAL.value
        await speaker.say(
            s,
            text,
            priority=out_priority,
            turn_id=turn_id,
            job_id=job_id,
            source="narration",
            interruptible=not any(it.kind == "confirmation" for it in verbatim_items) or True,
        )
        return True

    # ------------------------------------------------------------------ #
    # 合成
    # ------------------------------------------------------------------ #
    async def _summarize(
        self, s: "Session", items: list[NarrationItem], focus_topic: str | None
    ) -> str:
        keys = {it.summary_key for it in items}
        # 预制文本（如 heartbeat 安抚句）：直接使用，无需模型/事实合成
        explicit = [it.payload.get("text") for it in items if it.payload.get("text")]
        if explicit and len(explicit) == len(items):
            uniq = list(dict.fromkeys(t for t in explicit if t))
            return uniq[-1] if len(uniq) == 1 else "；".join(uniq)
        # 先尝试 LLM 摘要（可被关闭 / 超时回退）
        if settings.chat_llm_configured and len(items) > 1:
            try:
                from ..agent_brain import agent_brain

                payload = self._build_summary_payload(s, items, focus_topic)
                text = await asyncio.wait_for(
                    agent_brain.summarize_narration(payload),
                    timeout=min(4.0, max(1.0, settings.LLM_TIMEOUT_SECONDS)),
                )
                if text and text.strip():
                    return text.strip()
            except Exception as exc:  # noqa: BLE001
                logger.warning("narration summarizer fallback: %s", exc)
        return self._deterministic_summary(s, keys, focus_topic)

    def _build_summary_payload(
        self, s: "Session", items: list[NarrationItem], focus_topic: str | None
    ) -> dict[str, Any]:
        from .facts import facts_resolver

        return {
            "current_user_focus": {
                "last_turn": s.conversation.get("last_user_text"),
                "last_answer_topic": focus_topic or s.conversation.get("last_answer_topic"),
            },
            "current_foreground_state": {
                "speaking": s.interaction.get("speaking"),
            },
            "latest_facts": facts_resolver.build_llm_context(s)["facts"],
            "need_confirmation": s.need_user_confirmation,
            "confirmation_type": s.confirmation_type,
            "pending_items": [it.to_dict() for it in items],
        }

    def _deterministic_summary(
        self, s: "Session", keys: set[str], focus_topic: str | None
    ) -> str:
        # 结果优先于过程
        if "exam_result" in keys and s.result:
            sm = s.result.get("summary", {})
            weak = "、".join(w["name"] for w in s.result.get("weak_points", [])[:2])
            tail = f"，主要薄弱点是{weak}" if weak else ""
            head = "阅卷完成，我先报核心结果：" if "recommendation" not in keys else "阅卷和复训病例都准备好了，先说核心结果："
            return f"{head}平均分 {sm.get('average')} 分，及格率 {sm.get('pass_rate')}%{tail}。"

        if "exam_progress" in keys and s.progress:
            total = int(s.progress.get("published") or (s.exam_plan or {}).get("student_count") or 8)
            submitted = int(s.progress.get("submitted") or 0)
            answering = int(s.progress.get("answering") or 0)
            label = s.progress.get("label") or "答题进度更新"
            return f"我这边看到进度有了新变化：{label}，{total} 人里已经有 {submitted} 人交卷、{answering} 人还在答题。"

        # 准备链路合并
        prep: list[str] = []
        if "participants" in keys and s.students:
            prep.append(f"{s.students.get('total', 8)} 名学员已经绑定")
        if "exam_draft" in keys:
            prep.append("考试草稿建好了")
        if "exam_preview" in keys and s.exam_preview:
            q = s.exam_preview.get("question_total") or (s.exam_plan or {}).get("question_total") or 17
            prep.append(f"{q} 道题的试卷预览也生成了")
        if "publish" in keys:
            prep.append("考试已经下发、入口和二维码都开好了")

        lead = ""
        if focus_topic in {"participants", "exam_plan", "progress"} and prep:
            lead = "您刚才问的时候，我这边也把后续准备好了："
        body = ""
        if prep:
            body = (lead or "我这边的准备有进展：") + "，".join(prep) + "。"

        # 确认请求（verbatim，附在末尾）
        if s.need_user_confirmation and s.confirmation_type == "confirm_publish":
            body = (body + "您确认后，我就可以下发考试。").strip()
        elif s.need_user_confirmation and s.confirmation_type == "confirm_plan":
            body = (body + "您确认方案后，我就继续创建试卷。").strip()

        return body or "我这边有了一些新进展，您可以随时问我目前到哪一步。"


narration = NarrationAggregator()
