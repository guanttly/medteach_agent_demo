<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useDemoStore } from '../stores/demo'
import SharkAvatar from '../components/SharkAvatar.vue'
import TopStatusBar from '../components/TopStatusBar.vue'
import WorkflowPanel from '../components/WorkflowPanel.vue'
import ExamPlanCard from '../components/ExamPlanCard.vue'
import ExamProgressPanel from '../components/ExamProgressPanel.vue'
import ExamResultPanel from '../components/ExamResultPanel.vue'
import CaseRecommendPanel from '../components/CaseRecommendPanel.vue'
import EventTicker from '../components/EventTicker.vue'
import AppIcon from '../components/AppIcon.vue'

const store = useDemoStore()
const {
  sharkState,
  assistantText,
  userText,
  workflow,
  examPlan,
  examPreview,
  students,
  progress,
  result,
  recommendation,
  events
} = storeToRefs(store)

const stageRef = ref<HTMLElement | null>(null)
watch(
  () => [examPreview.value, progress.value, result.value, recommendation.value],
  () => {
    nextTick(() => {
      stageRef.value?.scrollTo({ top: stageRef.value.scrollHeight, behavior: 'smooth' })
    })
  },
  { deep: true }
)

const TYPE_LABEL: Record<string, string> = {
  single_choice: '单选',
  multiple_choice: '多选',
  case_analysis: '病例'
}
</script>

<template>
  <div class="screen">
    <div class="bg-aurora"></div>
    <div class="bg-grid"></div>

    <TopStatusBar />

    <div class="grid">
      <!-- 左栏：助教形象 + 字幕 + 学员 + 事件流 -->
      <aside class="col-left">
        <div class="presence glass">
          <div class="mini-shark">
            <SharkAvatar :state="sharkState" :mouth="store.mouth" />
          </div>
          <div class="dialog">
            <transition name="v">
              <div v-if="userText" class="user-line">
                <span class="u-tag">讲师</span>{{ userText }}
              </div>
            </transition>
            <div class="sub-line">
              <span class="s-tag">鲨鲨</span>
              <span class="s-text" :class="{ speaking: sharkState === 'speaking' }">{{ assistantText }}</span>
            </div>
          </div>
        </div>

        <transition name="v">
          <div v-if="students" class="students glass">
            <div class="st-head">现场学员 · {{ students.total }} 人</div>
            <div class="st-list">
              <div v-for="s in students.students" :key="s.id" class="st-item">
                <span class="st-ava" :style="{ background: s.color }">{{ s.name.charAt(0) }}</span>
                <span class="st-name">{{ s.name }}</span>
              </div>
            </div>
          </div>
        </transition>

        <EventTicker :events="events" class="ticker-fill" />
      </aside>

      <!-- 主区：工作流 + 阶段成果 -->
      <main class="col-main">
        <WorkflowPanel :steps="workflow" />

        <div class="stage" ref="stageRef">
          <transition name="v">
            <ExamPlanCard v-if="examPlan" :plan="examPlan" class="span-1" />
          </transition>

          <transition name="v">
            <div v-if="examPreview" class="card glass fade-up span-1">
              <div class="card-head">
                <span class="ico"><AppIcon name="document" :size="22" /></span>
                <div>
                  <div class="card-title">试卷预览</div>
                  <div class="card-sub">{{ examPreview.exam_name }}</div>
                </div>
              </div>
              <div class="q-list">
                <div v-for="q in examPreview.sample_questions" :key="q.no" class="q-item">
                  <div class="q-top">
                    <span class="q-type">{{ TYPE_LABEL[q.type] || q.type_label }}</span>
                    <span class="q-no">第 {{ q.no }} 题 · {{ q.score }} 分</span>
                  </div>
                  <div class="q-stem">{{ q.stem }}</div>
                </div>
              </div>
            </div>
          </transition>

          <transition name="v">
            <ExamProgressPanel
              v-if="progress"
              :progress="progress"
              :total="students?.total || examPlan?.student_count || 8"
              class="span-2"
            />
          </transition>

          <transition name="v">
            <ExamResultPanel v-if="result" :result="result" class="span-2" />
          </transition>

          <transition name="v">
            <CaseRecommendPanel v-if="recommendation" :recommendation="recommendation" class="span-2" />
          </transition>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.screen {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 14px;
  overflow: hidden;
}
.grid {
  position: relative;
  z-index: 1;
  flex: 1;
  display: grid;
  grid-template-columns: 350px 1fr;
  gap: 14px;
  min-height: 0;
}

.col-left { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.presence { padding: 16px 16px 18px; display: flex; flex-direction: column; align-items: center; }
.mini-shark {
  width: 100%;
  height: 210px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: radial-gradient(circle at 50% 46%, rgba(56, 189, 248, 0.14), transparent 70%);
  overflow: hidden;
}
.dialog { width: 100%; }
.user-line {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(56, 189, 248, 0.1);
  font-size: 13px;
}
.u-tag, .s-tag { font-size: 11px; color: var(--aqua); margin-right: 8px; }
.sub-line {
  margin-top: 10px;
  font-size: 14.5px;
  line-height: 1.5;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--line);
}
.s-text.speaking::after { content: '▍'; color: var(--aqua); animation: pulse 0.7s steps(1) infinite; }

.students { padding: 14px; }
.st-head { font-size: 14px; font-weight: 700; margin-bottom: 10px; }
.st-list { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.st-item { display: flex; align-items: center; gap: 8px; }
.st-ava {
  width: 26px; height: 26px; border-radius: 50%;
  display: grid; place-items: center;
  font-size: 13px; font-weight: 700; color: #06203a;
}
.st-name { font-size: 13px; }
.ticker-fill { flex: 1; min-height: 120px; }

.col-main { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.stage {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-content: start;
  padding-right: 4px;
}
.span-1 { grid-column: span 1; }
.span-2 { grid-column: span 2; }

.card { padding: 20px 22px; }
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.card-head .ico { color: var(--cyan); display: grid; place-items: center; }
.card-title { font-size: 17px; font-weight: 800; }
.card-sub { font-size: 11px; color: var(--muted); letter-spacing: 0.5px; }
.q-list { display: flex; flex-direction: column; gap: 10px; }
.q-item {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--line);
}
.q-top { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.q-type {
  font-size: 11px; padding: 2px 9px; border-radius: 6px;
  background: rgba(56, 189, 248, 0.16); color: var(--cyan); font-weight: 700;
}
.q-no { font-size: 11px; color: var(--muted); }
.q-stem { font-size: 13.5px; line-height: 1.5; }
</style>
