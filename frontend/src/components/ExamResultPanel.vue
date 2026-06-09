<script setup lang="ts">
import { computed } from 'vue'
import CountUp from './CountUp.vue'
import AppIcon from './AppIcon.vue'
import type { ExamResult } from '../types'

const props = defineProps<{ result: ExamResult }>()

const maxDist = computed(() =>
  Math.max(1, ...props.result.score_distribution.map((d) => d.count))
)
</script>

<template>
  <div class="card glass fade-up">
    <div class="card-head">
      <span class="ico"><AppIcon name="chart" :size="22" /></span>
      <div>
        <div class="card-title">阅卷分析</div>
        <div class="card-sub">智能阅卷报告</div>
      </div>
    </div>

    <div class="summary">
      <div class="sum-item">
        <div class="sum-num"><CountUp :value="result.summary.average" :decimals="1" /></div>
        <div class="sum-label">平均分</div>
      </div>
      <div class="sum-item">
        <div class="sum-num green"><CountUp :value="result.summary.pass_rate" :decimals="1" />%</div>
        <div class="sum-label">及格率</div>
      </div>
      <div class="sum-item">
        <div class="sum-num gold"><CountUp :value="result.summary.highest" /></div>
        <div class="sum-label">最高分</div>
      </div>
      <div class="sum-item">
        <div class="sum-num"><CountUp :value="result.summary.lowest" /></div>
        <div class="sum-label">最低分</div>
      </div>
    </div>

    <div class="dist">
      <div class="dist-title">分数分布</div>
      <div class="dist-bars">
        <div v-for="d in result.score_distribution" :key="d.range" class="dist-col">
          <div class="bar-wrap">
            <div class="bar" :style="{ height: (d.count / maxDist) * 100 + '%' }">
              <span class="bar-val">{{ d.count }}</span>
            </div>
          </div>
          <div class="bar-label">{{ d.range }}</div>
        </div>
      </div>
    </div>

    <div class="weak">
      <div class="weak-title">薄弱点 · 教学建议</div>
      <div v-for="(w, i) in result.weak_points" :key="i" class="weak-item">
        <div class="weak-row">
          <span class="weak-rank">{{ i + 1 }}</span>
          <span class="weak-name">{{ w.name }}</span>
          <span class="weak-rate mono">{{ Math.round(w.error_rate * 100) }}% 错误率</span>
        </div>
        <div class="weak-bar-bg">
          <div class="weak-bar" :style="{ width: w.error_rate * 100 + '%' }"></div>
        </div>
        <div v-if="w.comment" class="weak-comment">{{ w.comment }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { padding: 20px 22px; }
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.card-head .ico { color: var(--cyan); display: grid; place-items: center; }
.card-title { font-size: 17px; font-weight: 800; }
.card-sub { font-size: 11px; color: var(--muted); letter-spacing: 1px; }

.summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.sum-item {
  text-align: center;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 14px 6px;
}
.sum-num { font-size: 28px; font-weight: 800; }
.sum-num.green { color: var(--teal); }
.sum-num.gold { color: var(--gold); }
.sum-label { font-size: 12px; color: var(--muted); margin-top: 6px; }

.dist { margin-bottom: 20px; }
.dist-title,
.weak-title { font-size: 13px; color: var(--aqua); margin-bottom: 12px; font-weight: 700; }
.dist-bars { display: flex; align-items: flex-end; gap: 14px; height: 110px; }
.dist-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.bar-wrap { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; }
.bar {
  width: 70%;
  min-height: 6px;
  border-radius: 8px 8px 0 0;
  background: linear-gradient(180deg, var(--cyan), var(--violet));
  position: relative;
  transition: height 0.8s cubic-bezier(0.22, 1, 0.36, 1);
  animation: fadeUp 0.6s ease both;
}
.bar-val { position: absolute; top: -20px; left: 50%; transform: translateX(-50%); font-size: 13px; font-weight: 700; }
.bar-label { font-size: 11px; color: var(--muted); margin-top: 8px; }

.weak-item { margin-bottom: 14px; }
.weak-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.weak-rank {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
  background: rgba(248, 113, 113, 0.18);
  color: var(--danger);
}
.weak-name { font-size: 15px; font-weight: 600; flex: 1; }
.weak-rate { font-size: 12px; color: var(--danger); }
.weak-bar-bg { height: 7px; border-radius: 4px; background: rgba(255, 255, 255, 0.07); overflow: hidden; }
.weak-bar {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--gold), var(--danger));
  transition: width 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}
.weak-comment { font-size: 12px; color: var(--muted); margin-top: 6px; line-height: 1.4; }
</style>
