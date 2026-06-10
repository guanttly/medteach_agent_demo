<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useDemoStore } from '../stores/demo'
import SharkAvatar from '../components/SharkAvatar.vue'
import EventTicker from '../components/EventTicker.vue'
import AppIcon from '../components/AppIcon.vue'

const store = useDemoStore()
const { stateLabel, sharkState, mode, coreStatus, connected, fallbackActive, agentSource, agentProvider, events, needConfirm, confirmationType } =
  storeToRefs(store)

const msg = ref('')

const JUMPS = [
  { label: '生成方案', target: 'PLAN_PROPOSED' },
  { label: '试卷预览', target: 'EXAM_PREVIEW_READY' },
  { label: '下发考试', target: 'EXAM_PUBLISHED' },
  { label: '成绩分析', target: 'REPORT_READY' },
  { label: '病例推荐', target: 'DONE' }
]

// 业务模块语音指令：模拟现场讲师语音，触发各大教学业务（真实工具箱取数）。
const BUSINESS = [
  { label: '数据看板', icon: 'chart', text: '看一下数据看板' },
  { label: '学员名册', icon: 'users', text: '现场有哪些学员' },
  { label: '考试列表', icon: 'clipboard', text: '现在有哪些考试' },
  { label: '成绩分析', icon: 'chart', text: '看一下考试成绩' },
  { label: '题库', icon: 'document', text: '题库里有哪些题' },
  { label: '病例推荐', icon: 'bulb', text: '推荐几个复训病例' },
  { label: '教学计划', icon: 'monitor', text: '最近有哪些教学计划' }
]

function sendMsg() {
  const t = msg.value.trim()
  if (!t) return
  store.sendMessage(t)
  msg.value = ''
}
</script>

<template>
  <div class="control">
    <div class="bg-aurora"></div>

    <header class="ctrl-top glass">
      <div class="ct-left">
        <span class="logo"><AppIcon name="sliders" :size="24" /></span>
        <div>
          <div class="ct-title">现场控制台</div>
          <div class="ct-sub">演示操控与兜底工具</div>
        </div>
      </div>
      <div class="ct-status">
        <span class="chip"><i class="dot" :class="connected ? 'ok' : 'err'"></i>{{ connected ? '已连接' : '重连中' }}</span>
        <span class="chip">阶段 · {{ stateLabel }}</span>
        <span class="chip">接口 · {{ mode }}</span>
        <span class="chip agent-chip" :class="fallbackActive ? 'is-fallback' : 'is-live'">
          <i class="dot" :class="fallbackActive ? 'warn' : 'ok'"></i>智能体 · {{ fallbackActive ? '兜底' : '正常' }}
        </span>
      </div>
    </header>

    <div class="ctrl-grid">
      <div class="left-col">
        <section class="panel glass">
          <h3>智能体接入状态</h3>
          <div class="agent-status" :class="fallbackActive ? 'is-fallback' : 'is-live'">
            <span class="agent-badge">{{ fallbackActive ? '兜底 Fallback' : '正常 · 真实接入' }}</span>
            <div class="agent-meta">
              <div class="agent-line"><span>来源</span>{{ agentSource === 'llm' ? '大模型（CC + DeepSeek）' : '本地确定性编排' }}</div>
              <div class="agent-line"><span>引擎</span>{{ agentProvider }}</div>
              <div class="agent-line"><span>Core</span>{{ coreStatus }}</div>
            </div>
          </div>
          <p class="agent-tip">填入 DeepSeek API Key 后自动转「正常」；调用失败会自动回退「兜底」。</p>
        </section>

        <section class="panel glass">
          <h3>主流程推进</h3>
          <div class="btns">
            <button class="btn primary" @click="store.preset('arrange')"><AppIcon name="play" :size="16" /> 安排考试</button>
            <button class="btn" :class="{ primary: needConfirm && confirmationType === 'confirm_plan' }" @click="store.confirm('confirm_plan')">确认方案</button>
            <button class="btn" :class="{ primary: needConfirm && confirmationType === 'confirm_publish' }" @click="store.publish()">下发考试</button>
            <button class="btn" @click="store.simulateSubmit()">模拟全部提交</button>
            <button class="btn warn" @click="store.reset()">重置演示</button>
          </div>
        </section>

        <section class="panel glass">
          <h3>强制跳转（兜底）</h3>
          <div class="btns">
            <button v-for="(j, i) in JUMPS" :key="j.target" class="btn ghost" @click="store.controlStep(j.target)">
              {{ i + 1 }} · {{ j.label }}
            </button>
          </div>
        </section>

        <section class="panel glass">
          <h3>业务模块（语音指令 · 真实平台数据）</h3>
          <div class="btns">
            <button v-for="b in BUSINESS" :key="b.label" class="btn ghost" @click="store.sendMessage(b.text)">
              <AppIcon :name="b.icon" :size="15" /> {{ b.label }}
            </button>
          </div>
          <p class="agent-tip">点击即模拟现场语音指令，智能体经对应 Skill 调用教学平台工具箱取真实数据。</p>
        </section>

        <section class="panel glass">
          <h3>接口模式</h3>
          <div class="btns">
            <button class="btn" :class="{ primary: mode === 'mock' }" @click="store.setMode('mock')">Mock</button>
            <button class="btn" :class="{ primary: mode === 'hybrid' }" @click="store.setMode('hybrid')">Hybrid</button>
            <button class="btn" :class="{ primary: mode === 'real' }" @click="store.setMode('real')">Real</button>
          </div>
        </section>

        <section class="panel glass">
          <h3>自定义指令</h3>
          <div class="msg-row">
            <input v-model="msg" class="msg-input" placeholder="向智能体发送任意指令…" @keydown.enter="sendMsg" />
            <button class="btn primary" @click="sendMsg">发送</button>
          </div>
        </section>
      </div>

      <div class="right-col">
        <section class="panel glass shark-panel">
          <div class="mini"><SharkAvatar :state="sharkState" :mouth="store.mouth" /></div>
          <div class="shark-state">{{ sharkState }}</div>
        </section>
        <EventTicker :events="events" class="log" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.control {
  position: relative;
  height: 100vh;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}
