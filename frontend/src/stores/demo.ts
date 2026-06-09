import { defineStore } from 'pinia'
import { api, wsUrl, SESSION_ID } from '../api/client'
import type {
  ExamPlan,
  ExamResult,
  Progress,
  Recommendation,
  SharkState,
  Student,
  TickerEvent,
  WorkflowStep,
  WsEvent
} from '../types'

const STATE_LABELS: Record<string, string> = {
  IDLE: '待命',
  INTENT_RECOGNIZED: '识别任务',
  PLAN_PROPOSED: '生成方案',
  WAITING_PLAN_CONFIRM: '等待方案确认',
  CREATING_EXAM: '创建考试',
  EXAM_PREVIEW_READY: '试卷预览',
  WAITING_PUBLISH_CONFIRM: '等待下发确认',
  PUBLISHING_EXAM: '下发考试',
  EXAM_PUBLISHED: '考试已下发',
  MONITORING_PROGRESS: '监控答题进度',
  GRADING: '自动阅卷',
  REPORT_READY: '成绩分析',
  RECOMMENDING: '推荐病例',
  DONE: '演示完成'
}

interface DemoState {
  connected: boolean
  state: string
  mode: string
  sharkState: SharkState
  assistantText: string
  userText: string
  workflow: WorkflowStep[]
  examPlan: ExamPlan | null
  students: { group_name: string; total: number; students: Student[] } | null
  examPreview: any | null
  progress: Progress | null
  result: ExamResult | null
  recommendation: Recommendation | null
  needConfirm: boolean
  confirmationType: string | null
  coreStatus: string
  fallbackActive: boolean
  agentSource: string
  agentProvider: string
  busy: boolean
  events: TickerEvent[]
  ttsOutbox: { id: number; type: 'reset' | 'enqueue' | 'finish' | 'stop'; text: string }[]
  mouth: number
  // 交互过渡态：消除“用户说完话 → 鲨鲨开口”之间的空窗感
  liveTranscript: string
  thinking: boolean
  thinkingSince: number
  _ws: WebSocket | null
  _evtId: number
  _retry: number
  _ttsId: number
  _generation: number
  _curUttId: string
  _streamSpeechId: string
  _streamTts: boolean
  _lastAssistantSpeechId: string
  _lastAssistantSpeechText: string
  _lastAssistantSpeechAt: number
}

