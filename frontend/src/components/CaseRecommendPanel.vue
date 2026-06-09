<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { Recommendation } from '../types'

defineProps<{ recommendation: Recommendation }>()
</script>

<template>
  <div class="card glass fade-up">
    <div class="card-head">
      <span class="ico"><AppIcon name="bulb" :size="22" /></span>
      <div>
        <div class="card-title">学习目标与病例推荐</div>
        <div class="card-sub">下一步学习建议</div>
      </div>
    </div>

    <div class="goal">
      <span class="goal-ico"><AppIcon name="target" :size="20" /></span>
      <span>{{ recommendation.next_goal }}</span>
    </div>

    <div class="cases">
      <div
        v-for="(c, i) in recommendation.cases"
        :key="c.id"
        class="case glass"
        :style="{ animationDelay: i * 70 + 'ms' }"
      >
        <div class="case-top">
          <span class="case-no">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="case-diff" :class="c.difficulty">{{ c.difficulty }}</span>
        </div>
        <div class="case-title">{{ c.title }}</div>
        <div class="case-focus">聚焦 · {{ c.focus }}</div>
        <div class="case-tags">
          <span v-for="t in c.tags" :key="t" class="tag">{{ t }}</span>
        </div>
        <div class="case-foot">
          <span class="time"><AppIcon name="clock" :size="14" /> {{ c.est_minutes }} 分钟</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { padding: 20px 22px; }
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.card-head .ico { color: var(--teal); display: grid; place-items: center; }
.card-title { font-size: 17px; font-weight: 800; }
.card-sub { font-size: 11px; color: var(--muted); letter-spacing: 1px; }

.goal {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: 14px;
  background: linear-gradient(92deg, rgba(45, 212, 191, 0.16), rgba(56, 189, 248, 0.12));
  border: 1px solid rgba(45, 212, 191, 0.25);
  font-size: 15px;
  line-height: 1.5;
  margin-bottom: 18px;
}
.goal-ico { color: var(--teal); display: grid; place-items: center; }

.cases { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.case {
  padding: 16px;
  border-radius: 16px;
  animation: fadeUp 0.5s ease both;
  transition: transform 0.2s ease;
}
.case:hover { transform: translateY(-4px); }
.case-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.case-no { font-size: 20px; font-weight: 800; color: var(--aqua); }
.case-diff {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--line);
  color: var(--muted);
}
.case-diff.初级 { color: var(--teal); border-color: rgba(45, 212, 191, 0.4); }
.case-diff.中级 { color: var(--cyan); border-color: rgba(56, 189, 248, 0.4); }
.case-diff.高级 { color: var(--pink); border-color: rgba(244, 114, 182, 0.4); }
.case-title { font-size: 15px; font-weight: 700; line-height: 1.4; margin-bottom: 8px; }
.case-focus { font-size: 12.5px; color: var(--muted); margin-bottom: 10px; }
.case-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.tag {
  font-size: 11px;
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.1);
  color: var(--cyan);
  border: 1px solid rgba(56, 189, 248, 0.2);
}
.case-foot { font-size: 12px; color: var(--muted); }
.case-foot .time { display: inline-flex; align-items: center; gap: 5px; }
</style>
