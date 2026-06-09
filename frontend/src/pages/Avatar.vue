<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import SharkAvatar from '../components/SharkAvatar.vue'
import AppIcon from '../components/AppIcon.vue'
import { useDemoStore } from '../stores/demo'
import { useTts } from '../composables/useTts'

const store = useDemoStore()
const { sharkState, assistantText, userText, liveTranscript, thinking, mouth, connected, needConfirm, confirmationType } =
  storeToRefs(store)
const tts = useTts()

const started = ref(false)
const listening = ref(false)
const micEnabled = ref(false)
let recognition: any = null
let shouldListen = false
let restartTimer = 0
let routeTimer = 0
let pendingTranscript = ''
let asrCandidateTranscript = ''
let asrCandidateUpdatedAt = 0
let asrRouteTimer = 0
let pendingAsrTranscript = ''
let pendingAsrSource: 'final' | 'vad' | 'speechend' | 'end' | '' = ''
let pendingAsrCandidateAt = 0
let lastRoutedTranscript = ''
let lastRoutedAt = 0
let lastVadRoutedTranscript = ''
let lastVadRoutedAt = 0
// 识别器健壮性：打断后 Chrome 的 SpeechRecognition 常变「僵尸」（start 成功却不再拾音）。
// 用启动看门狗 + VAD 旁路探活把识别会话拉回，等价于用户手动开关麦克风的干净重建。
let startWatchdog = 0
let recognitionAlive = false
let recognitionRestarting = false
let lastAsrSignalAt = 0
let bargeInRecycleTimer = 0
let processedTtsId = 0
let vadStream: MediaStream | null = null
let vadCtx: AudioContext | null = null
let vadSource: MediaStreamAudioSourceNode | null = null
let vadAnalyser: AnalyserNode | null = null
let vadData: Uint8Array | null = null
let vadRaf = 0
let vadStarting = false
let vadSpeaking = false
let vadSpeechStartedAt = 0
let vadLastVoiceAt = 0
let vadNoiseFloor = 0.012

const VOICE_ROUTE_IDLE_FLUSH_MS = 80
const ASR_CANDIDATE_STALE_MS = 5000
const ASR_FINAL_SETTLE_MS = 220
const ASR_ENDPOINT_SETTLE_MS = 760
const ASR_SHORT_FRAGMENT_SETTLE_MS = 1400
const ASR_MIN_STABLE_CHARS = 3
const VAD_MIN_SPEECH_MS = 180
const VAD_SILENCE_MS = 650
const VAD_RMS_FLOOR = 0.012
const VAD_DUPLICATE_SUPPRESS_MS = 8000
const RECOGNITION_START_WATCHDOG_MS = 2500
const RECOGNITION_DEAD_SIGNAL_MS = 1800
const BARGE_IN_RECYCLE_MS = 500

const STATE_TEXT: Record<string, string> = {
  idle: '待命中',
  listening: '正在倾听',
  thinking: '思考中',
  speaking: '播报中',
  working: '处理中',
  waiting_confirm: '等待您确认',
  success: '已完成',
  soft_warning: '稳妥模式'
}
const stateText = computed(() => STATE_TEXT[sharkState.value] ?? '待命中')

// 「思考中」过渡态：用户话音刚落到鲨鲨开口前的可见反馈，>5s 给出温和的「慢」提示
const thinkingSlow = ref(false)
let thinkingTimer = 0
watch(thinking, (v) => {
  if (thinkingTimer) {
    clearTimeout(thinkingTimer)
    thinkingTimer = 0
  }
  thinkingSlow.value = false
  if (v) {
    thinkingTimer = window.setTimeout(() => {
      thinkingSlow.value = true
    }, 5000)
  }
})
const thinkingHint = computed(() =>
  thinkingSlow.value ? '网络有点慢，鲨鲨还在认真思考，请稍候…' : '好的，鲨鲨正在思考…'
)

// 引导语：等待确认时提示用户可以说什么
const voiceHint = computed(() => {
  if (thinking.value) return ''
  if (needConfirm.value && confirmationType.value === 'confirm_publish') return '对我说「下发考试」即可发布'
  if (needConfirm.value) return '对我说「确认」即可继续'
  if (sharkState.value === 'idle') return '对我说「安排一场胸部 CT 基础考试」'
  return ''
})
const micStateText = computed(() => {
  if (thinking.value) return '已听到，鲨鲨正在思考…'
  if (tts.speakingNow.value) {
    return listening.value ? '鲨鲨播报中 · 可随时说话打断' : '鲨鲨播报中'
  }
  if (listening.value) return '正在聆听，请说…'
  if (micEnabled.value) return '麦克风已开启，正在准备聆听'
  return '点击麦克风，对鲨鲨说话'
})