export const useDemoStore = defineStore('demo', {
  state: (): DemoState => ({
    connected: false,
    state: 'IDLE',
    mode: 'hybrid',
    sharkState: 'idle',
    assistantText: '你好，我是巨鲨数字助教鲨鲨。请对我说「安排一场胸部 CT 基础考试」。',
    userText: '',
    workflow: [],
    examPlan: null,
    students: null,
    examPreview: null,
    progress: null,
    result: null,
    recommendation: null,
    needConfirm: false,
    confirmationType: null,
    coreStatus: 'idle',
    fallbackActive: false,
    agentSource: 'local',
    agentProvider: '本地编排',
    busy: false,
    events: [],
    ttsOutbox: [],
    mouth: 0,
    liveTranscript: '',
    thinking: false,
    thinkingSince: 0,
    _ws: null,
    _evtId: 0,
    _retry: 0,
    _ttsId: 0,
    _generation: 0,
    _curUttId: '',
    _streamSpeechId: '',
    _streamTts: false,
    _lastAssistantSpeechId: '',
    _lastAssistantSpeechText: '',
    _lastAssistantSpeechAt: 0
  }),

  getters: {
    stateLabel: (s) => STATE_LABELS[s.state] ?? s.state,
    isDone: (s) => s.state === 'DONE'
  },

  actions: {
    connect(sessionId: string = SESSION_ID) {
      if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) {
        return
      }
      const ws = new WebSocket(wsUrl(sessionId))
      this._ws = ws
      ws.onopen = () => {
        this.connected = true
        this._retry = 0
        // 心跳，保持连接
        const ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
          else clearInterval(ping)
        }, 15000)
      }
      ws.onmessage = (e) => {
        try {
          this.handleEvent(JSON.parse(e.data) as WsEvent)
        } catch {
          /* ignore malformed frame */
        }
      }
      ws.onclose = () => {
        this.connected = false
        this._ws = null
        this._retry = Math.min(this._retry + 1, 6)
        setTimeout(() => this.connect(sessionId), 600 * this._retry)
      }
      ws.onerror = () => ws.close()
    },

    pushEvent(type: string, title: string, message: string, status = 'completed', fallback = false) {
      this._evtId += 1
      this.events.unshift({ id: this._evtId, type, title, message, status, fallback, ts: Date.now() })
      if (this.events.length > 40) this.events.length = 40
    },

    applySnapshot(snap: any) {
      this.state = snap.state
      this.mode = snap.mode
      this.sharkState = snap.shark_state
      this.assistantText = snap.assistant_text
      this.userText = snap.user_text
      this.workflow = snap.workflow ?? []
      this.examPlan = snap.exam_plan
      this.students = snap.students
      this.examPreview = snap.exam_preview
      this.progress = snap.progress
      this.result = snap.result
      this.recommendation = snap.recommendation
      this.needConfirm = snap.need_user_confirmation
      this.confirmationType = snap.confirmation_type
      this.coreStatus = snap.core_status
      this.fallbackActive = snap.fallback_active
      this.agentSource = snap.agent_source ?? this.agentSource
      this.agentProvider = snap.agent_provider ?? this.agentProvider
      this.busy = snap.busy
      if (typeof snap.generation === 'number') this._generation = snap.generation
    },

    // 过期 generation 的字幕 / 音频帧必须丢弃（打断后旧 utterance 失效）
    _isStale(gen?: number) {
      return typeof gen === 'number' && gen < this._generation
    },

    handleEvent(evt: WsEvent) {
      const d = evt.data || {}
      switch (evt.type) {
        case 'snapshot':
          this.applySnapshot(d)
          break
        case 'core_status_update':
          this.state = d.state
          this.mode = d.mode
          this.coreStatus = d.core_status
          this.fallbackActive = d.fallback_active
          this.agentSource = d.agent_source ?? this.agentSource
          this.agentProvider = d.agent_provider ?? this.agentProvider
          this.needConfirm = d.need_user_confirmation
          this.confirmationType = d.confirmation_type
          this.busy = d.busy
          break
        case 'shark_state_update':
          this.sharkState = d.state
          break
        case 'assistant_message':
          this.endThinking()
          this.assistantText = d.text
          this.sharkState = d.shark_state ?? this.sharkState
          if (d.tts) {
            const now = Date.now()
            const speechId = d.speech_id || ''
            const duplicateSpeech =
              (speechId && speechId === this._lastAssistantSpeechId) ||
              (d.text === this._lastAssistantSpeechText && now - this._lastAssistantSpeechAt < 2500)
            if (!duplicateSpeech) {
              this._lastAssistantSpeechId = speechId
              this._lastAssistantSpeechText = d.text
              this._lastAssistantSpeechAt = now
              this._pushTts('reset')
              this._pushTts('enqueue', d.text)
              this._pushTts('finish')
            }
          }
          break
        case 'assistant_stream': {
          const phase = d.phase
          if (phase === 'start') {
            this.endThinking()
            this.sharkState = d.shark_state ?? 'speaking'
            this.assistantText = ''
            this._streamSpeechId = d.speech_id || ''
            this._streamTts = !!d.tts
            if (this._streamTts) {
              this._lastAssistantSpeechId = this._streamSpeechId
              this._lastAssistantSpeechAt = Date.now()
              this._pushTts('reset')
            }
          } else if (phase === 'delta') {
            this.assistantText = d.text ?? this.assistantText
          } else if (phase === 'sentence') {
            if (this._streamTts && d.sentence) this._pushTts('enqueue', d.sentence)
          } else if (phase === 'end') {
            this.assistantText = d.text ?? this.assistantText
            this._lastAssistantSpeechText = this.assistantText
            this._lastAssistantSpeechAt = Date.now()
            if (this._streamTts) this._pushTts('finish')
          }
          break
        }
        // ---- 新前台交互协议：utterance.* / interaction.* ----
        case 'utterance.started': {
          if (this._isStale(evt.generation)) break
          this.endThinking()
          this._curUttId = evt.utterance_id || d.utterance_id || ''
          this.sharkState = d.shark_state ?? 'speaking'
          this.assistantText = ''
          this._streamTts = d.tts !== false
          if (this._streamTts) {
            this._lastAssistantSpeechId = this._curUttId
            this._lastAssistantSpeechAt = Date.now()
            this._pushTts('reset')
          }
          break
        }
        case 'utterance.delta': {
          if (this._isStale(evt.generation)) break
          this.assistantText = d.text ?? this.assistantText
          break
        }
        case 'utterance.sentence': {
          if (this._isStale(evt.generation)) break
          if (this._streamTts && d.tts !== false && d.sentence) this._pushTts('enqueue', d.sentence)
          break
        }
        case 'utterance.completed': {
          if (this._isStale(evt.generation)) break
          this.assistantText = d.text ?? this.assistantText
          this._lastAssistantSpeechText = this.assistantText
          this._lastAssistantSpeechAt = Date.now()
          if (this._streamTts) this._pushTts('finish')
          break
        }
        case 'utterance.confirmation_requested': {
          if (this._isStale(evt.generation)) break
          // 确认类播报会通过 utterance.* 完整播出；此处仅刷新需确认标记
          if (d.confirmation_type) this.confirmationType = d.confirmation_type
          this.needConfirm = true
          break
        }
        case 'interaction.interrupted': {
          // 进入新 generation：旧 utterance 的字幕 / 音频 / TTS end 全部失效
          if (typeof evt.generation === 'number') {
            this._generation = Math.max(this._generation, evt.generation)
          }
          this._streamTts = false
          this._curUttId = ''
          // 若本轮打断由用户说新话触发（本地已进入思考态），保持“思考中”，避免闪回 idle
          if (!this.thinking) this.sharkState = d.shark_state ?? 'idle'
          this._pushTts('stop')
          break
        }
        case 'interaction.barge_in_ignored':
          // 回声或无效插话，前台无需动作
          break
        case 'narration.summary_emitted':
          // 摘要最终通过 utterance.* 播报，这里仅作为诊断信号
          break
        case 'domain.updated':
        case 'workflow.job_updated':
        case 'workflow.step_started':
        case 'workflow.step_completed':
          // 业务面板由 legacy *_update / workflow_update 驱动，避免重复刷新
          break
        case 'user_message':
          this.userText = d.text
          break
        case 'workflow_update':
          this.workflow = d.workflow
          break
        case 'exam_plan_update':
          this.examPlan = d.exam_plan
          break
        case 'students_update':
          this.students = d.students
          break
        case 'exam_preview_update':
          this.examPreview = d.exam_preview
          break
        case 'exam_progress_update':
          this.progress = d.progress
          break
        case 'exam_result_update':
          this.result = d.result
          break
        case 'case_recommendation_update':
          this.recommendation = d.recommendation
          break
        case 'screen_event':
          this.pushEvent(d.type, d.title, d.message, d.status, !!d.fallback)
          break
        case 'demo_reset':
          this.endThinking()
          this.liveTranscript = ''
          this.events = []
          this.ttsOutbox = []
          this._generation = 0
          this._curUttId = ''
          this._streamSpeechId = ''
          this._streamTts = false
          this._lastAssistantSpeechId = ''
          this._lastAssistantSpeechText = ''
          this._lastAssistantSpeechAt = 0
          this._pushTts('stop')
          this.applySnapshot(d.snapshot)
          break
        default:
          break
      }
    },

    // ---- 用户 / 导演操作 ----
    sendMessage(text: string) {
      return api.sendMessage(text)
    },
    // 前台交互通道：语音/文本统一入口，非阻塞。barge-in 时由网关决定打断策略。
    sendTurn(text: string, opts: { barge_in?: boolean; source?: string } = {}) {
      // 乐观过渡：用户话音刚落即进入“思考中”，0 延迟反馈，等鲨鲨开口后由后端事件接管
      this.beginThinking(text)
      return api.conversationTurn(text, {
        source: opts.source ?? 'voice',
        barge_in: opts.barge_in ?? false,
        interrupts_utterance_id: this._curUttId || null
      })
    },
    // 主动打断：本地立即停止音频，并通知网关进入新 generation。
    interrupt(opts: { reason?: string; policy?: string } = {}) {
      this._pushTts('stop')
      return api.interrupt({
        utterance_id: this._curUttId || null,
        reason: opts.reason ?? 'user_barge_in',
        policy: opts.policy ?? 'stop_low_priority'
      })
    },
    confirm(type: string) {
      return api.confirm(type)
    },
    publish() {
      return api.publish()
    },
    reset() {
      return api.reset()
    },
    setMode(mode: string) {
      return api.setMode(mode)
    },
    controlStep(target: string) {
      return api.controlStep(target)
    },
    preset(p: string) {
      return api.preset(p)
    },
    simulateSubmit() {
      return api.simulateSubmit()
    },
    setMouth(v: number) {
      this.mouth = v
    },
    // ---- 交互过渡态：消除“用户说完话 → 鲨鲨开口”之间的空窗感 ----
    setLiveTranscript(text: string) {
      this.liveTranscript = text
    },
    // 用户开口：空闲态立即切“聆听”，给出“我在听”的可见反馈
    beginListening() {
      if (this.thinking) return
      if (['idle', 'success', 'waiting_confirm', 'soft_warning'].includes(this.sharkState)) {
        this.sharkState = 'listening'
      }
    },
    // 用户话音刚落：乐观进入“思考中”，由后端首个播报事件接管收敛
    beginThinking(text = '') {
      if (text) this.userText = text
      this.liveTranscript = ''
      this.thinking = true
      this.thinkingSince = Date.now()
      this.sharkState = 'thinking'
    },
    endThinking() {
      if (!this.thinking && !this.thinkingSince) return
      this.thinking = false
      this.thinkingSince = 0
    },
    _pushTts(type: 'reset' | 'enqueue' | 'finish' | 'stop', text = '') {
      this._ttsId += 1
      this.ttsOutbox.push({ id: this._ttsId, type, text })
      if (this.ttsOutbox.length > 100) this.ttsOutbox.splice(0, this.ttsOutbox.length - 100)
    },
    drainTts(afterId: number) {
      return this.ttsOutbox.filter((c) => c.id > afterId)
    }
  }
})
