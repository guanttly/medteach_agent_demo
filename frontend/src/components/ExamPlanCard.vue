<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { ExamPlan } from '../types'

defineProps<{ plan: ExamPlan }>()
</script>

<template>
  <div class="card glass fade-up">
    <div class="card-head">
      <span class="ico"><AppIcon name="clipboard" :size="22" /></span>
      <div>
        <div class="card-title">考试方案</div>
        <div class="card-sub">为本次教学定制</div>
      </div>
    </div>

    <div class="exam-name">{{ plan.exam_name }}</div>

    <div class="meta-row">
      <span class="chip">{{ plan.student_group }} · {{ plan.student_count }} 人</span>
      <span class="chip">{{ plan.duration_minutes }} 分钟</span>
      <span class="chip">难度 {{ plan.difficulty }}</span>
    </div>

    <div class="tiles">
      <div class="tile">
        <div class="tile-num">{{ plan.question_structure.single_choice }}</div>
        <div class="tile-label">单选题</div>
      </div>
      <div class="tile">
        <div class="tile-num">{{ plan.question_structure.multiple_choice }}</div>
        <div class="tile-label">多选题</div>
      </div>
      <div class="tile">
        <div class="tile-num">{{ plan.question_structure.case_analysis }}</div>
        <div class="tile-label">病例分析</div>
      </div>
      <div class="tile accent">
        <div class="tile-num">{{ plan.total_score }}</div>
        <div class="tile-label">总分</div>
      </div>
    </div>

    <div class="grading">
      <span class="g-label">阅卷方式</span>{{ plan.grading }}
    </div>
  </div>
</template>

<style scoped>
.card { padding: 20px 22px; }
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.card-head .ico { color: var(--cyan); display: grid; place-items: center; }
.card-title { font-size: 17px; font-weight: 800; }
.card-sub { font-size: 11px; color: var(--muted); letter-spacing: 1px; }
.exam-name {
  font-size: 22px;
  font-weight: 800;
  margin-bottom: 14px;
  background: linear-gradient(92deg, var(--aqua), var(--cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.meta-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.tile {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 8px;
  text-align: center;
}
.tile.accent {
  background: linear-gradient(160deg, rgba(56, 189, 248, 0.18), rgba(139, 92, 246, 0.18));
  border-color: rgba(56, 189, 248, 0.3);
}
.tile-num { font-size: 30px; font-weight: 800; line-height: 1; }
.tile-label { font-size: 12px; color: var(--muted); margin-top: 8px; }
.grading {
  margin-top: 16px;
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.5;
}
.g-label {
  display: inline-block;
  margin-right: 10px;
  color: var(--aqua);
  font-size: 12px;
}
</style>
