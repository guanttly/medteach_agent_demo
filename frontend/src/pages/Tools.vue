<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import AppIcon from '../components/AppIcon.vue'

interface ToolParam { name: string; type: string; default: unknown; label: string }
interface Tool {
  key: string
  name: string
  skill: string
  module: string
  category: string
  write: boolean
  summary: string
  scenario: string
  api: string
  params: ToolParam[]
}
interface PlatformStatus {
  base_url: string
  mode: string
  configured: boolean
  allow_write: boolean
  verify_ssl: boolean
  trust_env?: boolean
  llm_configured: boolean
  llm_provider: string
  tool_count: number
  cache?: WarmStatus
}
interface WarmModule { module: string; label: string; warm: boolean; age_ms: number | null; fallback: boolean | null }
interface WarmStatus { ttl_seconds: number; warm_count: number; total: number; modules: WarmModule[] }
interface InvokeResult {
  ok: boolean
  fallback: boolean
  empty?: boolean
  dry_run?: boolean
  cached?: boolean
  data: unknown
  error: { message?: string } | null
  mode: string
  elapsed_ms: number
  tool: string
}
interface ScenarioStep { key: string; name: string; write?: boolean }
interface Scenario { key: string; name: string; desc: string; steps: ScenarioStep[] }
interface ScenarioStepResult {
  key: string
  name: string
  ok: boolean
  fallback: boolean
  empty: boolean
  dry_run: boolean
  elapsed_ms: number
  error: string | null
}
interface ScenarioResult {
  ok: boolean
  key: string
  name: string
  mode: string
  real_ok: number
  total: number
  elapsed_ms: number
  steps: ScenarioStepResult[]
}
interface PrewarmModule { module: string; label: string; ok: boolean; fallback: boolean; empty: boolean; error: string | null; elapsed_ms: number }
interface PrewarmResult { mode: string; total: number; real_ok: number; fallback: number; failed: number; elapsed_ms: number; modules: PrewarmModule[] }

const SKILL_LABELS: Record<string, string> = {
  data_board: '数据看板',
  student_management: '学员管理',
  exam_monitoring: '考试监控',
  exam_arrange: '考试编排',
  exam_grading: '阅卷分析',
  question_bank: '题库',
  teaching_plan: '教学计划',
  case_recommend: '病例推荐'
}
const SKILL_ICON: Record<string, string> = {
  data_board: 'chart',
  student_management: 'users',
  exam_monitoring: 'signal',
  exam_arrange: 'clipboard',
  exam_grading: 'chart',
  question_bank: 'document',
  teaching_plan: 'monitor',
  case_recommend: 'bulb'
}

const tools = ref<Tool[]>([])
const platform = ref<PlatformStatus | null>(null)
const loading = ref(true)
const switching = ref(false)
const paramInputs = reactive<Record<string, Record<string, string>>>({})
const results = reactive<Record<string, InvokeResult | null>>({})
const running = reactive<Record<string, boolean>>({})
const showRaw = reactive<Record<string, boolean>>({})

const scenarios = ref<Scenario[]>([])
const scenarioResults = reactive<Record<string, ScenarioResult | null>>({})
const runningScenario = reactive<Record<string, boolean>>({})
const prewarming = ref(false)
const prewarmResult = ref<PrewarmResult | null>(null)

const mode = computed(() => platform.value?.mode ?? '—')
const warm = computed(() => platform.value?.cache ?? null)

const groups = computed(() => {
  const map: Record<string, Tool[]> = {}
  for (const t of tools.value) (map[t.skill] ||= []).push(t)
  return Object.keys(map).map((skill) => ({
    skill,
    label: SKILL_LABELS[skill] ?? skill,
    icon: SKILL_ICON[skill] ?? 'wrench',
    list: map[skill]
  }))
})

async function load() {
  loading.value = true
  try {
    const res = await api.getTools()
    tools.value = res.tools || []
    platform.value = res.platform || null
    scenarios.value = res.scenarios || []
    for (const t of tools.value) {
      paramInputs[t.key] ||= {}
      for (const p of t.params) {
        if (!(p.name in paramInputs[t.key])) {
          paramInputs[t.key][p.name] = p.default != null ? String(p.default) : ''
        }
      }
    }
  } catch {
    platform.value = null
  } finally {
    loading.value = false
  }
}

