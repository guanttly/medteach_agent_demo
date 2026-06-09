<script setup lang="ts">
import { computed } from 'vue'
import type { SharkState } from '../types'

const props = withDefaults(
  defineProps<{ state: SharkState; mouth?: number }>(),
  { mouth: 0 }
)

const speaking = computed(() => props.state === 'speaking')
const mouthOpen = computed(() =>
  speaking.value ? Math.min(1, Math.max(0, props.mouth ?? 0)) : 0
)
const mouthScale = computed(() => 0.12 + mouthOpen.value * 0.92)
const rootClass = computed(() => `shark shark--${props.state}`)

const showRing = computed(() => ['working', 'thinking'].includes(props.state))
const showWaves = computed(() => props.state === 'listening')
const showThink = computed(() => props.state === 'thinking')
const showData = computed(() => props.state === 'working')
const showSpark = computed(() => props.state === 'success')
const showConfirm = computed(() => props.state === 'waiting_confirm')
const showWarn = computed(() => props.state === 'soft_warning')
const showHappy = computed(() => props.state === 'success')
</script>

<template>
  <div :class="rootClass">
    <svg class="shark-svg" viewBox="0 0 440 480" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="auraG" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="rgba(56,189,248,.5)" />
          <stop offset="55%" stop-color="rgba(56,189,248,.12)" />
          <stop offset="100%" stop-color="rgba(56,189,248,0)" />
        </radialGradient>
        <linearGradient id="bodyG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#7fdaf2" />
          <stop offset="50%" stop-color="#46a8da" />
          <stop offset="100%" stop-color="#2b73bc" />
        </linearGradient>
        <linearGradient id="bellyG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#f6fcff" />
          <stop offset="100%" stop-color="#d6ecfb" />
        </linearGradient>
        <linearGradient id="finG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#3a9fd6" />
          <stop offset="100%" stop-color="#235fa6" />
        </linearGradient>
      </defs>

      <!-- 光环 -->
      <circle class="aura" cx="220" cy="250" r="196" fill="url(#auraG)" />

      <!-- 数据环（工作 / 思考） -->
      <g class="ring" v-if="showRing">
        <circle cx="220" cy="250" r="198" fill="none" stroke="rgba(56,189,248,.45)" stroke-width="2" stroke-dasharray="6 16" />
        <circle class="ring-2" cx="220" cy="250" r="216" fill="none" stroke="rgba(139,92,246,.4)" stroke-width="2" stroke-dasharray="2 20" />
      </g>

      <!-- 声波（倾听·左右对称） -->
      <g class="waves" v-if="showWaves" stroke="var(--aqua)" stroke-width="4" fill="none" stroke-linecap="round">
        <path class="wave" d="M78 212 q -22 38 0 76" />
        <path class="wave" d="M58 194 q -34 56 0 112" />
        <path class="wave" d="M362 212 q 22 38 0 76" />
        <path class="wave" d="M382 194 q 34 56 0 112" />
      </g>

      <!-- 主体 -->
      <g class="body-group">
        <!-- 尾鳍（身后） -->
        <path class="tail tail-l" d="M198 396 C 178 420, 164 432, 150 440 C 174 440, 198 426, 212 408 Z" fill="url(#finG)" />
        <path class="tail tail-r" d="M242 396 C 262 420, 276 432, 290 440 C 266 440, 242 426, 228 408 Z" fill="url(#finG)" />

        <!-- 胸鳍（左右对称） -->
        <path class="pfin pfin-l" d="M120 266 C 74 280, 46 318, 48 360 C 88 342, 118 322, 140 304 Z" fill="url(#finG)" />
        <path class="pfin pfin-r" d="M320 266 C 366 280, 394 318, 392 360 C 352 342, 322 322, 300 304 Z" fill="url(#finG)" />

        <!-- 背鳍 -->
        <path class="dorsal" d="M220 100 C 213 130, 207 156, 205 178 L235 178 C 233 156, 227 130, 220 100 Z" fill="url(#finG)" />

        <!-- 身体 -->
        <path
          class="body"
          d="M220 122 C 150 122, 92 172, 92 248 C 92 344, 150 408, 220 408 C 290 408, 348 344, 348 248 C 348 172, 290 122, 220 122 Z"
          fill="url(#bodyG)"
        />
        <!-- 腹部高光 -->
        <path
          class="belly"
          d="M220 198 C 170 198, 142 240, 142 300 C 142 358, 178 400, 220 400 C 262 400, 298 358, 298 300 C 298 240, 270 198, 220 198 Z"
          fill="url(#bellyG)"
          opacity="0.95"
        />

        <!-- 听诊器 -->
        <path d="M170 212 C 150 264, 158 312, 200 326" fill="none" stroke="#1f6f8b" stroke-width="6" stroke-linecap="round" />
        <path d="M270 212 C 290 264, 282 312, 240 326" fill="none" stroke="#1f6f8b" stroke-width="6" stroke-linecap="round" />
        <circle cx="170" cy="212" r="5" fill="#1f6f8b" />
        <circle cx="270" cy="212" r="5" fill="#1f6f8b" />
        <circle cx="220" cy="332" r="15" fill="#1f6f8b" />
        <circle cx="220" cy="332" r="6.5" fill="#bfe9fc" />

        <!-- 胸前红十字徽章 -->
        <g class="badge">
          <rect x="150" y="292" width="30" height="30" rx="9" fill="#fff" />
          <rect x="161" y="298" width="8" height="18" rx="2.5" fill="#ef4d6b" />
          <rect x="156" y="303" width="18" height="8" rx="2.5" fill="#ef4d6b" />
        </g>

        <!-- 脸部 -->
        <g class="face">
          <!-- 额头额镜（医者标识） -->
          <circle cx="220" cy="150" r="17" fill="#e6f2fc" stroke="#a6cdec" stroke-width="3" />
          <circle cx="220" cy="150" r="6.5" fill="#15618a" />
          <circle cx="215" cy="145" r="2.6" fill="#fff" opacity="0.9" />

          <!-- 腮红 -->
          <ellipse class="cheek" cx="150" cy="256" rx="20" ry="12" fill="rgba(244,114,182,.5)" />
          <ellipse class="cheek" cx="290" cy="256" rx="20" ry="12" fill="rgba(244,114,182,.5)" />

          <!-- 眉 -->
          <rect class="brow brow-l" x="150" y="172" width="44" height="9" rx="5" fill="#173453" />
          <rect class="brow brow-r" x="246" y="172" width="44" height="9" rx="5" fill="#173453" />

          <!-- 普通眼睛 -->
          <g class="eyes-normal">
            <ellipse class="eye-white" cx="180" cy="218" rx="32" ry="39" fill="#fff" />
            <ellipse class="eye-white" cx="260" cy="218" rx="32" ry="39" fill="#fff" />
            <g class="pupil-g">
              <circle cx="182" cy="224" r="15" fill="#10243f" />
              <circle cx="176" cy="217" r="6" fill="#fff" />
              <circle cx="188" cy="229" r="3" fill="#fff" opacity="0.8" />
            </g>
            <g class="pupil-g">
              <circle cx="258" cy="224" r="15" fill="#10243f" />
              <circle cx="252" cy="217" r="6" fill="#fff" />
              <circle cx="264" cy="229" r="3" fill="#fff" opacity="0.8" />
            </g>
          </g>

          <!-- 开心眯眼（完成） -->
          <g class="happy-eyes" v-if="showHappy" stroke="#10243f" stroke-width="7" stroke-linecap="round" fill="none">
            <path d="M160 222 Q 180 200 200 222" />
            <path d="M240 222 Q 260 200 280 222" />
          </g>

          <!-- 嘴：闭合微笑 + 萌牙 -->
          <g v-if="!speaking" class="smile-g">
            <path class="smile" d="M186 288 C 200 312, 240 312, 254 288" fill="none" stroke="#15324f" stroke-width="6" stroke-linecap="round" />
            <path d="M204 296 l9 0 l-4.5 9 z" fill="#fff" />
            <path d="M227 296 l9 0 l-4.5 9 z" fill="#fff" />
          </g>
          <!-- 嘴：说话张合 -->
          <g v-else class="mouth-open-g" :style="{ transform: `scaleY(${mouthScale})` }">
            <ellipse cx="220" cy="300" rx="26" ry="22" fill="#0c2138" />
            <path d="M196 300 a24 13 0 0 0 48 0 Z" fill="#ef6d8a" />
            <rect x="202" y="281" width="36" height="5" rx="2.5" fill="#fff" opacity="0.92" />
          </g>
        </g>
      </g>

      <!-- 思考气泡 -->
      <g class="think" v-if="showThink" fill="rgba(234,242,255,.9)">
        <circle class="bub" cx="300" cy="118" r="9" />
        <circle class="bub" cx="330" cy="90" r="7" />
        <circle class="bub" cx="356" cy="66" r="5" />
      </g>

      <!-- 工作数据流 -->
      <g class="data" v-if="showData" fill="var(--aqua)">
        <rect class="d-dot" x="96" y="150" width="8" height="8" rx="2" />
        <rect class="d-dot" x="70" y="220" width="6" height="6" rx="2" />
        <rect class="d-dot" x="338" y="160" width="7" height="7" rx="2" />
        <rect class="d-dot" x="362" y="240" width="9" height="9" rx="2" />
        <circle class="d-dot" cx="86" cy="320" r="4" />
      </g>

      <!-- 成功星光 -->
      <g class="spark" v-if="showSpark" fill="var(--gold)">
        <path class="star" d="M96 150 l6 14 14 6 -14 6 -6 14 -6 -14 -14 -6 14 -6 Z" />
        <path class="star" d="M344 120 l5 11 11 5 -11 5 -5 11 -5 -11 -11 -5 11 -5 Z" />
        <path class="star" d="M360 320 l4 9 9 4 -9 4 -4 9 -4 -9 -9 -4 9 -4 Z" />
        <path class="star" d="M80 320 l4 9 9 4 -9 4 -4 9 -4 -9 -9 -4 9 -4 Z" />
      </g>

      <!-- 等待确认气泡 -->
      <g class="confirm" v-if="showConfirm">
        <rect x="304" y="92" width="56" height="46" rx="14" fill="#fff" />
        <path d="M324 138 l-10 14 -2 -16 Z" fill="#fff" />
        <text x="332" y="124" text-anchor="middle" font-size="30" font-weight="700" fill="#2c74bd">?</text>
      </g>

      <!-- 兜底提示 -->
      <g class="warn" v-if="showWarn">
        <path d="M332 84 l30 52 -60 0 Z" fill="#fbbf24" />
        <rect x="329" y="104" width="6" height="18" rx="3" fill="#7a4d04" />
        <circle cx="332" cy="129" r="3.4" fill="#7a4d04" />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.shark {
  position: relative;
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 22px 34px rgba(4, 20, 50, 0.45));
  transition: filter 0.5s ease;
}
.shark-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}
.shark-svg .tail,
.shark-svg .pfin,
.shark-svg .dorsal,
.shark-svg .ring,
.shark-svg .ring-2,
.shark-svg .aura,
.shark-svg .body-group,
.shark-svg .eye-white,
.shark-svg .star,
.shark-svg .mouth-open-g,
.shark-svg .badge {
  transform-box: fill-box;
  transform-origin: center;
}

