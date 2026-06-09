<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ name: string; size?: number | string; stroke?: number }>(),
  { size: 22, stroke: 1.9 }
)

/** 线性图标库（24x24，currentColor 描边），统一替代 emoji。 */
const STROKE: Record<string, string[]> = {
  // 识别教学任务
  target: [
    'M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0 -20',
    'M12 7a5 5 0 1 0 0 10a5 5 0 1 0 0 -10',
    'M12 11.4a.6 .6 0 1 0 0 1.2a.6 .6 0 1 0 0 -1.2'
  ],
  // 考试方案 / 计划清单
  clipboard: [
    'M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2',
    'M9 2.5h6a1 1 0 0 1 1 1V5a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z',
    'M8.5 12H16',
    'M8.5 16H16'
  ],
  // 工具调用成功
  wrench: [
    'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.6-3.6a6 6 0 0 1-7.9 7.9l-6.5 6.5a2.1 2.1 0 0 1-3-3l6.5-6.5a6 6 0 0 1 7.9-7.9z'
  ],
  // 试卷预览 / 文档
  document: [
    'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z',
    'M14 3v5h5',
    'M9 13h6',
    'M9 17h6'
  ],
  // 下发考试 / 发布
  send: ['M22 2 11 13', 'M22 2 15 22 11 13 2 9z'],
  // 阅卷分析 / 数据
  chart: ['M4 4v16h16', 'M8 16v-4', 'M13 16V8', 'M18 16v-7'],
  // 学习目标 / 病例推荐
  bulb: [
    'M9.5 18h5',
    'M10 22h4',
    'M15.1 14c.2-1 .7-1.7 1.4-2.5A4.6 4.6 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .3 2.2 1.5 3.5.7.8 1.2 1.5 1.4 2.5'
  ],
  // 完成
  check: ['M20 6 9 17l-5-5'],
  // 答题进度 / 实时信号
  signal: [
    'M4.9 19.1A10 10 0 0 1 4.9 4.9',
    'M7.8 16.2a6 6 0 0 1 0-8.4',
    'M16.2 7.8a6 6 0 0 1 0 8.4',
    'M19.1 4.9a10 10 0 0 1 0 14.2',
    'M12 10a2 2 0 1 0 0 4a2 2 0 1 0 0 -4'
  ],
  // 时间
  clock: ['M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0 -20', 'M12 6.5V12l3.5 2'],
  // 展厅大屏
  monitor: [
    'M3 4.5h18a1 1 0 0 1 1 1V16a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1z',
    'M8.5 21h7',
    'M12 17v4'
  ],
  // 控制台
  sliders: [
    'M4 21v-7', 'M4 10V3', 'M12 21v-9', 'M12 8V3', 'M20 21v-5', 'M20 12V3',
    'M2 14h4', 'M10 8h4', 'M18 16h4'
  ],
  // 麦克风
  mic: [
    'M12 2.5a3 3 0 0 0-3 3V11a3 3 0 0 0 6 0V5.5a3 3 0 0 0-3-3z',
    'M19 10.5V11a7 7 0 0 1-14 0v-.5',
    'M12 18v3.5',
    'M8.5 21.5h7'
  ],
  // 提醒（兜底）
  alert: ['M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z', 'M12 9v4.5', 'M12 17.5h.01'],
  // 箭头
  arrow: ['M5 12h13', 'M13 6l6 6-6 6'],
  // 开始 / 播放
  play: ['M7 4.5v15l13-7.5z'],
  // 现场学员
  users: [
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2',
    'M9 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8',
    'M22 21v-2a4 4 0 0 0-3-3.85',
    'M16 3.15A4 4 0 0 1 16 11'
  ],
  // 语音播报 / 声音
  sound: [
    'M11 5 6 9H3a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h3l5 4z',
    'M15.5 8.5a5 5 0 0 1 0 7',
    'M18.5 5.5a9 9 0 0 1 0 13'
  ]
}
const paths = computed(() => STROKE[props.name] ?? [])
const isShark = computed(() => props.name === 'shark')
</script>

<template>
  <svg
    v-if="isShark"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    class="icon icon-shark"
    aria-hidden="true"
  >
    <!-- 品牌标记：圆润正面小鲨鱼 -->
    <path
      d="M12 3.6c-1.6-2-3.6-1.4-3 .7C6 5.3 3.6 8 3.6 11.4c0 4.5 3.8 8 8.4 8s8.4-3.5 8.4-8c0-3.4-2.4-6.1-5.4-7.1.6-2.1-1.4-2.7-3-.7z"
      fill="currentColor"
    />
    <ellipse cx="9.2" cy="11.6" rx="1.7" ry="2" fill="#fff" />
    <ellipse cx="14.8" cy="11.6" rx="1.7" ry="2" fill="#fff" />
    <circle cx="9.5" cy="12" r=".95" fill="#0c2138" />
    <circle cx="14.5" cy="12" r=".95" fill="#0c2138" />
    <path d="M9.8 15.4c.9 1.1 3.5 1.1 4.4 0" fill="none" stroke="#0c2138" stroke-width="1.1" stroke-linecap="round" />
  </svg>

  <svg
    v-else
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    :stroke-width="stroke"
    stroke="currentColor"
    stroke-linecap="round"
    stroke-linejoin="round"
    class="icon"
    aria-hidden="true"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<style scoped>
.icon {
  display: inline-block;
  vertical-align: middle;
  flex: none;
}
</style>
