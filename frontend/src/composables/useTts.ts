import { ref } from 'vue'
import { fetchTtsConfig, ttsStreamUrl } from '../api/client'
import { useDemoStore } from '../stores/demo'

/**
 * 数字形象语音播报（真·流式音频版）。
 *
 * 后端按「句」推送文本；本模块把每句通过专用 WebSocket 发给 Demo Shell，服务端实时调用
 * 阿里云流式语音合成，把 PCM 音频帧「边合成边」回推；前端用 Web Audio 无缝调度播放，
 * 首字音频通常数百毫秒内出声，避免「整句合成完才出声」的十几秒等待。
 *
 * 模块级单例：同一页面只允许一个音频通道出声。speakingNow 在整段播报期间保持 true，
 * 供页面挂起麦克风、避免数字人自问自答。
 *
 * 阿里云未配置 / 合成失败时，自动逐句回退浏览器 SpeechSynthesis。
 */
const enabled = ref(false)
const speakingNow = ref(false)

let activeStore: ReturnType<typeof useDemoStore> | null = null

// ---- Web Audio 播放图：bufferSource → gain → analyser → destination ----
let ctx: AudioContext | null = null
let gainNode: GainNode | null = null
let analyser: AnalyserNode | null = null
let mouthBuf: Uint8Array | null = null
let mouthRaf = 0
let browserTimer = 0
let browserKeepAlive = 0
let browserTimeout = 0

// ---- 流式 PCM 调度 ----
let nextStartTime = 0
const activeSources = new Set<AudioBufferSourceNode>()
let streamSampleRate = 16000
let pcmRemainder: Uint8Array | null = null
let currentRecvId = -1
let pendingPcmChunks: Uint8Array[] = []
let pcmFlushActive = false
let pcmFlushSeq = 0

// ---- 后端流式 TTS 通道 ----
let ttsWs: WebSocket | null = null
let wsConnecting = false
let wsPing = 0
let provider: 'aliyun' | 'browser' | 'unknown' = 'unknown'
let configLoaded = false
let sendBuffer: number[] = []

// ---- 句级请求跟踪 ----
let reqSeq = 0
let pendingSynth = 0
const liveReqs = new Set<number>()
const reqText = new Map<number, string>()

// ---- 浏览器兜底队列 ----
let browserQueue: string[] = []
let browserActive = false
let browserPumpSeq = 0

// ---- 运行/取消代 + 输入流状态 ----
let runId = 0
let streamOpen = false

const DUCK_GAIN = 0.45
const MAX_PENDING_PCM_CHUNKS = 240
const SENTENCE_SPLIT = /[^。！？!?；;…\n]*[。！？!?；;…\n]|[^。！？!?；;…\n]+$/g

function setMouth(v: number) {
  activeStore?.setMouth(v)
}

function resumeAudioContext(): Promise<boolean> {
  if (!ctx) return Promise.resolve(false)
  if (ctx.state === 'running') return Promise.resolve(true)
  return ctx
    .resume()
    .then(() => ctx?.state === 'running')
    .catch(() => false)
}

async function ensureAudioContextRunning(): Promise<boolean> {
  if (!ctx) return false
  if (ctx.state === 'running') return true
  if (await resumeAudioContext()) return true
  await new Promise((resolve) => setTimeout(resolve, 160))
  return resumeAudioContext()
}

function enable() {
  if (!ctx) {
    const AC = (window as any).AudioContext || (window as any).webkitAudioContext
    if (AC) {
      try {
        ctx = new AC()
        gainNode = ctx.createGain()
        gainNode.gain.value = 1
        analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        mouthBuf = new Uint8Array(analyser.frequencyBinCount)
        gainNode.connect(analyser)
        analyser.connect(ctx.destination)
      } catch {
        ctx = null
      }
    }
  }
  resumeAudioContext()
  if (!ctx) {
    // 没有 Web Audio：只能走浏览器 TTS
    provider = 'browser'
    configLoaded = true
  }
  try {
    window.speechSynthesis?.getVoices()
  } catch {
    /* noop */
  }
  enabled.value = true
  void ensureConfig()
}

