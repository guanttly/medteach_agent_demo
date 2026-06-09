<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { TickerEvent } from '../types'

defineProps<{ events: TickerEvent[] }>()

const ICONS: Record<string, string> = {
  intent_recognized: 'target',
  plan_proposed: 'clipboard',
  tool_call_succeeded: 'wrench',
  exam_preview_ready: 'document',
  exam_published: 'send',
  report_ready: 'chart',
  recommendation_ready: 'bulb',
  demo_done: 'check'
}

function fmt(ts: number) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(
    d.getSeconds()
  ).padStart(2, '0')}`
}
</script>

<template>
  <div class="ticker glass">
    <div class="tk-head">
      <span class="tk-title">实时事件流</span>
      <span class="live"><i></i>LIVE</span>
    </div>
    <div class="tk-list">
      <transition-group name="list">
        <div v-for="e in events" :key="e.id" class="tk-item" :class="{ fb: e.fallback }">
          <span class="tk-ico"><AppIcon :name="ICONS[e.type] || 'signal'" :size="17" /></span>
          <div class="tk-body">
            <div class="tk-row">
              <span class="tk-name">{{ e.title }}</span>
              <span class="tk-time mono">{{ fmt(e.ts) }}</span>
            </div>
            <div class="tk-msg">{{ e.message }}</div>
          </div>
          <span v-if="e.fallback" class="fb-badge">兜底</span>
        </div>
      </transition-group>
      <div v-if="!events.length" class="tk-empty">等待智能体动作…</div>
    </div>
  </div>
</template>

<style scoped>
.ticker { padding: 16px 18px; display: flex; flex-direction: column; min-height: 0; }
.tk-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.tk-title { font-size: 15px; font-weight: 800; }
.live { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--danger); letter-spacing: 1px; }
.live i { width: 7px; height: 7px; border-radius: 50%; background: var(--danger); animation: pulse 1.2s infinite; }
.tk-list { overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 8px; }
.tk-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--line);
  align-items: flex-start;
}
.tk-item.fb { border-color: rgba(251, 191, 36, 0.4); background: rgba(251, 191, 36, 0.06); }
.tk-ico { color: var(--cyan); display: grid; place-items: center; margin-top: 1px; }
.tk-body { flex: 1; min-width: 0; }
.tk-row { display: flex; justify-content: space-between; gap: 8px; }
.tk-name { font-size: 13.5px; font-weight: 700; }
.tk-time { font-size: 11px; color: var(--muted); }
.tk-msg { font-size: 12px; color: var(--muted); margin-top: 3px; line-height: 1.4; word-break: break-all; }
.fb-badge {
  flex: none;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 6px;
  background: var(--gold);
  color: #2a1d02;
  font-weight: 700;
  height: fit-content;
}
.tk-empty { color: var(--muted); font-size: 13px; text-align: center; padding: 24px 0; }
</style>
