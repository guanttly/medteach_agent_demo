<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { WorkflowStep } from '../types'

defineProps<{ steps: WorkflowStep[] }>()
</script>

<template>
  <div class="workflow glass">
    <div class="wf-head">
      <span class="wf-title">智能助教工作流</span>
      <span class="wf-sub">全程 · 10 个环节</span>
    </div>
    <div class="wf-track">
      <div
        v-for="(s, i) in steps"
        :key="s.id"
        class="wf-step"
        :class="`is-${s.status}`"
      >
        <div class="node">
          <span v-if="s.status === 'running'" class="spinner"></span>
          <AppIcon v-else-if="s.status === 'completed'" name="check" :size="18" />
          <AppIcon v-else-if="s.status === 'fallback'" name="alert" :size="17" />
          <span v-else class="ico">{{ i + 1 }}</span>
        </div>
        <div class="label">{{ s.label }}</div>
        <div v-if="i < steps.length - 1" class="connector"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow { padding: 18px 22px; }
.wf-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px; }
.wf-title { font-size: 17px; font-weight: 800; }
.wf-sub { font-size: 12px; color: var(--muted); letter-spacing: 1px; }
.wf-track {
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 2px;
}
.wf-step {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding-top: 6px;
}
.node {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 15px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.05);
  border: 2px solid var(--line);
  z-index: 2;
  transition: all 0.4s ease;
}
.label {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.35;
  max-width: 84px;
  transition: color 0.4s ease;
}
.connector {
  position: absolute;
  top: 26px;
  left: 50%;
  width: 100%;
  height: 3px;
  background: var(--line);
  z-index: 1;
  transition: background 0.5s ease;
}

/* running */
.is-running .node {
  color: var(--aqua);
  border-color: var(--aqua);
  box-shadow: 0 0 0 6px rgba(34, 211, 238, 0.12), 0 0 22px rgba(34, 211, 238, 0.5);
  background: rgba(34, 211, 238, 0.1);
}
.is-running .label { color: var(--text); font-weight: 700; }
.spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 3px solid rgba(34, 211, 238, 0.25);
  border-top-color: var(--aqua);
  animation: spin 0.8s linear infinite;
}

/* completed */
.is-completed .node {
  color: #04122e;
  background: linear-gradient(135deg, var(--teal), var(--cyan));
  border-color: transparent;
}
.is-completed .label { color: var(--text); }
.is-completed .connector { background: linear-gradient(90deg, var(--teal), var(--cyan)); }

/* fallback */
.is-fallback .node {
  color: #2a1d02;
  background: var(--gold);
  border-color: transparent;
}
.is-fallback .connector { background: var(--gold); }

/* failed */
.is-failed .node {
  color: #fff;
  background: var(--danger);
  border-color: transparent;
}
</style>
