<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import type { BusinessData } from '../types'

const props = defineProps<{ business: BusinessData }>()

const module = computed(() => props.business.module)
const data = computed<any>(() => props.business.data || {})
const fallback = computed(() => props.business.fallback)

const ICONS: Record<string, string> = {
  data_board: 'chart',
  list_exams: 'clipboard',
  list_questions: 'document',
  list_teaching: 'monitor'
}
const icon = computed(() => ICONS[module.value] || 'sliders')

const boardMetrics = computed(() => {
  const exam = data.value.exam || {}
  const teaching = data.value.teaching || {}
  return [
    { label: '考试', value: exam.exam_num ?? 0 },
    { label: '试卷', value: exam.paper_num ?? 0 },
    { label: '题目', value: exam.question_num ?? 0 },
    { label: '平均分', value: exam.exam_avg ?? 0 },
    { label: '教学场次', value: teaching.education_num ?? 0 },
    { label: '直播', value: teaching.livestream_num ?? 0 }
  ]
})
const boardDist = computed(() => data.value?.exam?.question_type_dist || [])
</script>

<template>
  <div class="card glass fade-up">
    <div class="card-head">
      <span class="ico"><AppIcon :name="icon" :size="22" /></span>
      <div class="head-text">
        <div class="card-title">{{ business.title }}</div>
        <div class="card-sub">教学平台 · 业务模块</div>
      </div>
      <span class="src" :class="fallback ? 'is-fb' : 'is-live'">
        {{ fallback ? '演示数据' : '真实平台数据' }}
      </span>
    </div>

    <!-- 数据看板 -->
    <template v-if="module === 'data_board'">
      <div class="metrics">
        <div v-for="m in boardMetrics" :key="m.label" class="metric">
          <div class="m-val">{{ m.value }}</div>
          <div class="m-label">{{ m.label }}</div>
        </div>
      </div>
      <div v-if="boardDist.length" class="dist">
        <span v-for="d in boardDist" :key="d.name" class="dist-tag">{{ d.name }} · {{ d.num }}</span>
      </div>
    </template>

    <!-- 考试列表 -->
    <template v-else-if="module === 'list_exams'">
      <div class="count">共 {{ data.total ?? (data.exams || []).length }} 场考试</div>
      <div class="rows">
        <div v-for="e in (data.exams || []).slice(0, 6)" :key="e.exam_id" class="row">
          <span class="r-main">{{ e.name }}</span>
          <span class="r-meta">{{ e.begin_time }} · {{ e.minutes }}分钟</span>
          <span class="r-tag">{{ e.status }}</span>
        </div>
      </div>
    </template>

    <!-- 题库 -->
    <template v-else-if="module === 'list_questions'">
      <div class="count">题库共 {{ data.total ?? (data.questions || []).length }} 道题</div>
      <div class="rows">
        <div v-for="q in (data.questions || []).slice(0, 6)" :key="q.id" class="row">
          <span class="r-main">{{ q.content || '题目' }}</span>
          <span class="r-tag">{{ q.type }}</span>
          <span class="r-meta">{{ q.organ }} · {{ q.difficulty }}</span>
        </div>
      </div>
    </template>

    <!-- 教学计划 -->
    <template v-else-if="module === 'list_teaching'">
      <div class="count">共 {{ data.total ?? (data.plans || []).length }} 项教学安排</div>
      <div class="rows">
        <div v-for="p in (data.plans || []).slice(0, 6)" :key="p.id" class="row">
          <span class="r-main">{{ p.subject }}</span>
          <span class="r-tag">{{ p.type }}</span>
          <span class="r-meta">{{ p.education_time }} · {{ p.lecturer }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.card { padding: 20px 22px; }
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.card-head .ico { color: var(--cyan); display: grid; place-items: center; }
.head-text { flex: 1; min-width: 0; }
.card-title { font-size: 17px; font-weight: 800; }
.card-sub { font-size: 11px; color: var(--muted); letter-spacing: 1px; }
.src {
  flex: none;
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  white-space: nowrap;
}
.src.is-live { color: var(--teal); border-color: rgba(45, 212, 191, 0.4); background: rgba(45, 212, 191, 0.1); }
.src.is-fb { color: #fbbf24; border-color: rgba(251, 191, 36, 0.45); background: rgba(251, 191, 36, 0.1); }

.metrics { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.metric {
  padding: 14px 10px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line);
  text-align: center;
}
.m-val { font-size: 24px; font-weight: 800; color: var(--aqua); }
.m-label { font-size: 12px; color: var(--muted); margin-top: 4px; }
.dist { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.dist-tag {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: var(--cyan);
}

.count { font-size: 13px; color: var(--muted); margin-bottom: 12px; }
.rows { display: flex; flex-direction: column; gap: 8px; }
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--line);
}
.r-main {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.r-tag {
  flex: none;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(45, 212, 191, 0.12);
  border: 1px solid rgba(45, 212, 191, 0.3);
  color: var(--teal);
}
.r-meta { flex: none; font-size: 12px; color: var(--muted); }
</style>