// 声纹振幅条
const bars = computed(() => {
  const m = mouth.value
  return Array.from({ length: 11 }, (_, i) => {
    const base = Math.sin((i / 11) * Math.PI)
    return Math.max(0.08, base * (0.25 + m * 1.1))
  })
})

// 是否正在播报（用于显示「打断」按钮）
const speaking = computed(() => tts.speakingNow.value)

function start() {
  tts.enable()
  started.value = true
  setupRecognition()
  setTimeout(() => tts.speak(assistantText.value), 400)
}

// 监听 TTS 指令外发队列 -> 驱动流式播报（仅本页持有音频通道）
watch(
  () => store._ttsId,
  () => {
    if (!started.value || document.visibilityState !== 'visible') {
      processedTtsId = store._ttsId
      return
    }
    const items = store.drainTts(processedTtsId)
    processedTtsId = store._ttsId
    for (const it of items) {
      if (it.type === 'reset') tts.reset()
      else if (it.type === 'enqueue') tts.enqueue(it.text)
      else if (it.type === 'finish') tts.finish()
      else if (it.type === 'stop') tts.stop()
    }
  }
)

// 播报期间保持麦克风开启以支持「说话打断」；用户开口先压低音量给出反馈。
// 字幕 / 音频的「过期丢弃」由 store 依据 generation 统一处理。

