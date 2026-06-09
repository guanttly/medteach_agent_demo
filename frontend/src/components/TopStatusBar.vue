<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useDemoStore } from '../stores/demo'
import AppIcon from './AppIcon.vue'

const store = useDemoStore()
const { stateLabel } = storeToRefs(store)
</script>

<template>
  <header class="topbar glass">
    <div class="left">
      <span class="brand-logo"><AppIcon name="shark" :size="30" /></span>
      <div>
        <div class="t1">巨鲨数字助教 · 展厅大屏</div>
        <div class="t2">当前任务 · 安排胸部 CT 基础诊断考试</div>
      </div>
    </div>

    <div class="center">
      <div class="stage-label">
        <span class="stage-dot"></span>
        当前阶段 · {{ stateLabel }}
      </div>
    </div>

    <div class="right">
      <span class="chip"><i class="dot" :class="store.connected ? 'ok' : 'err'"></i>{{ store.connected ? '已连接' : '重连中' }}</span>
      <span class="chip">
        <i class="dot" :class="store.fallbackActive ? 'warn' : store.busy ? 'run' : 'ok'"></i>
        助教 · {{ store.fallbackActive ? '稳妥模式' : store.busy ? '处理中' : '就绪' }}
      </span>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 26px;
  border-radius: 18px;
}
.left { display: flex; align-items: center; gap: 14px; }
.brand-logo { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 13px; color: var(--cyan); background: var(--glass-2); border: 1px solid var(--line); }
.t1 { font-size: 19px; font-weight: 800; letter-spacing: 0.4px; }
.t2 { font-size: 13px; color: var(--muted); margin-top: 2px; }
.center { flex: 1; display: flex; justify-content: center; }
.stage-label {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--aqua);
  padding: 8px 20px;
  border-radius: 999px;
  background: rgba(34, 211, 238, 0.08);
  border: 1px solid rgba(34, 211, 238, 0.25);
}
.stage-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--aqua);
  box-shadow: 0 0 12px var(--aqua);
  animation: pulse 1.4s ease-in-out infinite;
}
.right { display: flex; gap: 10px; }
</style>