.aura { animation: auraPulse 4s ease-in-out infinite; }
@keyframes auraPulse {
  0%, 100% { opacity: 0.55; transform: scale(0.95); }
  50% { opacity: 0.95; transform: scale(1.06); }
}

.body-group { animation: bob 4.4s ease-in-out infinite; transform-box: fill-box; transform-origin: center; }
@keyframes bob {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-12px) scale(1.012); }
}

.dorsal { animation: dorsalSway 4s ease-in-out infinite; transform-origin: bottom; }
@keyframes dorsalSway {
  0%, 100% { transform: rotate(-3deg); }
  50% { transform: rotate(3deg); }
}

.pfin-l { transform-origin: 78% 22%; animation: finL 3.2s ease-in-out infinite; }
.pfin-r { transform-origin: 22% 22%; animation: finR 3.2s ease-in-out infinite; }
@keyframes finL {
  0%, 100% { transform: rotate(-5deg); }
  50% { transform: rotate(11deg); }
}
@keyframes finR {
  0%, 100% { transform: rotate(5deg); }
  50% { transform: rotate(-11deg); }
}

.tail-l { transform-origin: 90% 0%; animation: finL 2.8s ease-in-out infinite; }
.tail-r { transform-origin: 10% 0%; animation: finR 2.8s ease-in-out infinite; }