async function ensureConfig() {
  if (configLoaded) return
  configLoaded = true
  try {
    const cfg = await fetchTtsConfig()
    provider = cfg?.enabled ? 'aliyun' : 'browser'
  } catch {
    provider = 'browser'
  }
  if (provider === 'aliyun') connectWs()
}

function splitSentences(text: string): string[] {
  const t = (text || '').trim()
  if (!t) return []
  const matches = t.match(SENTENCE_SPLIT)
  if (!matches) return [t]
  const out: string[] = []
  for (const m of matches) {
    const s = m.trim()
    if (s) out.push(s)
  }
  return out.length ? out : [t]
}

// ------------------------------------------------------------------ //
// 后端流式 TTS WebSocket
// ------------------------------------------------------------------ //
function connectWs() {
  if (ttsWs && (ttsWs.readyState === WebSocket.OPEN || ttsWs.readyState === WebSocket.CONNECTING)) {
    return
  }
  if (wsConnecting) return
  wsConnecting = true
  let ws: WebSocket
  try {
    ws = new WebSocket(ttsStreamUrl())
  } catch {
    wsConnecting = false
    provider = 'browser'
    return
  }
  ws.binaryType = 'arraybuffer'
  ttsWs = ws
  ws.onopen = () => {
    wsConnecting = false
    if (wsPing) clearInterval(wsPing)
    wsPing = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ type: 'ping' }))
        } catch {
          /* noop */
        }
      }
    }, 15000)
    // 冲刷连接期间排队的合成请求
    const ids = sendBuffer
    sendBuffer = []
    for (const id of ids) {
      const t = reqText.get(id)
      if (t && liveReqs.has(id)) wsSend({ type: 'synthesize', id, text: t })
    }
  }
  ws.onmessage = (e) => handleWsMessage(e)
  ws.onerror = () => {
    /* 关闭回调里统一兜底 */
  }
  ws.onclose = () => {
    wsConnecting = false
    if (wsPing) {
      clearInterval(wsPing)
      wsPing = 0
    }
    if (ttsWs === ws) ttsWs = null
    handleWsDropped()
  }
}

function wsSend(obj: Record<string, unknown>): boolean {
  const ws = ttsWs
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(obj))
      return true
    } catch {
      return false
    }
  }
  return false
}

/** 连接断开：把还没拿到音频的句子统统改用浏览器 TTS（保序）。 */
function handleWsDropped() {
  if (reqText.size) {
    const ids = [...reqText.keys()].sort((a, b) => a - b)
    for (const id of ids) {
      const t = reqText.get(id)
      reqText.delete(id)
      if (liveReqs.has(id)) {
        liveReqs.delete(id)
        pendingSynth = Math.max(0, pendingSynth - 1)
      }
      if (t) browserQueue.push(t)
    }
    ensureBrowserPump()
  }
  sendBuffer = []
  currentRecvId = -1
  maybeIdle()
}

function handleWsMessage(e: MessageEvent) {
  const data = e.data
  if (data instanceof ArrayBuffer) {
    if (currentRecvId >= 0 && liveReqs.has(currentRecvId)) {
      enqueuePcm(new Uint8Array(data))
    }
    return
  }
  if (data instanceof Blob) {
    const recvId = currentRecvId
    if (recvId >= 0 && liveReqs.has(recvId)) {
      void data
        .arrayBuffer()
        .then((buf) => {
          if (recvId >= 0 && recvId === currentRecvId && liveReqs.has(recvId)) {
            enqueuePcm(new Uint8Array(buf))
          }
        })
        .catch(() => undefined)
    }
    return
  }
  let msg: any
  try {
    msg = JSON.parse(data as string)
  } catch {
    return
  }
  switch (msg.type) {
    case 'config':
      if (msg.sample_rate) streamSampleRate = msg.sample_rate
      provider = msg.provider === 'aliyun' ? 'aliyun' : 'browser'
      break
    case 'start':
      currentRecvId = msg.id
      if (msg.sample_rate) streamSampleRate = msg.sample_rate
      pcmRemainder = null
      break
    case 'end':
      completeReq(msg.id)
      break
    case 'fallback': {
      const text = reqText.get(msg.id) || msg.text || ''
      const wasLive = liveReqs.has(msg.id)
      completeReq(msg.id)
      if (wasLive && text) {
        browserQueue.push(text)
        ensureBrowserPump()
      }
      break
    }
    default:
      break
  }
}