async function invoke(t: Tool) {
  running[t.key] = true
  try {
    const params: Record<string, unknown> = {}
    for (const p of t.params) {
      const v = paramInputs[t.key]?.[p.name]
      if (v != null && v !== '') params[p.name] = v
    }
    results[t.key] = (await api.invokeTool(t.key, params)) as InvokeResult
  } catch (e) {
    results[t.key] = {
      ok: false,
      fallback: false,
      data: null,
      error: { message: String(e) },
      mode: mode.value,
      elapsed_ms: 0,
      tool: t.key
    }
  } finally {
    running[t.key] = false
  }
}

async function switchMode(m: string) {
  if (switching.value || m === platform.value?.mode) return
  switching.value = true
  try {
    await api.setMode(m)
    const res = await api.getTools()
    platform.value = res.platform || platform.value
    prewarmResult.value = null
  } finally {
    switching.value = false
  }
}

async function prewarm() {
  if (prewarming.value) return
  prewarming.value = true
  try {
    prewarmResult.value = (await api.prewarmTools()) as PrewarmResult
    // 刷新平台状态，回填缓存命中计数
    const res = await api.getTools()
    platform.value = res.platform || platform.value
  } catch (e) {
    prewarmResult.value = {
      mode: mode.value,
      total: 0,
      real_ok: 0,
      fallback: 0,
      failed: 0,
      elapsed_ms: 0,
      modules: []
    }
  } finally {
    prewarming.value = false
  }
}

async function runScenario(s: Scenario) {
  if (runningScenario[s.key]) return
  runningScenario[s.key] = true
  try {
    scenarioResults[s.key] = (await api.runScenario(s.key)) as ScenarioResult
  } catch (e) {
    scenarioResults[s.key] = {
      ok: false,
      key: s.key,
      name: s.name,
      mode: mode.value,
      real_ok: 0,
      total: s.steps.length,
      elapsed_ms: 0,
      steps: []
    }
  } finally {
    runningScenario[s.key] = false
  }
}

function stepClass(s: ScenarioStepResult): string {
  if (!s.ok) return 'r-error'
  if (s.dry_run) return 'r-dry'
  return s.fallback ? 'r-fallback' : 'r-live'
}
function stepBadge(s: ScenarioStepResult): string {
  if (!s.ok) return '失败'
  if (s.dry_run) return '预演'
  if (s.empty) return '空数据·已回退'
  return s.fallback ? '回退' : '真实'
}

function resultClass(r?: InvokeResult | null): string {
  if (!r) return ''
  if (!r.ok) return 'r-error'
  if (r.dry_run) return 'r-dry'
  return r.fallback ? 'r-fallback' : 'r-live'
}
function resultBadge(r?: InvokeResult | null): string {
  if (!r) return ''
  if (!r.ok) return '调用失败'
  if (r.dry_run) return '写操作预演（Dry-run）'
  if (r.empty) return '平台暂无数据（已回退示例）'
  if (r.cached) return '真实平台数据（缓存）'
  return r.fallback ? '演示数据（回退）' : '真实平台数据'
}
function pretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

interface DryRunData { dry_run?: boolean; endpoint?: string; payload?: unknown; note?: string }
function isDryRun(v: unknown): boolean {
  return !!v && typeof v === 'object' && (v as DryRunData).dry_run === true
}
function dryData(v: unknown): DryRunData {
  return (v as DryRunData) ?? {}
}

onMounted(load)
</script>

