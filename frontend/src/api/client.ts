// REST + WebSocket 客户端。开发态经由 Vite 代理转发到 Demo Shell (8000)。

export const SESSION_ID = 'demo_001'

async function post<T = any>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return res.json()
}

export const api = {
  sendMessage: (message: string, session_id = SESSION_ID) =>
    post('/api/demo/message', { session_id, message }),
  // 前台交互通道：统一用户输入（语音/文本），支持 barge-in 打断。
  conversationTurn: (
    text: string,
    opts: {
      source?: string
      barge_in?: boolean
      interrupts_utterance_id?: string | null
      interrupt_policy?: string | null
    } = {},
    session_id = SESSION_ID
  ) =>
    post('/api/conversation/turn', {
      session_id,
      text,
      source: opts.source ?? 'voice',
      barge_in: opts.barge_in ?? false,
      interrupts_utterance_id: opts.interrupts_utterance_id ?? null,
      interrupt_policy: opts.interrupt_policy ?? null,
      client_time: Date.now() / 1000
    }),
  interrupt: (
    opts: {
      utterance_id?: string | null
      reason?: string
      policy?: string
      job_id?: string | null
      job_policy?: string
    } = {},
    session_id = SESSION_ID
  ) =>
    post('/api/conversation/interrupt', {
      session_id,
      utterance_id: opts.utterance_id ?? null,
      reason: opts.reason ?? 'user_barge_in',
      policy: opts.policy ?? 'stop_low_priority',
      job_id: opts.job_id ?? null,
      job_policy: opts.job_policy ?? 'continue'
    }),
  confirm: (confirmation_type: string, session_id = SESSION_ID) =>
    post('/api/demo/confirm', { session_id, confirmation_type }),
  publish: (session_id = SESSION_ID) => post('/api/demo/publish', { session_id }),
  reset: (session_id = SESSION_ID) => post('/api/demo/reset', { session_id }),
  setMode: (mode: string, session_id = SESSION_ID) => post('/api/demo/mode', { session_id, mode }),
  controlStep: (target_state: string, session_id = SESSION_ID) =>
    post('/api/demo/control/step', { session_id, target_state }),
  preset: (preset: string, session_id = SESSION_ID) =>
    post('/api/demo/control/preset', { session_id, preset }),
  simulateSubmit: (session_id = SESSION_ID) =>
    post('/api/demo/control/simulate-submit', { session_id }),
  getState: (session_id = SESSION_ID) =>
    fetch(`/api/demo/state?session_id=${session_id}`).then((r) => r.json()),
  getJobs: (session_id = SESSION_ID) =>
    fetch(`/api/sessions/${session_id}/jobs`).then((r) => r.json()),
  ttsConfig: () => fetch('/api/tts/config').then((r) => r.json())
}

export type TtsResult =
  | { mode: 'audio'; blob: Blob }
  | { mode: 'browser'; text: string }

export async function synthesize(text: string, voice?: string): Promise<TtsResult> {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice })
  })
  const ct = res.headers.get('Content-Type') || ''
  if (ct.startsWith('audio')) {
    return { mode: 'audio', blob: await res.blob() }
  }
  const j = await res.json().catch(() => ({}))
  return { mode: 'browser', text: j.text ?? text }
}

export function wsUrl(sessionId = SESSION_ID): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws/demo/${sessionId}`
}

/** 流式 TTS 通道：前端逐句发文本，服务端边合成边回推 PCM 音频帧。 */
export function ttsStreamUrl(sessionId = SESSION_ID): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws/tts/${sessionId}`
}

export interface TtsConfig {
  provider: string
  enabled: boolean
  voice?: string
}

export async function fetchTtsConfig(): Promise<TtsConfig> {
  try {
    const r = await fetch('/api/tts/config')
    return (await r.json()) as TtsConfig
  } catch {
    return { provider: 'browser', enabled: false }
  }
}
