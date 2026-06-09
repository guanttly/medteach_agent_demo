#!/usr/bin/env bash
# 启动 Demo Shell 后端
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[run] 创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi" 2>/dev/null; then
  echo "[run] 安装依赖 ..."
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
fi

if [ ! -f ".env" ]; then
  echo "[run] 未发现 .env，已复制 .env.example（可按需填入阿里云 TTS 凭据）"
  cp .env.example .env
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "[run] Demo Shell 启动于 http://${HOST}:${PORT}"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