<template>
  <div class="tools">
    <div class="bg-aurora"></div>

    <header class="t-top glass">
      <div class="t-left">
        <span class="logo"><AppIcon name="wrench" :size="24" /></span>
        <div>
          <div class="t-title">工具箱验证</div>
          <div class="t-sub">查看已接入的真实教学平台工具 · 一键点测 Agent 效果</div>
        </div>
      </div>
      <div class="t-status">
        <span class="chip"><i class="dot" :class="platform?.configured ? 'ok' : 'warn'"></i>平台 · {{ platform?.configured ? '已接入' : '未配置凭据' }}</span>
        <span class="chip">接口 · {{ mode }}</span>
        <span class="chip"><i class="dot" :class="platform?.llm_configured ? 'ok' : 'warn'"></i>大模型 · {{ platform?.llm_provider ?? '—' }}</span>
        <RouterLink to="/home" class="chip link"><AppIcon name="arrow" :size="14" /> 返回首页</RouterLink>
      </div>
    </header>

    <div class="t-body">
      <section class="panel glass status-panel">
        <h3><AppIcon name="signal" :size="16" /> 平台接入状态</h3>
        <div class="status-grid">
          <div class="st-item"><span>接口地址</span><b class="mono">{{ platform?.base_url || '—' }}</b></div>
          <div class="st-item"><span>当前模式</span><b>{{ mode }}</b></div>
          <div class="st-item"><span>平台凭据</span><b :class="platform?.configured ? 'good' : 'bad'">{{ platform?.configured ? '已配置' : '未配置' }}</b></div>
          <div class="st-item"><span>写操作</span><b :class="platform?.allow_write ? 'good' : 'muted'">{{ platform?.allow_write ? '已开启' : '已禁用' }}</b></div>
          <div class="st-item"><span>SSL 校验</span><b>{{ platform?.verify_ssl ? '开' : '关' }}</b></div>
          <div class="st-item"><span>大模型</span><b :class="platform?.llm_configured ? 'good' : 'muted'">{{ platform?.llm_provider || '—' }}</b></div>
          <div class="st-item"><span>已接入工具</span><b>{{ platform?.tool_count ?? tools.length }} 个</b></div>
        </div>
        <div class="mode-row">
          <span class="mode-label">切换接口模式</span>
          <button
            v-for="m in ['mock', 'hybrid', 'real']"
            :key="m"
            class="t-btn sm"
            :class="{ primary: mode === m }"
            :disabled="switching"
            @click="switchMode(m)"
          >
            {{ m }}
          </button>
        </div>
        <p class="hint">Mock = 全本地演示数据；Hybrid = 优先真实、失败回退；Real = 仅真实接口。切换会同步到大屏 / 控制台与数字人问答。</p>

        <div class="warm-row">
          <button class="t-btn primary" :disabled="prewarming" @click="prewarm">
            <AppIcon name="signal" :size="14" /> {{ prewarming ? '预热中…' : '一键预热真数据' }}
          </button>
          <span v-if="warm" class="warm-stat">
            缓存命中 <b :class="warm.warm_count > 0 ? 'good' : 'muted'">{{ warm.warm_count }}/{{ warm.total }}</b>
            · 有效期 {{ Math.round(warm.ttl_seconds / 60) }} 分钟
          </span>
          <span class="warm-tip">演示前预热，现场命中缓存即秒开真实统计，规避平台抖动。</span>
        </div>

        <div v-if="prewarmResult" class="warm-detail">
          <div class="warm-summary">
            预热完成 · {{ prewarmResult.elapsed_ms }} ms ·
            <b class="good">真实 {{ prewarmResult.real_ok }}</b> /
            <b class="warn">回退 {{ prewarmResult.fallback }}</b> /
            <b :class="prewarmResult.failed ? 'bad' : 'muted'">失败 {{ prewarmResult.failed }}</b>
          </div>
          <div class="warm-mods">
            <span
              v-for="m in prewarmResult.modules"
              :key="m.module"
              class="warm-chip"
              :class="m.ok && !m.fallback ? 'is-live' : m.ok ? 'is-fallback' : 'is-fail'"
              :title="m.error || ''"
            >
              {{ m.label }} · {{ m.ok && !m.fallback ? '真实' : m.ok ? '回退' : '失败' }} · {{ m.elapsed_ms }}ms
            </span>
          </div>
        </div>
      </section>

      <section v-if="scenarios.length" class="panel glass scenario-panel">
        <h3><AppIcon name="play" :size="16" /> 组合场景验证（多工具链路）</h3>
        <p class="hint">单技能只验证单点；组合场景按真实演示话术把多个工具串成一条链路跑通，统计哪步真实、哪步回退、哪步预演，确保现场不卡壳。</p>
        <div class="scenario-grid">
          <div v-for="s in scenarios" :key="s.key" class="scenario-card glass">
            <div class="sc-head">
              <div class="sc-name">{{ s.name }}</div>
              <button class="t-btn primary sm" :disabled="runningScenario[s.key]" @click="runScenario(s)">
                <AppIcon name="play" :size="13" /> {{ runningScenario[s.key] ? '运行中…' : '运行场景' }}
              </button>
            </div>
            <div class="sc-desc">{{ s.desc }}</div>
            <div class="sc-flow">
              <span v-for="(st, i) in s.steps" :key="st.key" class="sc-step-tag">
                <span class="sc-step-name">{{ st.name }}</span>
                <span v-if="st.write" class="sc-write">写</span>
                <span v-if="i < s.steps.length - 1" class="sc-arrow">→</span>
              </span>
            </div>

            <div v-if="scenarioResults[s.key]" class="sc-result">
              <div class="sc-summary" :class="scenarioResults[s.key].ok ? 'ok' : 'bad'">
                {{ scenarioResults[s.key].ok ? '链路跑通' : '链路异常' }} ·
                真实 {{ scenarioResults[s.key].real_ok }}/{{ scenarioResults[s.key].total }} ·
                {{ scenarioResults[s.key].elapsed_ms }} ms
              </div>
              <div v-for="st in scenarioResults[s.key].steps" :key="st.key" class="sc-step-row" :class="stepClass(st)">
                <span class="sc-sr-name">{{ st.name }}</span>
                <span class="sc-sr-badge">{{ stepBadge(st) }}</span>
                <span class="sc-sr-meta">{{ st.elapsed_ms }} ms</span>
                <span v-if="st.error" class="sc-sr-err">{{ st.error }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div v-if="loading" class="loading">正在加载工具箱…</div>

      <section v-for="g in groups" :key="g.skill" class="skill-group">
        <div class="sg-head">
          <AppIcon :name="g.icon" :size="16" /> {{ g.label }}
          <span class="sg-skill">{{ g.skill }} Skill</span>
        </div>
        <div class="tool-grid">
          <div v-for="t in g.list" :key="t.key" class="tool-card glass" :class="{ 'is-write': t.write }">
            <div class="tc-head">
              <div class="tc-name">{{ t.name }}</div>
              <span class="tag" :class="t.write ? 'tag-write' : 'tag-read'">{{ t.write ? '写' : '只读' }}</span>
            </div>
            <div class="tc-api mono">{{ t.api }}</div>
            <div class="tc-summary">{{ t.summary }}</div>
            <div class="tc-scene"><AppIcon name="mic" :size="13" /> {{ t.scenario }}</div>

            <div v-if="t.params.length" class="tc-params">
              <label v-for="p in t.params" :key="p.name" class="param">
                <span>{{ p.label }}</span>
                <input v-model="paramInputs[t.key][p.name]" class="p-input" :placeholder="String(p.default ?? '')" />
              </label>
            </div>

            <div class="tc-foot">
              <button
                class="t-btn primary"
                :disabled="running[t.key]"
                @click="invoke(t)"
              >
                <AppIcon name="play" :size="14" />
                {{ running[t.key] ? '调用中…' : t.write && !platform?.allow_write ? '预演写操作' : '点击测试' }}
              </button>
              <span v-if="t.write && !platform?.allow_write" class="write-lock">写已锁 · 仅预演不落库</span>
            </div>

            <div v-if="results[t.key]" class="tc-result" :class="resultClass(results[t.key])">
              <div class="r-head">
                <span class="r-badge">{{ resultBadge(results[t.key]) }}</span>
                <span class="r-meta">{{ results[t.key].mode }} · {{ results[t.key].elapsed_ms }} ms</span>
                <button class="raw-toggle" @click="showRaw[t.key] = !showRaw[t.key]">
                  {{ showRaw[t.key] ? '收起' : '原始数据' }}
                </button>
              </div>
              <div v-if="results[t.key].dry_run && isDryRun(results[t.key].data)" class="r-dryrun">
                <div class="r-dry-line"><span>将调用</span><b class="mono">{{ dryData(results[t.key].data).endpoint }}</b></div>
                <div class="r-dry-line"><span>说明</span><b>{{ dryData(results[t.key].data).note }}</b></div>
                <div class="r-dry-label">请求体预览（不会真实写入平台）</div>
                <pre class="r-json">{{ pretty(dryData(results[t.key].data).payload) }}</pre>
              </div>
              <div v-if="results[t.key].error && !results[t.key].dry_run" class="r-error-msg">{{ results[t.key].error?.message }}</div>
              <pre v-if="showRaw[t.key]" class="r-json">{{ pretty(results[t.key].data) }}</pre>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.tools {
  position: relative;
  height: 100vh;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}
.t-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 22px;
}
.t-left { display: flex; align-items: center; gap: 12px; }
.logo {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  color: var(--violet);
  background: var(--glass-2);
  border: 1px solid var(--line);
}
.t-title { font-size: 18px; font-weight: 800; }
.t-sub { font-size: 12px; color: var(--muted); }
.t-status { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.chip.link { cursor: pointer; color: var(--aqua); }

.t-body {
  position: relative;
  z-index: 1;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-right: 4px;
}

.panel { padding: 18px 20px; flex-shrink: 0; }
.panel h3 {
  margin: 0 0 14px;
  font-size: 15px;
  color: var(--aqua);
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 12px;
}
.st-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--glass);
  border: 1px solid var(--line);
}
.st-item span { font-size: 12px; color: var(--muted); }
.st-item b { font-size: 14px; }
.st-item b.good { color: var(--ok); }
.st-item b.bad { color: var(--danger); }
.st-item b.muted { color: var(--muted); }
.mono {
  font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
  font-size: 12.5px;
  word-break: break-all;
}