.ring { animation: spin 16s linear infinite; transform-origin: 220px 250px; }
.ring-2 { animation: spin 22s linear infinite reverse; transform-origin: 220px 250px; }

.pupil-g { transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1); }
.brow { transition: transform 0.4s ease; transform-box: fill-box; transform-origin: center; }
.mouth-open-g { transition: transform 0.07s linear; transform-box: fill-box; transform-origin: 220px 300px; }
.cheek { transition: opacity 0.4s ease; }

/* ---------- 倾听 ---------- */
.wave { animation: waveOut 1.8s ease-out infinite; opacity: 0; }
.wave:nth-child(2) { animation-delay: 0.25s; }
.wave:nth-child(3) { animation-delay: 0.12s; }
.wave:nth-child(4) { animation-delay: 0.37s; }
@keyframes waveOut {
  0% { opacity: 0; }
  45% { opacity: 0.9; }
  100% { opacity: 0; }
}
.shark--listening .eye-white { transform: scaleY(1.1); }
.shark--listening .body-group { animation-duration: 5.2s; }

/* ---------- 思考 ---------- */
.shark--thinking .pupil-g { transform: translateY(-8px); }
.shark--thinking .brow { transform: translateY(-4px); }
.bub { animation: floatUp 2.6s ease-in-out infinite; }
.bub:nth-child(2) { animation-delay: 0.4s; }
.bub:nth-child(3) { animation-delay: 0.8s; }
@keyframes floatUp {
  0% { opacity: 0.2; transform: translateY(8px) scale(0.85); }
  50% { opacity: 1; }
  100% { opacity: 0.2; transform: translateY(-10px) scale(1.05); }
}

