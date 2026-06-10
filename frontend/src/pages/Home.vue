<script setup lang="ts">
import { RouterLink } from 'vue-router'
import SharkAvatar from '../components/SharkAvatar.vue'
import AppIcon from '../components/AppIcon.vue'

const entries = [
  {
    to: '/screen',
    icon: 'monitor',
    title: '展厅大屏',
    sub: '实时演示画面',
    desc: '动态展示助教动作、阶段成果与最终学情分析',
    accent: 'a'
  },
  {
    to: '/avatar',
    icon: 'shark',
    title: '数字助教',
    sub: '语音对话',
    desc: '会随对话灵动变化的助教鲨鲨 · 仅需动口说话',
    accent: 'b'
  },
  {
    to: '/control',
    icon: 'sliders',
    title: '现场控制台',
    sub: '操控与兑底',
    desc: '推进流程、一键跳转、随时掌控演示节奏',
    accent: 'c'  },
  {
    to: '/tools',
    icon: 'wrench',
    title: '工具箱验证',
    sub: '真实接口测试',
    desc: '查看已接入的平台工具 · 一键点测真实教学平台 Agent',
    accent: 'd'  }
]
</script>

<template>
  <div class="home">
    <div class="bg-aurora"></div>
    <div class="bg-grid"></div>

    <div class="hero">
      <div class="hero-shark"><SharkAvatar state="speaking" :mouth="0.4" /></div>
      <h1 class="title-grad">巨鲨医用教学助手</h1>
      <p class="tagline">听懂教学需求 · 一句话安排考试 · 自动阅卷与学情分析 · 全程语音陪伴</p>
    </div>

    <div class="entries">
      <RouterLink v-for="e in entries" :key="e.to" :to="e.to" class="entry glass" :class="`ac-${e.accent}`">
        <div class="e-icon"><AppIcon :name="e.icon" :size="34" /></div>
        <div class="e-title">{{ e.title }}</div>
        <div class="e-sub">{{ e.sub }}</div>
        <div class="e-desc">{{ e.desc }}</div>
        <div class="e-go">进入 <AppIcon name="arrow" :size="16" /></div>
      </RouterLink>
    </div>

    <div class="tip glass">
      <span class="tip-dot"></span>
      推荐：大屏与数字助教分屏展示，控制台用平板或副屏操作。先在数字助教页点击「开始对话」开启语音。
    </div>
  </div>
</template>

<style scoped>
.home {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 36px;
  padding: 30px;
  overflow: hidden;
}
.hero { position: relative; z-index: 1; text-align: center; }
.hero-shark { width: 220px; height: 220px; margin: 0 auto; }
.hero h1 { font-size: 46px; margin: 8px 0 6px; letter-spacing: 1px; }
.tagline { color: var(--muted); font-size: 16px; letter-spacing: 1px; margin: 0; }

.entries {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, 250px);
  gap: 18px;
}
.entry {
  padding: 28px 26px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: transform 0.22s ease, box-shadow 0.22s ease;
  cursor: pointer;
}
.entry:hover { transform: translateY(-8px); box-shadow: 0 30px 70px rgba(4, 12, 40, 0.6); }
.e-icon {
  width: 60px;
  height: 60px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: var(--cyan);
  background: var(--glass-2);
  border: 1px solid var(--line);
  margin-bottom: 10px;
}
.e-title { font-size: 24px; font-weight: 800; }
.e-sub { font-size: 12px; color: var(--muted); letter-spacing: 2px; text-transform: uppercase; }
.e-desc { font-size: 13.5px; color: var(--muted); line-height: 1.5; margin-top: 8px; min-height: 40px; }
.e-go { margin-top: 14px; color: var(--aqua); font-weight: 700; display: inline-flex; align-items: center; gap: 6px; }
.ac-a:hover { border-color: rgba(56, 189, 248, 0.5); }
.ac-b:hover { border-color: rgba(45, 212, 191, 0.5); }
.ac-c:hover { border-color: rgba(139, 92, 246, 0.5); }
.ac-d:hover { border-color: rgba(244, 114, 182, 0.5); }

.tip {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 22px;
  font-size: 13.5px;
  color: var(--muted);
  max-width: 920px;
}
.tip-dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: var(--aqua); box-shadow: 0 0 12px var(--aqua);
  animation: pulse 1.4s infinite; flex: none;
}
</style>