// ---- 回声判定：避免把鲨鲨自己的播报当成用户插话 ----
function normalizeZh(s: string): string {
  return (s || '').replace(/[\s，。！？、,.!?；;:：…·\-—~"'""'']/g, '').toLowerCase()
}
function isNearDuplicateText(a: string, b: string): boolean {
  const x = normalizeZh(a)
  const y = normalizeZh(b)
  if (!x || !y) return false
  if (x === y) return true
  if (x.length < 3 || y.length < 3) return false
  return x.includes(y) || y.includes(x)
}
// 业务关键控制指令：无论是否正在播报、是否像回声，都必须放行，绝不丢弃。
// 保证「确认 / 下发 / 停一下 / 重来 / 安排考试」等指令在任何时刻都能被响应。
const CONTROL_INTENT_RE =
  /(确认|确定|可以了?|没问题|没毛病|同意|通过|批准|就这样|按这个|下发|发布|开考|开始考试|开放答题|生成入口|二维码|停一?下|停止|取消|暂停|先别|不用了|别说了|重置|重来|重新开始|继续|往下|下一步|开始吧|安排|考试|测评|考核|出题|组织)/
function isControlIntent(text: string): boolean {
  const t = normalizeZh(text)
  if (!t || t.length > 16) return false
  return CONTROL_INTENT_RE.test(t)
}

function isLikelyEcho(text: string): boolean {
  const t = normalizeZh(text)
  if (!t) return true
  // 业务关键控制指令永不当回声，保证用户随时可用语音控制
  if (isControlIntent(text)) return false
  // 回声参考优先用「最近真正播完的整句」，避免用实时累积字幕造成误判
  for (const r of [store._lastAssistantSpeechText, store.assistantText]) {
    const ref = normalizeZh(r)
    if (ref.length < 4) continue
    // 连续包含：候选基本是播报文本的子串（典型回声拾取）
    if (t.length >= 3 && (ref.includes(t) || t.includes(ref))) return true
    // 无序字符重合度：仅对较长候选启用，阈值收紧，避免短指令被误杀
    if (t.length >= 6) {
      let hit = 0
      for (const ch of t) if (ref.includes(ch)) hit++
      if (hit / t.length > 0.86) return true
    }
  }
  return false
}
function isRecentAssistantEcho(text: string): boolean {
  const t = normalizeZh(text)
  if (t.length < 4) return false
  return Date.now() - store._lastAssistantSpeechAt < 2500 && isLikelyEcho(text)
}

// ---- ASR 候选文本 + VAD 端点：不要把业务推进绑死在 Chrome 的 isFinal 上 ----
function rememberAsrCandidate(text: string) {
  const t = text.trim()
  if (!t) return
  asrCandidateTranscript = t
  asrCandidateUpdatedAt = Date.now()
}
function clearPendingAsrRoute() {
  if (asrRouteTimer) {
    clearTimeout(asrRouteTimer)
    asrRouteTimer = 0
  }
  pendingAsrTranscript = ''
  pendingAsrSource = ''
  pendingAsrCandidateAt = 0
}
function clearAsrCandidate() {
  asrCandidateTranscript = ''
  asrCandidateUpdatedAt = 0
  clearPendingAsrRoute()
}
function asrRouteDelay(text: string, source: 'final' | 'vad' | 'speechend' | 'end') {
  const len = normalizeZh(text).length
  if (isControlIntent(text)) return source === 'final' ? VOICE_ROUTE_IDLE_FLUSH_MS : ASR_FINAL_SETTLE_MS
  if (len < ASR_MIN_STABLE_CHARS) return ASR_SHORT_FRAGMENT_SETTLE_MS
  return source === 'final' ? ASR_FINAL_SETTLE_MS : ASR_ENDPOINT_SETTLE_MS
}
function betterAsrCandidate(current: string, pending: string): boolean {
  const c = normalizeZh(current)
  const p = normalizeZh(pending)
  if (!c || !p || c === p) return false
  if (c.length <= p.length) return false
  if (p.length < ASR_MIN_STABLE_CHARS) return true
  return c.includes(p) || c.length >= p.length + 2
}
function flushPendingAsrRoute() {
  if (asrRouteTimer) {
    clearTimeout(asrRouteTimer)
    asrRouteTimer = 0
  }
  let t = pendingAsrTranscript.trim()
  const source = pendingAsrSource || 'end'
  if (!t) return

  const current = asrCandidateTranscript.trim()
  const currentIsFresh = !!asrCandidateUpdatedAt && Date.now() - asrCandidateUpdatedAt <= ASR_CANDIDATE_STALE_MS
  if (currentIsFresh && betterAsrCandidate(current, t)) {
    t = current
    pendingAsrTranscript = current
    pendingAsrCandidateAt = asrCandidateUpdatedAt
  }

  const delay = asrRouteDelay(t, source)
  const candidateAge = pendingAsrCandidateAt ? Date.now() - pendingAsrCandidateAt : delay
  if (candidateAge < delay) {
    asrRouteTimer = window.setTimeout(flushPendingAsrRoute, delay - candidateAge)
    return
  }

  if (
    source === 'final' &&
    lastVadRoutedTranscript &&
    Date.now() - lastVadRoutedAt < VAD_DUPLICATE_SUPPRESS_MS &&
    isNearDuplicateText(t, lastVadRoutedTranscript)
  ) {
    clearAsrCandidate()
    return
  }
  if (source !== 'final') {
    if (!currentIsFresh) {
      clearAsrCandidate()
      return
    }
    if (isRecentAssistantEcho(t)) {
      clearAsrCandidate()
      tts.restore()
      return
    }
    lastVadRoutedTranscript = t
    lastVadRoutedAt = Date.now()
  }
  routeVoiceNow(t)
  clearAsrCandidate()
}
function routeAsrText(text: string, source: 'final' | 'vad' | 'speechend' | 'end') {
  const t = text.trim()
  if (!t) return
  if (source !== 'final') {
    const now = Date.now()
    if (!asrCandidateUpdatedAt || now - asrCandidateUpdatedAt > ASR_CANDIDATE_STALE_MS) return
    if (pendingAsrSource === 'final' && isNearDuplicateText(t, pendingAsrTranscript)) return
  }
  if (asrRouteTimer) clearTimeout(asrRouteTimer)
  pendingAsrTranscript = t
  pendingAsrSource = source
  pendingAsrCandidateAt = asrCandidateUpdatedAt || Date.now()
  asrRouteTimer = window.setTimeout(flushPendingAsrRoute, asrRouteDelay(t, source))
}
function routeAsrCandidate(source: 'vad' | 'speechend' | 'end') {
  routeAsrText(asrCandidateTranscript, source)
}

// ---- 插话时的临时压低音量恢复定时器 ----
let duckRestoreTimer = 0
function scheduleDuckRestore() {
  cancelDuckRestore()
  duckRestoreTimer = window.setTimeout(() => {
    duckRestoreTimer = 0
    if (tts.speakingNow.value) tts.restore()
  }, 1500)
}
function cancelDuckRestore() {
  if (duckRestoreTimer) {
    clearTimeout(duckRestoreTimer)
    duckRestoreTimer = 0
  }
}

// 主动打断（打断按钮）：本地立即停音 + 通知网关进入新 generation，并保持聆听。
function bargeIn() {
  cancelDuckRestore()
  tts.stop()
  store.interrupt({})
  if (!shouldListen) {
    shouldListen = true
    micEnabled.value = true
  }
  // 打断后做一次干净重建，规避 Chrome 识别僵尸态导致的「打断后无法再录入」
  forceRestartRecognition()
}

function scheduleVoiceRoute(text: string, delayMs = VOICE_ROUTE_IDLE_FLUSH_MS) {
  pendingTranscript = pendingTranscript ? `${pendingTranscript} ${text}` : text
  if (routeTimer) clearTimeout(routeTimer)
  routeTimer = window.setTimeout(flushVoiceRoute, delayMs)
}

function routeVoiceNow(text: string) {
  pendingTranscript = pendingTranscript ? `${pendingTranscript} ${text}` : text
  flushVoiceRoute()
}

function flushVoiceRoute() {
  if (routeTimer) {
    clearTimeout(routeTimer)
    routeTimer = 0
  }
  const text = pendingTranscript.trim()
  pendingTranscript = ''
  if (!text) {
    if (!thinking.value) store.setLiveTranscript('')
    return
  }
  const speaking = tts.speakingNow.value
  // 播报期间：先做回声判定，是鲨鲨自己的声音则忽略并恢复音量
  if (speaking && isLikelyEcho(text)) {
    cancelDuckRestore()
    tts.restore()
    return
  }
  const now = Date.now()
  if (text === lastRoutedTranscript && now - lastRoutedAt < 2500) return
  lastRoutedTranscript = text
  lastRoutedAt = now
  if (speaking) {
    // 真·插话：本地立即停音，并让网关进入新 generation 后路由本轮输入
    cancelDuckRestore()
    tts.stop()
    store.sendTurn(text, { barge_in: true })
    // 打断后 Chrome 识别会话极易变僵尸，主动做一次干净重建，保证下一句仍能录入
    scheduleBargeInRecycle()
  } else {
    store.sendTurn(text, { barge_in: false })
  }
}

function setupRecognition() {
  const R = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
  if (!R) return
  // 重建前彻底解绑并中止旧实例，避免 Chrome 残留的僵尸会话继续回调
  if (recognition) {
    try {
      recognition.onstart = null
      recognition.onaudiostart = null
      recognition.onresult = null
      recognition.onspeechstart = null
      recognition.onspeechend = null
      recognition.onend = null
      recognition.onerror = null
    } catch {
      /* ignore */
    }
    try {
      recognition.abort()
    } catch {
      /* ignore */
    }
  }
  recognition = new R()
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true
  recognition.maxAlternatives = 1
  // onstart/onaudiostart：识别真正开始拾音的存活信号，用于解除启动看门狗
  recognition.onstart = () => {
    recognitionAlive = true
    recognitionRestarting = false
    lastAsrSignalAt = Date.now()
    clearStartWatchdog()
  }
  recognition.onaudiostart = () => {
    recognitionAlive = true
    recognitionRestarting = false
    lastAsrSignalAt = Date.now()
    clearStartWatchdog()
  }
  recognition.onresult = (e: any) => {
    lastAsrSignalAt = Date.now()
    recognitionAlive = true
    let finalText = ''
    let interim = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const result = e.results[i]
      const piece = result[0]?.transcript ?? ''
      if (result.isFinal) finalText += piece
      else interim += piece
    }
    // 鲨鲨播报期间的 interim 多为回声，不显示草稿（真插话由 flushVoiceRoute 回声判定处理）
    if (!tts.speakingNow.value) {
      const transcript = (finalText + interim).trim()
      store.setLiveTranscript(transcript)
      if (transcript) store.beginListening()
    }
    const candidate = (finalText + interim).trim()
    if (candidate) rememberAsrCandidate(candidate)
    const text = finalText.trim()
    if (text) routeAsrText(text, 'final')
  }
  recognition.onspeechstart = () => {
    lastAsrSignalAt = Date.now()
    recognitionAlive = true
    // 用户开口：若鲨鲨正在播报，先压低音量给出「我在听」的反馈，
    // 真伪插话在 flushVoiceRoute 里依据回声判定最终决定停不停。
    if (tts.speakingNow.value) {
      tts.duck()
      scheduleDuckRestore()
    } else {
      // 鲨鲨空闲时用户开口：立即进入「聆听」态，让数字人有可见回应
      store.beginListening()
    }
  }
  recognition.onspeechend = () => {
    routeAsrCandidate('speechend')
  }
  recognition.onend = () => {
    routeAsrCandidate('end')
    flushVoiceRoute()
    listening.value = false
    if (shouldListen) scheduleRecognitionRestart()
  }
  recognition.onerror = (event: any) => {
    listening.value = false
    if (event?.error === 'not-allowed' || event?.error === 'service-not-allowed') {
      shouldListen = false
      return
    }
    if (shouldListen) scheduleRecognitionRestart()
  }
}

async function startVad() {
  if (vadStarting || vadRaf || vadStream) return
  const mediaDevices = navigator.mediaDevices
  if (!mediaDevices?.getUserMedia) return
  vadStarting = true
  try {
    vadStream = await mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    })
    if (!shouldListen) {
      stopVad()
      return
    }
    const AC = (window as any).AudioContext || (window as any).webkitAudioContext
    if (!AC) {
      stopVad()
      return
    }
    vadCtx = new AC()
    vadSource = vadCtx.createMediaStreamSource(vadStream)
    vadAnalyser = vadCtx.createAnalyser()
    vadAnalyser.fftSize = 1024
    vadData = new Uint8Array(vadAnalyser.fftSize)
    vadSource.connect(vadAnalyser)
    vadNoiseFloor = VAD_RMS_FLOOR
    void vadCtx.resume()
    vadLoop()
  } catch {
    stopVad()
  } finally {
    vadStarting = false
  }
}