function completeReq(id: number) {
  reqText.delete(id)
  if (liveReqs.has(id)) {
    liveReqs.delete(id)
    pendingSynth = Math.max(0, pendingSynth - 1)
  }
  if (currentRecvId === id) currentRecvId = -1
  maybeIdle()
}

function sendSynthesize(text: string) {
  const id = ++reqSeq
  liveReqs.add(id)
  reqText.set(id, text)
  pendingSynth += 1
  if (!wsSend({ type: 'synthesize', id, text })) {
    sendBuffer.push(id)
    connectWs()
  }
}

// ------------------------------------------------------------------ //
// 流式 PCM 播放（无缝调度）
// ------------------------------------------------------------------ //
function enqueuePcm(bytes: Uint8Array) {
  if (!bytes.length) return
  pendingPcmChunks.push(bytes)
  if (pendingPcmChunks.length > MAX_PENDING_PCM_CHUNKS) {
    pendingPcmChunks.splice(0, pendingPcmChunks.length - MAX_PENDING_PCM_CHUNKS)
  }
  void flushPcmQueue()
}

async function flushPcmQueue() {
  if (pcmFlushActive) return
  pcmFlushActive = true
  const seq = pcmFlushSeq
  try {
    const ok = await ensureAudioContextRunning()
    if (seq !== pcmFlushSeq) return
    if (!ok) {
      fallbackStreamToBrowser()
      return
    }
    while (pendingPcmChunks.length && seq === pcmFlushSeq) {
      const bytes = pendingPcmChunks.shift()
      if (bytes) schedulePcm(bytes)
    }
  } finally {
    pcmFlushActive = false
  }
  if (pendingPcmChunks.length) void flushPcmQueue()
}

function fallbackStreamToBrowser() {
  provider = 'browser'
  pcmFlushSeq += 1
  pendingPcmChunks = []
  pcmRemainder = null
  currentRecvId = -1
  wsSend({ type: 'cancel' })
  sendBuffer = []
  if (reqText.size) {
    const ids = [...reqText.keys()].sort((a, b) => a - b)
    for (const id of ids) {
      const text = reqText.get(id)
      reqText.delete(id)
      if (liveReqs.has(id)) {
        liveReqs.delete(id)
        pendingSynth = Math.max(0, pendingSynth - 1)
      }
      if (text) browserQueue.push(text)
    }
    ensureBrowserPump()
  }
  maybeIdle()
}

function schedulePcm(bytes: Uint8Array) {
  if (!ctx || !gainNode) return
  resumeAudioContext()
  let buf = bytes
  if (pcmRemainder && pcmRemainder.length) {
    const merged = new Uint8Array(pcmRemainder.length + bytes.length)
    merged.set(pcmRemainder, 0)
    merged.set(bytes, pcmRemainder.length)
    buf = merged
  }
  const usableLen = buf.length - (buf.length % 2)
  pcmRemainder = usableLen < buf.length ? buf.slice(usableLen) : null
  if (usableLen <= 0) return

  const sampleCount = usableLen / 2
  const view = new DataView(buf.buffer, buf.byteOffset, usableLen)
  const f32 = new Float32Array(sampleCount)
  for (let i = 0; i < sampleCount; i++) {
    f32[i] = view.getInt16(i * 2, true) / 32768
  }
  let audioBuf: AudioBuffer
  try {
    audioBuf = ctx.createBuffer(1, sampleCount, streamSampleRate)
  } catch {
    return
  }
  audioBuf.copyToChannel(f32, 0)
  const src = ctx.createBufferSource()
  src.buffer = audioBuf
  src.connect(gainNode)

  const lead = 0.08
  const now = ctx.currentTime
  if (nextStartTime < now + 0.01) nextStartTime = now + lead
  const startAt = nextStartTime
  try {
    src.start(startAt)
  } catch {
    return
  }
  nextStartTime = startAt + audioBuf.duration
  activeSources.add(src)
  src.onended = () => {
    activeSources.delete(src)
    maybeIdle()
  }
  startMouthLoop()
}