.mode-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.mode-label { font-size: 13px; color: var(--muted); }
.hint { font-size: 12.5px; color: var(--muted); margin: 12px 0 0; line-height: 1.6; }
.loading { color: var(--muted); padding: 20px; text-align: center; }

.skill-group { display: flex; flex-direction: column; gap: 12px; }
.sg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}
.sg-skill { font-size: 12px; color: var(--muted); font-weight: 400; letter-spacing: 0.5px; }

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}
.tool-card {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tool-card.is-write { border-color: rgba(251, 191, 36, 0.3); }
.tc-head { display: flex; align-items: center; justify-content: space-between; }
.tc-name { font-size: 16px; font-weight: 700; }
.tag { font-size: 11px; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--line); }
.tag-read { color: var(--aqua); border-color: rgba(34, 211, 238, 0.4); }
.tag-write { color: var(--gold); border-color: rgba(251, 191, 36, 0.45); }
.tc-api { color: var(--muted); }
.tc-summary { font-size: 13.5px; color: var(--text); line-height: 1.5; }
.tc-scene {
  font-size: 12.5px;
  color: var(--aqua);
  display: flex;
  align-items: center;
  gap: 5px;
}

.tc-params { display: flex; flex-direction: column; gap: 8px; padding: 10px 0; }
.param { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--muted); }
.param span { width: 120px; flex: none; }
.p-input {
  flex: 1;
  padding: 7px 11px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: var(--glass);
  color: var(--text);
  font-size: 13px;
  outline: none;
  font-family: inherit;
}
.p-input:focus { border-color: rgba(56, 189, 248, 0.5); }