function stopVad() {
  if (vadRaf) {
    cancelAnimationFrame(vadRaf)
    vadRaf = 0
  }
  try {
    vadSource?.disconnect()
  } catch {
    /* ignore */
  }
  try {
    vadAnalyser?.disconnect()
  } catch {
    /* ignore */
  }
  vadStream?.getTracks().forEach((track) => track.stop())
  if (vadCtx) void vadCtx.close().catch(() => undefined)
  vadStream = null
  vadCtx = null
  vadSource = null
  vadAnalyser = null
  vadData = null
  vadStarting = false
  vadSpeaking = false
  vadSpeechStartedAt = 0
  vadLastVoiceAt = 0
}

function vadLoop() {
  if (!vadAnalyser || !vadData) {
    vadRaf = 0
    return
  }
  vadAnalyser.getByteTimeDomainData(vadData)
  let sum = 0
  for (const value of vadData) {
    const v = (value - 128) / 128
    sum += v * v
  }
  const rms = Math.sqrt(sum / vadData.length)
  const now = Date.now()
  const threshold = Math.max(VAD_RMS_FLOOR, vadNoiseFloor * 2.4 + 0.006)
  const voiced = rms > threshold

  if (voiced) {
    if (!vadSpeaking) {
      vadSpeaking = true
      vadSpeechStartedAt = now
    }
    vadLastVoiceAt = now
  } else if (!vadSpeaking && !tts.speakingNow.value) {
    vadNoiseFloor = vadNoiseFloor * 0.96 + rms * 0.04
  }

  if (vadSpeaking && !voiced && now - vadLastVoiceAt >= VAD_SILENCE_MS) {
    const speechMs = vadLastVoiceAt - vadSpeechStartedAt
    vadSpeaking = false
    if (speechMs >= VAD_MIN_SPEECH_MS) {
      routeAsrCandidate('vad')
      // 探活：VAD（独立麦克风音量监测）明确听到一段话，但识别器在这段时间内毫无信号，
      // 说明 SpeechRecognition 已僵死（典型为打断后），自动干净重建以恢复拾音。
      if (
        shouldListen &&
        !tts.speakingNow.value &&
        Date.now() - lastAsrSignalAt > RECOGNITION_DEAD_SIGNAL_MS
      ) {
        forceRestartRecognition()
      }
    }
  }

  vadRaf = requestAnimationFrame(vadLoop)
}