function startMouthLoop() {
  if (mouthRaf || !analyser || !mouthBuf) return
  const loop = () => {
    if (!analyser || !mouthBuf) {
      mouthRaf = 0
      return
    }
    analyser.getByteTimeDomainData(mouthBuf)
    let sum = 0
    for (let i = 0; i < mouthBuf.length; i++) {
      const v = (mouthBuf[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / mouthBuf.length)
    setMouth(Math.min(1, rms * 3.2))
    const playing = activeSources.size > 0 || nextStartTime > (ctx?.currentTime ?? 0)
    if (playing) {
      mouthRaf = requestAnimationFrame(loop)
    } else {
      mouthRaf = 0
      setMouth(0)
    }
  }
  mouthRaf = requestAnimationFrame(loop)
}

function stopMouthLoop() {
  if (mouthRaf) cancelAnimationFrame(mouthRaf)
  mouthRaf = 0
  if (browserTimer) clearInterval(browserTimer)
  browserTimer = 0
  if (browserKeepAlive) clearInterval(browserKeepAlive)
  browserKeepAlive = 0
  if (browserTimeout) clearTimeout(browserTimeout)
  browserTimeout = 0
}

// ------------------------------------------------------------------ //
// 浏览器兜底（顺序播报）
// ------------------------------------------------------------------ //
function ensureBrowserPump() {
  if (browserActive) return
  void browserPump(++browserPumpSeq)
}

async function browserPump(pumpId: number) {
  browserActive = true
  while (browserQueue.length) {
    const text = browserQueue.shift() as string
    const my = runId
    await speakBrowserOnce(text, my)
    if (my !== runId) {
      if (browserPumpSeq === pumpId) browserActive = false
      return
    }
  }
  if (browserPumpSeq === pumpId) {
    browserActive = false
    maybeIdle()
  }
}

function speakBrowserOnce(text: string, myRun: number): Promise<void> {
  return new Promise<void>((resolve) => {
    if (myRun !== runId) return resolve()
    const synth = window.speechSynthesis
    if (!synth || !text) {
      return resolve()
    }

    const u = new SpeechSynthesisUtterance(text)
    u.lang = 'zh-CN'
    u.rate = 1.02
    u.pitch = 1.1
    const voices = synth.getVoices()
    const zh = voices.find((v) => v.lang?.toLowerCase().startsWith('zh'))
    if (zh) u.voice = zh

    let t = 0
    let started = false
    let settled = false
    const cleanup = (cancelCurrent: boolean) => {
      if (settled) return
      settled = true
      if (browserTimer) clearInterval(browserTimer)
      browserTimer = 0
      if (browserKeepAlive) clearInterval(browserKeepAlive)
      browserKeepAlive = 0
      if (browserTimeout) clearTimeout(browserTimeout)
      browserTimeout = 0
      if (cancelCurrent) {
        try {
          synth.cancel()
        } catch {
          /* noop */
        }
      }
      if (activeSources.size === 0) setMouth(0)
      resolve()
    }
    const done = () => cleanup(false)
    const startedAt = Date.now()
    const maxMs = Math.min(45000, Math.max(6000, text.length * 360 + 2500))

    if (browserTimer) clearInterval(browserTimer)
    browserTimer = window.setInterval(() => {
      if (myRun !== runId) {
        cleanup(false)
        return
      }
      t += 0.18
      const v = 0.45 + 0.45 * Math.abs(Math.sin(t * 6)) * (0.6 + Math.random() * 0.4)
      setMouth(Math.min(1, v))
    }, 60)

    if (browserKeepAlive) clearInterval(browserKeepAlive)
    browserKeepAlive = window.setInterval(() => {
      if (myRun !== runId) {
        cleanup(false)
        return
      }
      try {
        if (synth.paused) synth.resume()
        if (started && !synth.speaking && !synth.pending) cleanup(false)
        if (!started && Date.now() - startedAt > 1600 && !synth.speaking && !synth.pending) {
          cleanup(false)
        }
      } catch {
        cleanup(false)
      }
    }, 700)

    if (browserTimeout) clearTimeout(browserTimeout)
    browserTimeout = window.setTimeout(() => cleanup(true), maxMs)

    u.onstart = () => {
      started = true
    }
    u.onend = () => {
      if (myRun !== runId) return cleanup(false)
      done()
    }
    u.onerror = () => {
      if (myRun !== runId) return cleanup(false)
      done()
    }
    try {
      if (synth.paused) synth.resume()
      synth.speak(u)
    } catch {
      done()
    }
  })
}

// ------------------------------------------------------------------ //
// 空闲判定
// ------------------------------------------------------------------ //
function maybeIdle() {
  if (
    !streamOpen &&
    pendingSynth === 0 &&
    activeSources.size === 0 &&
    !browserActive &&
    browserQueue.length === 0
  ) {
    setIdle()
  }
}

function setIdle() {
  speakingNow.value = false
  stopMouthLoop()
  setMouth(0)
  nextStartTime = 0
  pcmRemainder = null
  pendingPcmChunks = []
}

// ------------------------------------------------------------------ //
// 对外 API
// ------------------------------------------------------------------ //
/** 开始一段新的流式播报：打开输入流（接到当前播报之后顺序播放）。 */
function reset() {
  if (!enabled.value) return
  resumeAudioContext()
  void ensureConfig()
  if (provider !== 'browser') connectWs()
  restore()
  streamOpen = true
  speakingNow.value = true
}

/** 追加一段文本（自动切句后逐句送合成）。 */
function enqueue(text: string) {
  if (!enabled.value) return
  resumeAudioContext()
  const parts = splitSentences(text)
  if (!parts.length) return
  speakingNow.value = true
  const useStream = provider !== 'browser'
  for (const p of parts) {
    if (useStream) {
      sendSynthesize(p)
    } else {
      browserQueue.push(p)
      ensureBrowserPump()
    }
  }
}

/** 标记输入流结束：所有音频播完后归位。 */
function finish() {
  streamOpen = false
  maybeIdle()
}

/** 一次性播报便捷入口（开场白 / 非流式播报）。 */
async function speak(text: string) {
  if (!text || !enabled.value) return
  reset()
  enqueue(text)
  finish()
}

/** 立即停止并清空（打断）。 */
function stop() {
  runId += 1
  streamOpen = false
  wsSend({ type: 'cancel' })
  sendBuffer = []
  liveReqs.clear()
  reqText.clear()
  pendingSynth = 0
  currentRecvId = -1
  pcmRemainder = null
  pendingPcmChunks = []
  pcmFlushSeq += 1
  browserQueue = []
  browserPumpSeq += 1
  for (const src of activeSources) {
    try {
      src.onended = null
      src.stop()
    } catch {
      /* ignore */
    }
    try {
      src.disconnect()
    } catch {
      /* ignore */
    }
  }
  activeSources.clear()
  nextStartTime = 0
  try {
    window.speechSynthesis?.cancel()
  } catch {
    /* noop */
  }
  browserActive = false
  stopMouthLoop()
  setMouth(0)
  restore()
  speakingNow.value = false
}

/** 压低当前播报音量（用户疑似插话时的瞬时反馈，不清空队列）。 */
function duck() {
  if (gainNode && ctx) {
    try {
      gainNode.gain.cancelScheduledValues(ctx.currentTime)
      gainNode.gain.setValueAtTime(gainNode.gain.value, ctx.currentTime)
      gainNode.gain.setTargetAtTime(DUCK_GAIN, ctx.currentTime, 0.05)
    } catch {
      gainNode.gain.value = DUCK_GAIN
    }
  }
}

/** 恢复正常播报音量（确认是回声、放弃插话时调用）。 */
function restore() {
  if (gainNode && ctx) {
    try {
      gainNode.gain.cancelScheduledValues(ctx.currentTime)
      gainNode.gain.setValueAtTime(gainNode.gain.value, ctx.currentTime)
      gainNode.gain.setTargetAtTime(1, ctx.currentTime, 0.06)
    } catch {
      gainNode.gain.value = 1
    }
  }
}

/** 唤醒音频上下文（页面回到前台、或浏览器在后台自动挂起后重新激活）。 */
function resume() {
  if (!enabled.value) return
  resumeAudioContext()
}

export function useTts() {
  activeStore = useDemoStore()
  return { enabled, speakingNow, enable, speak, reset, enqueue, finish, stop, duck, restore, resume }
}
