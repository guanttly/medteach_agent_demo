#!/usr/bin/env bash
# 容器入口：可选生成自签 TLS 证书 -> 在 :8000 单端口同时托管前端与 API。
# 设计要点：
#   · Claude Code 已在镜像内预装（claude --version 可用），DeepSeek 凭据经环境变量注入。
#   · ~/.claude.json 已在构建期预置（跳过全新容器首启引导 / 信任弹窗），此处幂等兜底。
#   · 缺 DeepSeek / 阿里云 Key 时自动走本地确定性兜底，演示永不翻车。
set -euo pipefail

APP_HOME="${APP_HOME:-/app}"
cd "$APP_HOME/backend"

# --- 幂等兜底：HOME 被卷覆盖或种子缺失时，补写 Claude onboarding 种子 ---
CLAUDE_CFG="${HOME:-/home/appuser}/.claude.json"
CORE_DIR="${CLAUDE_CORE_DIR:-$APP_HOME/medteach-agent-core}"
if [ ! -f "$CLAUDE_CFG" ]; then
  echo "[entrypoint] 写入 Claude onboarding 种子: $CLAUDE_CFG"
  cat > "$CLAUDE_CFG" <<JSON
{
  "hasCompletedOnboarding": true,
  "bypassPermissionsModeAccepted": true,
  "projects": {
    "${CORE_DIR}": {
      "hasTrustDialogAccepted": true,
      "projectOnboardingSeenCount": 1,
      "allowedTools": [],
      "history": []
    }
  }
}
JSON
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# --- 可选 HTTPS（远程演示推荐：浏览器麦克风/语音识别需安全上下文）---
HTTPS="${HTTPS:-${ENABLE_HTTPS:-0}}"
SSL_ARGS=()
SCHEME="http"
if [ "$HTTPS" = "1" ] || [ "$HTTPS" = "true" ]; then
  CERT_DIR="$APP_HOME/backend/certs"
  mkdir -p "$CERT_DIR"
  if [ ! -f "$CERT_DIR/cert.pem" ] || [ ! -f "$CERT_DIR/key.pem" ]; then
    echo "[entrypoint] 生成自签 TLS 证书 ..."
    CERT_DIR="$CERT_DIR" bash "$APP_HOME/gen_cert.sh" || echo "[entrypoint] 证书生成失败，回退 HTTP"
  fi
  if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    SSL_ARGS=(--ssl-keyfile "$CERT_DIR/key.pem" --ssl-certfile "$CERT_DIR/cert.pem")
    SCHEME="https"
  fi
fi

echo "[entrypoint] 启动 Demo Shell：${SCHEME}://0.0.0.0:${PORT}  (大屏 /screen · 数字形象 /avatar · 控制台 /control)"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT" "${SSL_ARGS[@]}"
