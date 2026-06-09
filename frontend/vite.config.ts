import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Demo Shell 后端默认监听 8000，Vite dev 通过代理转发 /api 与 /ws
type RuntimeProcess = {
  env?: {
    BACKEND_URL?: string
    HTTPS?: string
    ENABLE_HTTPS?: string
  }
}

const runtimeProcess = (globalThis as typeof globalThis & { process?: RuntimeProcess }).process
const BACKEND = runtimeProcess?.env?.BACKEND_URL || 'http://localhost:8000'

// HTTPS（远程演示）：HTTPS=1 且证书存在时，让 Vite dev 走 TLS，
// 这样其他机器经 IP 访问也能拿到麦克风权限（浏览器安全上下文要求）。
// 浏览器 → Vite 走 https/wss，Vite → 后端仍走 http/ws（本机内部转发，无需证书）。
const httpsEnabled = ['1', 'true'].includes(
  (runtimeProcess?.env?.HTTPS || runtimeProcess?.env?.ENABLE_HTTPS || '').toLowerCase()
)
const certDir = fileURLToPath(new URL('../backend/certs', import.meta.url))
const certFile = `${certDir}/cert.pem`
const keyFile = `${certDir}/key.pem`
const httpsConfig =
  httpsEnabled && existsSync(certFile) && existsSync(keyFile)
    ? { cert: readFileSync(certFile), key: readFileSync(keyFile) }
    : undefined

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    https: httpsConfig,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND.replace('http', 'ws'), ws: true }
    }
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500
  }
})