.tc-foot { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.write-lock { font-size: 12px; color: var(--gold); }

.t-btn {
  padding: 9px 16px;
  border-radius: 11px;
  border: 1px solid var(--line);
  background: var(--glass);
  color: var(--text);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.18s ease;
}
.t-btn:hover:not(:disabled) { border-color: rgba(56, 189, 248, 0.5); transform: translateY(-1px); }
.t-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.t-btn.primary {
  background: linear-gradient(92deg, var(--cyan), var(--violet));
  color: #04122e;
  font-weight: 700;
  border: none;
}
.t-btn.sm { padding: 6px 14px; font-size: 13px; }

.tc-result {
  margin-top: 6px;
  border-radius: 12px;
  border: 1px solid var(--line);
  padding: 10px 12px;
  background: var(--glass);
}
.tc-result.r-live { border-color: rgba(52, 211, 153, 0.45); }
.tc-result.r-fallback { border-color: rgba(251, 191, 36, 0.45); }
.tc-result.r-error { border-color: rgba(248, 113, 113, 0.5); }
.r-head { display: flex; align-items: center; gap: 10px; }
.r-badge { font-size: 12.5px; font-weight: 700; }
.r-live .r-badge { color: var(--ok); }
.r-fallback .r-badge { color: var(--gold); }
.r-error .r-badge { color: var(--danger); }
.r-meta { font-size: 12px; color: var(--muted); margin-left: auto; }
.raw-toggle {
  font-size: 12px;
  color: var(--aqua);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}
.r-error-msg { font-size: 12.5px; color: var(--danger); margin-top: 6px; word-break: break-all; }
.r-json {
  margin: 8px 0 0;
  padding: 10px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.25);
  font-size: 12px;
  line-height: 1.5;
  max-height: 240px;
  overflow: auto;
  font-family: 'SF Mono', Consolas, monospace;
  color: #cfe0ff;
}

