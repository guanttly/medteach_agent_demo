#!/usr/bin/env bash
# 一键启动（单端口）：构建前端 -> 后端在 :8000 同时托管前端与 API
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "[start] 1/3 清理并构建前端静态资源 ..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  npm install
fi
rm -rf "$ROOT/frontend/dist" "$ROOT/frontend/node_modules/.vite"
npm run build
BUILD_TIME="$(date '+%Y-%m-%d %H:%M:%S %z')"
GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
{
  echo "build_time=$BUILD_TIME"
  echo "git_sha=$GIT_SHA"
} > "$ROOT/frontend/dist/build-info.txt"
echo "[start] 前端已重新打包：$BUILD_TIME ($GIT_SHA)"

echo "[start] 2/3 准备后端环境 ..."
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
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "[start] 已生成 backend/.env（如需阿里云语音请填入凭据）"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# HTTPS（远程演示推荐）：设 HTTPS=1 启用 TLS。
# 其他机器经 IP 访问时，麦克风 / 语音识别只有在 HTTPS 安全上下文下才可用。
HTTPS="${HTTPS:-${ENABLE_HTTPS:-0}}"
SSL_ARGS=()
SCHEME="http"
if [ "$HTTPS" = "1" ] || [ "$HTTPS" = "true" ]; then
  CERT_DIR="$ROOT/backend/certs"
  if [ ! -f "$CERT_DIR/cert.pem" ] || [ ! -f "$CERT_DIR/key.pem" ]; then
    echo "[start] 生成自签 TLS 证书 ..."
    CERT_DIR="$CERT_DIR" bash "$ROOT/gen_cert.sh"
  fi
  SSL_ARGS=(--ssl-keyfile "$CERT_DIR/key.pem" --ssl-certfile "$CERT_DIR/cert.pem")
  SCHEME="https"
fi

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "[start] 3/3 启动 Demo Shell：${SCHEME}://localhost:${PORT}"
[ -n "$LAN_IP" ] && echo "        局域网其他机器访问：${SCHEME}://${LAN_IP}:${PORT}"
echo "        大屏 /screen   数字形象 /avatar   控制台 /control"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" "${SSL_ARGS[@]}"
