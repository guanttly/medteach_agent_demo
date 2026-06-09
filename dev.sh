#!/usr/bin/env bash
# 开发模式：后端(:8000) + 前端 Vite(:5173) 并行，支持热更新
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo "\n[dev] 停止服务 ..."
  [ -n "${BACK_PID:-}" ] && kill "$BACK_PID" 2>/dev/null || true
  [ -n "${FRONT_PID:-}" ] && kill "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[dev] 启动后端 :8000 ..."
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if ! python -c "import fastapi" 2>/dev/null; then
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
fi
[ -f ".env" ] || cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACK_PID=$!

echo "[dev] 启动前端 :5173 ..."
cd "$ROOT/frontend"
[ -d "node_modules" ] || npm install

# HTTPS（远程演示）：HTTPS=1 时让 Vite dev 走 TLS（其他机器经 IP 访问才能用麦克风）。
HTTPS="${HTTPS:-${ENABLE_HTTPS:-0}}"
SCHEME="http"
if [ "$HTTPS" = "1" ] || [ "$HTTPS" = "true" ]; then
  if [ ! -f "$ROOT/backend/certs/cert.pem" ] || [ ! -f "$ROOT/backend/certs/key.pem" ]; then
    echo "[dev] 生成自签 TLS 证书 ..."
    bash "$ROOT/gen_cert.sh"
  fi
  export HTTPS=1
  SCHEME="https"
fi
npm run dev -- --host &
FRONT_PID=$!

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "[dev] 后端 http://localhost:8000   前端 ${SCHEME}://localhost:5173"
[ -n "$LAN_IP" ] && echo "[dev] 局域网其他机器访问前端：${SCHEME}://${LAN_IP}:5173"
wait
