<script setup lang="ts">
import { computed } from 'vue'
import CountUp from './CountUp.vue'
import AppIcon from './AppIcon.vue'
import type { Progress } from '../types'

const props = defineProps<{ progress: Progress; total: number }>()

const total = computed(() => props.total || props.progress.published || 8)
const submitRatio = computed(() => Math.min(1, props.progress.submitted / total.value))
const R = 54
const C = 2 * Math.PI * R
const dash = computed(() => C * (1 - submitRatio.value))

const countdown = computed(() => {
  const s = Math.max(0, props.progress.remaining_seconds || 0)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
})

const dots = computed(() => Array.from({ length: total.value }, (_, i) => i < props.progress.submitted))
</script>

<template>
  <div class="card glass fade-up">
    <div class="card-head">
      <span class="ico"><AppIcon name="signal" :size="22" /></span>
      <div>
        <div class="card-title">答题进度</div>
        <div class="card-sub">{{ progress.label || '实时监考' }}</div>
      </div>
      <div class="countdown">
        <span class="cd-label">剩余</span>
        <span class="cd-time mono">{{ countdown }}</span>
      </div>
    </div>

    <div class="prog-body">
      <div class="ring-wrap">
        <svg viewBox="0 0 140 140" class="ring">
          <circle cx="70" cy="70" :r="R" class="ring-bg" />
          <circle
            cx="70"
            cy="70"
            :r="R"
            class="ring-fg"
            :stroke-dasharray="C"
            :stroke-dashoffset="dash"
          />
        </svg>
        <div class="ring-center">
          <div class="ring-num"><CountUp :value="progress.submitted" />/{{ total }}</div>
          <div class="ring-label">已提交</div>
        </div>
      </div>

      <div class="stats">
        <div class="stat">
          <div class="s-num"><CountUp :value="progress.published" /></div>
          <div class="s-label">已下发</div>
        </div>
        <div class="stat">
          <div class="s-num"><CountUp :value="progress.entered" /></div>
          <div class="s-label">已进入</div>
        </div>
        <div class="stat">
          <div class="s-num answering"><CountUp :value="progress.answering" /></div>
          <div class="s-label">答题中</div>
        </div>
        <div class="stat">
          <div class="s-num done"><CountUp :value="progress.submitted" /></div>
          <div class="s-label">已提交</div>
        </div>
      </div>
    </div>

    <div class="dots">
      <span v-for="(d, i) in dots" :key="i" class="seat" :class="{ on: d }"></span>
    </div>
  </div>
</template>

<style scoped>
.card { padding: 20px 22px; }
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.card-head .ico { color: var(--cyan); display: grid; place-items: center; }
.card-title { font-size: 17px; font-weight: 800; }
.card-sub { font-size: 11px; color: var(--muted); letter-spacing: 1px; }
.countdown { margin-left: auto; text-align: right; }
.cd-label { font-size: 11px; color: var(--muted); margin-right: 6px; }
.cd-time { font-size: 22px; font-weight: 800; color: var(--gold); }

.prog-body { display: flex; align-items: center; gap: 26px; }
.ring-wrap { position: relative; width: 140px; height: 140px; flex: none; }
.ring { width: 140px; height: 140px; transform: rotate(-90deg); }
.ring-bg { fill: none; stroke: rgba(255, 255, 255, 0.08); stroke-width: 12; }
.ring-fg {
  fill: none;
  stroke: url(#g);
  stroke: var(--aqua);
  stroke-width: 12;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s cubic-bezier(0.22, 1, 0.36, 1);
  filter: drop-shadow(0 0 8px rgba(34, 211, 238, 0.7));
}
.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.ring-num { font-size: 26px; font-weight: 800; }
.ring-label { font-size: 12px; color: var(--muted); }

.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; flex: 1; }
.stat {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
}
.s-num { font-size: 26px; font-weight: 800; }
.s-num.answering { color: var(--gold); }
.s-num.done { color: var(--teal); }
.s-label { font-size: 12px; color: var(--muted); margin-top: 2px; }

.dots { display: flex; gap: 8px; margin-top: 18px; flex-wrap: wrap; }
.seat {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid var(--line);
  transition: all 0.5s ease;
}
.seat.on {
  background: linear-gradient(135deg, var(--teal), var(--cyan));
  border-color: transparent;
  box-shadow: 0 0 12px rgba(45, 212, 191, 0.6);
}
</style>