function clearStartWatchdog() {
  if (startWatchdog) {
    clearTimeout(startWatchdog)
    startWatchdog = 0
  }
}

// 启动看门狗：start() 调用后若迟迟收不到 onstart/onaudiostart，判定为僵尸会话并强制重建。
function armStartWatchdog() {
  clearStartWatchdog()
  startWatchdog = window.setTimeout(() => {
    startWatchdog = 0
    if (!recognitionAlive && shouldListen) {
      recognitionRestarting = false
      forceRestartRecognition()
    }
  }, RECOGNITION_START_WATCHDOG_MS)
}

// 与「手动关→开麦克风」等价的干净重建：中止并重建识别实例 + 回收 VAD 麦克风流。
// 打断后识别变僵尸、或 start() 反复抛 InvalidStateError 时调用，确保下一句仍能录入。
function forceRestartRecognition() {
  if (!shouldListen) return
  if (recognitionRestarting) return
  recognitionRestarting = true
  clearStartWatchdog()
  if (restartTimer) {
    clearTimeout(restartTimer)
    restartTimer = 0
  }
  recognitionAlive = false
  stopVad()
  setupRecognition()
  restartTimer = window.setTimeout(() => {
    restartTimer = 0
    startRecognition()
  }, 350)
}

// 语音打断后延迟做一次干净重建（全自动，等价于用户手动开关麦克风）。
function scheduleBargeInRecycle() {
  if (!shouldListen) return
  if (bargeInRecycleTimer) clearTimeout(bargeInRecycleTimer)
  bargeInRecycleTimer = window.setTimeout(() => {
    bargeInRecycleTimer = 0
    if (shouldListen) forceRestartRecognition()
  }, BARGE_IN_RECYCLE_MS)
}