/* —— 一键预热 —— */
.warm-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}
.warm-stat { font-size: 13px; color: var(--muted); }
.warm-stat b { font-weight: 800; }
.warm-stat b.good { color: var(--ok); }
.warm-stat b.muted { color: var(--muted); }
.warm-tip { font-size: 12px; color: var(--muted); flex: 1 1 200px; }
.warm-detail {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--glass);
}
.warm-summary { font-size: 13px; margin-bottom: 10px; }
.warm-summary b { font-weight: 800; }
.warm-summary b.good { color: var(--ok); }
.warm-summary b.warn { color: var(--gold); }
.warm-summary b.bad { color: var(--danger); }
.warm-summary b.muted { color: var(--muted); }
.warm-mods { display: flex; flex-wrap: wrap; gap: 8px; }
.warm-chip {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--glass-2);
}
.warm-chip.is-live { color: var(--ok); border-color: rgba(52, 211, 153, 0.4); }
.warm-chip.is-fallback { color: var(--gold); border-color: rgba(251, 191, 36, 0.4); }
.warm-chip.is-fail { color: var(--danger); border-color: rgba(248, 113, 113, 0.45); }

/* —— 组合场景 —— */
.scenario-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}
.scenario-card {
  border-radius: 14px;
  border: 1px solid var(--line);
  padding: 14px 16px;
}
.sc-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.sc-name { font-size: 14.5px; font-weight: 800; }
.sc-desc { font-size: 12.5px; color: var(--muted); margin: 8px 0 10px; line-height: 1.55; }
.sc-flow { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.sc-step-tag { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
.sc-step-name {
  padding: 3px 9px;
  border-radius: 8px;
  background: var(--glass-2);
  border: 1px solid var(--line);
  color: var(--aqua);
}
.sc-write {
  font-size: 10.5px;
  color: var(--gold);
  border: 1px solid rgba(251, 191, 36, 0.45);
  border-radius: 6px;
  padding: 0 4px;
}
.sc-arrow { color: var(--muted); }
.sc-result {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}
.sc-summary { font-size: 13px; font-weight: 800; margin-bottom: 8px; }
.sc-summary.ok { color: var(--ok); }
.sc-summary.bad { color: var(--danger); }
.sc-step-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  padding: 5px 8px;
  border-radius: 8px;
  border-left: 3px solid var(--line);
  margin-bottom: 4px;
}
.sc-step-row.r-live { border-left-color: var(--ok); }
.sc-step-row.r-fallback { border-left-color: var(--gold); }
.sc-step-row.r-dry { border-left-color: var(--violet); }
.sc-step-row.r-error { border-left-color: var(--danger); }
.sc-sr-name { font-weight: 600; }
.sc-sr-badge { font-size: 11.5px; font-weight: 700; }
.r-live .sc-sr-badge, .sc-step-row.r-live .sc-sr-badge { color: var(--ok); }
.sc-step-row.r-fallback .sc-sr-badge { color: var(--gold); }
.sc-step-row.r-dry .sc-sr-badge { color: var(--violet); }
.sc-step-row.r-error .sc-sr-badge { color: var(--danger); }
.sc-sr-meta { font-size: 11.5px; color: var(--muted); margin-left: auto; }
.sc-sr-err { font-size: 11.5px; color: var(--muted); flex-basis: 100%; }

/* —— 写操作 Dry-run 预览 —— */
.tc-result.r-dry { border-color: rgba(167, 139, 250, 0.5); }
.r-dry .r-badge { color: var(--violet); }
.r-dryrun { margin-top: 8px; }
.r-dry-line { display: flex; gap: 8px; font-size: 12.5px; margin-bottom: 4px; }
.r-dry-line span { color: var(--muted); min-width: 44px; }
.r-dry-line b { font-weight: 700; word-break: break-all; }
.r-dry-label { font-size: 11.5px; color: var(--violet); margin: 8px 0 0; }
</style>