/* ---------- 说话 ---------- */
.shark--speaking .body-group { animation-duration: 3.2s; }

/* ---------- 工作 ---------- */
.shark--working .body-group { animation-duration: 2.6s; }
.shark--working .pfin-l,
.shark--working .pfin-r { animation-duration: 1.6s; }
.d-dot { animation: floatUp 2.1s ease-in-out infinite; }
.d-dot:nth-child(2) { animation-delay: 0.3s; }
.d-dot:nth-child(3) { animation-delay: 0.6s; }
.d-dot:nth-child(4) { animation-delay: 0.9s; }
.d-dot:nth-child(5) { animation-delay: 1.2s; }

/* ---------- 等待确认 ---------- */
.shark--waiting_confirm .body-group { animation: nod 1.9s ease-in-out infinite; }
@keyframes nod {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(4px) rotate(2.5deg); }
}
.confirm { animation: pop 1.6s ease-in-out infinite; transform-box: fill-box; transform-origin: 332px 115px; }

/* ---------- 成功 ---------- */
.shark--success .body-group { animation: bounce 1.1s ease infinite; }
@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  30% { transform: translateY(-22px); }
  55% { transform: translateY(-4px); }
}
.star { animation: pop 1.4s ease-in-out infinite; }
.star:nth-child(2) { animation-delay: 0.35s; }
.star:nth-child(3) { animation-delay: 0.7s; }
.star:nth-child(4) { animation-delay: 1s; }
@keyframes pop {
  0%, 100% { opacity: 0; transform: scale(0.4); }
  50% { opacity: 1; transform: scale(1); }
}

/* ---------- 兜底提示 ---------- */
.shark--soft_warning { filter: hue-rotate(-26deg) saturate(1.08) drop-shadow(0 20px 30px rgba(80, 50, 4, 0.38)); }
.shark--soft_warning .body-group { animation: shake 1.3s ease-in-out infinite; }
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-6px) rotate(-1.5deg); }
  75% { transform: translateX(6px) rotate(1.5deg); }
}
.warn { animation: pulse 1.2s ease-in-out infinite; transform-box: fill-box; transform-origin: 332px 110px; }

/* ---------- 待命 ---------- */
.shark--idle .body-group { animation-duration: 4.8s; }
</style>