function scheduleRecognitionRestart() {
  if (!recognition || restartTimer) return
  restartTimer = window.setTimeout(() => {
    restartTimer = 0
    startRecognition()
  }, 350)
}

function startRecognition() {
  if (!recognition || !shouldListen) return
  void startVad()
  recognitionAlive = false
  try {
    recognition.start()
    listening.value = true
    lastAsrSignalAt = Date.now()
    armStartWatchdog()
  } catch (err: any) {
    listening.value = false
    // InvalidStateError：Chrome 仍把上一段识别视为「运行中」（打断后常见的僵尸态）。
    // 反复 start() 只会持续抛错，必须 abort + 重建实例才能恢复拾音。
    if (err?.name === 'InvalidStateError') {
      forceRestartRecognition()
    } else {
      scheduleRecognitionRestart()
    }
  }
}

function stopRecognition() {
  shouldListen = false
  micEnabled.value = false
  cancelDuckRestore()
  clearStartWatchdog()
  recognitionRestarting = false
  recognitionAlive = false
  if (bargeInRecycleTimer) {
    clearTimeout(bargeInRecycleTimer)
    bargeInRecycleTimer = 0
  }
  if (restartTimer) {
    clearTimeout(restartTimer)
    restartTimer = 0
  }
  if (routeTimer) {
    clearTimeout(routeTimer)
    routeTimer = 0
  }
  clearPendingAsrRoute()
  pendingTranscript = ''
  clearAsrCandidate()
  lastRoutedTranscript = ''
  lastRoutedAt = 0
  lastVadRoutedTranscript = ''
  lastVadRoutedAt = 0
  stopVad()
  if (!recognition) return
  try {
    recognition.stop()
  } catch {
    /* ignore invalid state */
  }
  listening.value = false
}

function toggleMic() {
  if (!recognition) return
  if (shouldListen) {
    stopRecognition()
  } else {
    shouldListen = true
    micEnabled.value = true
    startRecognition()
  }
}

function handleVisibilityChange() {
  if (document.visibilityState === 'hidden') {
    tts.stop()
  }
}

const hasRecognition = computed(
  () => !!((window as any).webkitSpeechRecognition || (window as any).SpeechRecognition)
)

onMounted(() => {
  store.connect()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})
onUnmounted(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  if (thinkingTimer) clearTimeout(thinkingTimer)
  stopRecognition()
  tts.stop()
})
</script>