.ctrl-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px;
}
.ct-left { display: flex; align-items: center; gap: 12px; }
.logo { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 12px; color: var(--violet); background: var(--glass-2); border: 1px solid var(--line); }
.ct-title { font-size: 18px; font-weight: 800; }
.ct-sub { font-size: 12px; color: var(--muted); }
.ct-status { display: flex; gap: 10px; flex-wrap: wrap; }
.agent-chip.is-live { color: var(--aqua); border-color: rgba(34, 211, 238, 0.45); }
.agent-chip.is-fallback { color: #fbbf24; border-color: rgba(251, 191, 36, 0.5); }

.ctrl-grid {
  position: relative;
  z-index: 1;
  flex: 1;
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 14px;
  min-height: 0;
}
.left-col { display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.left-col > .panel { flex: none; }
.right-col { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.panel { padding: 18px 20px; }
.panel h3 { margin: 0 0 14px; font-size: 15px; color: var(--aqua); }
.btns { display: flex; gap: 10px; flex-wrap: wrap; }

.msg-row { display: flex; gap: 10px; }
.msg-input {
  flex: 1;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--glass);
  color: var(--text);
  font-size: 15px;
  font-family: inherit;
  outline: none;
}
.msg-input:focus { border-color: rgba(56, 189, 248, 0.5); }

.agent-status {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--glass);
}
.agent-status.is-live { border-color: rgba(34, 211, 238, 0.4); box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.12); }
.agent-status.is-fallback { border-color: rgba(251, 191, 36, 0.45); box-shadow: inset 0 0 0 1px rgba(251, 191, 36, 0.12); }
.agent-badge {
  flex: none;
  padding: 8px 14px;
  border-radius: 10px;
  font-weight: 800;
  font-size: 15px;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
.agent-status.is-live .agent-badge { color: #04122e; background: linear-gradient(92deg, var(--cyan), var(--violet)); }
.agent-status.is-fallback .agent-badge { color: #2a1d00; background: linear-gradient(92deg, #fbbf24, #f59e0b); }
.agent-meta { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.agent-line { font-size: 13px; color: var(--muted); }
.agent-line span {
  display: inline-block;
  width: 40px;
  color: var(--aqua);
  opacity: 0.85;
  margin-right: 6px;
}
.agent-tip { margin: 12px 0 0; font-size: 12px; color: var(--muted); line-height: 1.5; }

.shark-panel { display: flex; flex-direction: column; align-items: center; }
.mini { width: 200px; height: 200px; }
.shark-state { font-size: 14px; color: var(--aqua); letter-spacing: 2px; text-transform: uppercase; }
.log { flex: 1; min-height: 120px; }
</style>