<template>
  <div class="stage">
    <div class="bg-aurora"></div>
    <div class="bg-grid"></div>

    <!-- 顶部品牌 / 状态 -->
    <header class="top">
      <div class="brand">
        <span class="logo"><AppIcon name="shark" :size="34" /></span>
        <div>
          <div class="brand-name">巨鲨数字助教 · 鲨鲨</div>
          <div class="brand-sub">一句话，帮您安排一场考试</div>
        </div>
      </div>
      <div class="status">
        <span class="chip"><i class="dot" :class="connected ? 'ok' : 'err'"></i>{{ connected ? '在线' : '重连中' }}</span>
        <span class="chip state-chip"><i class="dot run"></i>{{ stateText }}</span>
      </div>
    </header>

    <!-- 数字形象舞台 -->
    <main class="persona">
      <div class="halo" :class="`halo--${sharkState}`"></div>
      <div class="shark-wrap">
        <SharkAvatar :state="sharkState" :mouth="mouth" />
      </div>
      <div class="state-name">
        <span class="pulse-dot"></span>{{ stateText }}
      </div>
      <div class="viz">
        <span v-for="(b, i) in bars" :key="i" class="viz-bar" :style="{ transform: `scaleY(${b})` }"></span>
      </div>
    </main>

    <!-- 用户语音气泡：实时草稿（聆听中）/ 最终输入 -->
    <transition name="v">
      <div v-if="liveTranscript || userText" class="user-bubble" :class="{ draft: !!liveTranscript }">
        <span class="u-label">{{ liveTranscript ? '聆听中' : '您说' }}</span>{{ liveTranscript || userText }}<span v-if="liveTranscript" class="u-caret">▍</span>
      </div>
    </transition>

    <!-- 字幕 -->
    <section class="subtitle glass" :class="{ 'is-thinking': thinking }">
      <div class="sub-tag">鲨鲨</div>
      <transition name="v" mode="out-in">
        <p v-if="thinking" key="thinking" class="sub-text thinking-text">
          {{ thinkingHint }}<span class="think-dots"><i></i><i></i><i></i></span>
        </p>
        <p v-else key="speak" class="sub-text" :class="{ speaking: sharkState === 'speaking' }">{{ assistantText }}</p>
      </transition>
      <transition name="v">
        <button v-if="speaking && started" class="barge-btn" @click="bargeIn" title="打断鲨鲨">
          <AppIcon name="mic" :size="16" /> 打断
        </button>
      </transition>
    </section>

    <!-- 语音交互 dock（仅语音） -->
    <footer class="dock">
      <template v-if="hasRecognition">
        <button class="mic" :class="{ on: micEnabled }" @click="toggleMic" title="点击说话">
          <AppIcon name="mic" :size="30" />
          <span class="mic-ring"></span>
        </button>
        <div class="mic-hint">
          <div class="mic-state">{{ micStateText }}</div>
          <transition name="v">
            <div v-if="voiceHint" class="mic-tip">{{ voiceHint }}</div>
          </transition>
        </div>
      </template>
      <div v-else class="no-mic glass">
        当前浏览器不支持语音识别，请使用 Chrome 或在控制台推进演示。
      </div>
    </footer>

    <!-- 开场遮罩 -->
    <transition name="v">
      <div v-if="!started" class="overlay" @click="start">
        <div class="overlay-card glass">
          <div class="ov-shark"><SharkAvatar state="idle" :mouth="0" /></div>
          <h1 class="title-grad">巨鲨数字助教 · 鲨鲨</h1>
          <p>轻触屏幕，开始与鲨鲨语音对话</p>
          <button class="btn primary big" @click.stop="start">
            <AppIcon name="mic" :size="20" /> 开始对话
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.stage {
  position: relative;
  height: 100vh;
  width: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.top {
  position: relative;
  z-index: 2;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 22px 30px;
}
.brand { display: flex; align-items: center; gap: 14px; }
.logo {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  color: var(--cyan);
  background: var(--glass-2);
  border: 1px solid var(--line);
}
.brand-name { font-size: 20px; font-weight: 800; letter-spacing: 0.5px; }
.brand-sub { font-size: 13px; color: var(--muted); letter-spacing: 0.5px; margin-top: 2px; }
.status { display: flex; gap: 10px; }
.state-chip { color: var(--aqua); }

.persona {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.shark-wrap {
  width: min(50vh, 460px);
  height: min(50vh, 460px);
  position: relative;
  z-index: 2;
}
.halo {
  position: absolute;
  width: min(64vh, 620px);
  height: min(64vh, 620px);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(56, 189, 248, 0.2), transparent 65%);
  filter: blur(10px);
  z-index: 1;
  transition: background 0.6s ease;
  animation: floatY 7s ease-in-out infinite;
}
.halo--working { background: radial-gradient(circle, rgba(34, 211, 238, 0.3), transparent 65%); }
.halo--thinking { background: radial-gradient(circle, rgba(139, 92, 246, 0.26), transparent 65%); }
.halo--success { background: radial-gradient(circle, rgba(251, 191, 36, 0.28), transparent 65%); }
.halo--soft_warning { background: radial-gradient(circle, rgba(251, 146, 60, 0.26), transparent 65%); }
.state-name {
  position: relative;
  z-index: 2;
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 17px;
  color: var(--aqua);
  letter-spacing: 2px;
}
.pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--aqua);
  box-shadow: 0 0 14px var(--aqua);
  animation: pulse 1.4s ease-in-out infinite;
}
.viz {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 36px;
  margin-top: 14px;
  z-index: 2;
}
.viz-bar {
  width: 6px;
  height: 36px;
  border-radius: 4px;
  background: linear-gradient(180deg, var(--aqua), var(--violet));
  transform-origin: bottom;
  transition: transform 0.09s ease;
  opacity: 0.85;
}

.user-bubble {
  position: absolute;
  top: 100px;
  right: 36px;
  z-index: 3;
  max-width: 420px;
  padding: 12px 18px;
  border-radius: 16px 16px 4px 16px;
  background: linear-gradient(92deg, rgba(56, 189, 248, 0.22), rgba(139, 92, 246, 0.22));
  border: 1px solid var(--line);
  font-size: 16px;
  backdrop-filter: blur(8px);
}
.u-label {
  display: inline-block;
  margin-right: 8px;
  font-size: 12px;
  color: var(--aqua);
  opacity: 0.9;
}
.user-bubble.draft {
  background: linear-gradient(92deg, rgba(56, 189, 248, 0.12), rgba(139, 92, 246, 0.12));
  border-style: dashed;
  opacity: 0.94;
}
.u-caret {
  margin-left: 1px;
  color: var(--aqua);
  animation: pulse 0.7s steps(1) infinite;
}

.subtitle {
  position: relative;
  z-index: 2;
  margin: 0 auto;
  width: min(960px, 92%);
  padding: 18px 26px;
  display: flex;
  align-items: center;
  gap: 18px;
}
.sub-tag {
  flex: none;
  font-weight: 800;
  color: var(--aqua);
  font-size: 18px;
}
.sub-text {
  margin: 0;
  font-size: 21px;
  line-height: 1.5;
  flex: 1;
}
.sub-text.speaking::after {
  content: '▍';
  margin-left: 4px;
  animation: pulse 0.7s steps(1) infinite;
  color: var(--aqua);
}
.barge-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid rgba(255, 122, 122, 0.55);
  background: rgba(255, 80, 80, 0.16);
  color: #ff9d9d;
  font-weight: 700;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.1s ease;
}
.barge-btn:hover {
  background: rgba(255, 80, 80, 0.28);
}
.barge-btn:active {
  transform: scale(0.95);
}
.subtitle.is-thinking {
  border-color: rgba(139, 92, 246, 0.42);
  box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.18) inset;
}
.thinking-text {
  color: var(--aqua);
  display: inline-flex;
  align-items: center;
}
.think-dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 10px;
}
.think-dots i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--aqua);
  display: inline-block;
  animation: thinkDot 1.2s ease-in-out infinite;
}
.think-dots i:nth-child(2) {
  animation-delay: 0.18s;
}
.think-dots i:nth-child(3) {
  animation-delay: 0.36s;
}
@keyframes thinkDot {
  0%, 100% {
    transform: translateY(0);
    opacity: 0.35;
  }
  50% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.dock {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 20px 30px 30px;
}
.mic {
  position: relative;
  width: 76px;
  height: 76px;
  border-radius: 50%;
  border: 1px solid var(--line);
  background: var(--glass-2);
  color: var(--text);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.2s ease;
}
.mic:hover { transform: translateY(-2px); border-color: rgba(56, 189, 248, 0.5); }
.mic.on {
  background: linear-gradient(92deg, var(--cyan), var(--violet));
  border: none;
  color: #04122e;
}
.mic > .icon {
  grid-area: 1 / 1;
}
.mic-ring {
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 2px solid transparent;
  pointer-events: none;
}
.mic.on .mic-ring {
  border-color: var(--aqua);
  animation: pulse 1.1s ease-in-out infinite;
}
.mic-hint { text-align: center; }
.mic-state { font-size: 14px; color: var(--muted); }
.mic-tip {
  margin-top: 4px;
  font-size: 13px;
  color: var(--aqua);
  letter-spacing: 0.5px;
}
.no-mic { padding: 14px 22px; font-size: 14px; color: var(--muted); }

.overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  background: rgba(4, 8, 22, 0.6);
  backdrop-filter: blur(8px);
  cursor: pointer;
}
.overlay-card {
  padding: 40px 56px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.ov-shark { width: 220px; height: 220px; }
.overlay-card h1 { margin: 6px 0 0; font-size: 32px; }
.overlay-card p { color: var(--muted); margin: 0 0 14px; }
.btn.big { padding: 14px 32px; font-size: 17px; display: inline-flex; align-items: center; gap: 10px; }
</style>
