#!/usr/bin/env bash
# Self-extracting installer header for medteach-agent-demo.
set -euo pipefail

APP_NAME="medteach-agent-demo"
INSTALL_DIR="${INSTALL_DIR:-}"
PORT_OVERRIDE="${PORT:-}"
HTTPS_OVERRIDE="${HTTPS:-}"
START_AFTER_INSTALL=1
FORCE_ENV=0
COMPOSE_AVAILABLE=0
COMPOSE_CMD=()

log() {
  printf '[medteach-installer] %s\n' "$*"
}

die() {
  printf '[medteach-installer] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
用法:
  bash medteach-agent-demo-xxx.run [选项]

选项:
  --install-dir DIR   安装目录。root 默认 /opt/medteach-agent-demo，普通用户默认 ~/medteach-agent-demo
  --port PORT         对外端口，默认 8000
  --https            启用容器内自签 HTTPS
  --http             强制使用 HTTP
  --no-start         只安装/导入镜像，不启动服务
  --force-env        用包内模板覆盖安装目录已有 .env（会先备份）
  -h, --help         显示帮助

示例:
  bash medteach-agent-demo-20260611.run
  bash medteach-agent-demo-20260611.run --install-dir /opt/medteach-agent-demo --port 18000 --https
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"
}

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
    COMPOSE_AVAILABLE=1
  elif command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
    COMPOSE_AVAILABLE=1
  else
    log "未找到 docker compose，启动时将退回到 docker run。"
  fi
}

extract_payload() {
  local target_dir="$1"
  local payload_line
  payload_line="$(awk '/^__MEDTEACH_PAYLOAD_BELOW__$/ { print NR + 1; exit 0; }' "$0")"
  [ -n "$payload_line" ] || die "安装包格式错误：找不到 payload 标记。"
  tail -n +"$payload_line" "$0" | tar -xzf - -C "$target_dir"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local env_file="$INSTALL_DIR/.env"
  local tmp_file
  tmp_file="$(mktemp)"
  if [ -f "$env_file" ] && grep -q "^${key}=" "$env_file"; then
    awk -v key="$key" -v value="$value" '
      index($0, key "=") == 1 { print key "=" value; next }
      { print }
    ' "$env_file" > "$tmp_file"
  else
    [ -f "$env_file" ] && cp "$env_file" "$tmp_file"
    [ -s "$tmp_file" ] && printf '\n' >> "$tmp_file"
    printf '%s=%s\n' "$key" "$value" >> "$tmp_file"
  fi
  mv "$tmp_file" "$env_file"
}

get_env_value() {
  local key="$1"
  local env_file="$INSTALL_DIR/.env"
  [ -f "$env_file" ] || return 0
  awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); exit 0; }' "$env_file"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-dir)
      [ "$#" -ge 2 ] || die "--install-dir 需要目录参数"
      INSTALL_DIR="$2"
      shift 2
      ;;
    --install-dir=*)
      INSTALL_DIR="${1#*=}"
      shift
      ;;
    --port)
      [ "$#" -ge 2 ] || die "--port 需要端口参数"
      PORT_OVERRIDE="$2"
      shift 2
      ;;
    --port=*)
      PORT_OVERRIDE="${1#*=}"
      shift
      ;;
    --https)
      HTTPS_OVERRIDE=1
      shift
      ;;
    --http)
      HTTPS_OVERRIDE=0
      shift
      ;;
    --no-start)
      START_AFTER_INSTALL=0
      shift
      ;;
    --force-env)
      FORCE_ENV=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数: $1"
      ;;
  esac
done

require_command awk
require_command docker
require_command gzip
require_command mktemp
require_command tar
require_command tail

docker info >/dev/null 2>&1 || die "无法连接 Docker daemon。请确认 Docker 已启动，并用有 docker 权限的用户执行。"
[ "$START_AFTER_INSTALL" -eq 1 ] && detect_compose

if [ -z "$INSTALL_DIR" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    INSTALL_DIR="/opt/${APP_NAME}"
  else
    INSTALL_DIR="${HOME}/${APP_NAME}"
  fi
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
extract_payload "$TMP_DIR"

[ -f "$TMP_DIR/metadata.env" ] || die "安装包缺少 metadata.env。"
# shellcheck disable=SC1091
. "$TMP_DIR/metadata.env"
: "${IMAGE_REF:?metadata.env 缺少 IMAGE_REF}"

log "安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

log "导入镜像: $IMAGE_REF"
gzip -dc "$TMP_DIR/image.tar.gz" | docker load >/dev/null

if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
  cp "$INSTALL_DIR/docker-compose.yml" "$INSTALL_DIR/docker-compose.yml.bak.$(date +%Y%m%d%H%M%S)"
fi
cp "$TMP_DIR/docker-compose.yml" "$INSTALL_DIR/docker-compose.yml"

if [ -f "$INSTALL_DIR/.env" ] && [ "$FORCE_ENV" -ne 1 ]; then
  log "保留已有配置: $INSTALL_DIR/.env"
else
  if [ -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak.$(date +%Y%m%d%H%M%S)"
  fi
  cp "$TMP_DIR/env.example" "$INSTALL_DIR/.env"
  log "写入配置模板: $INSTALL_DIR/.env"
fi

[ -n "$PORT_OVERRIDE" ] && set_env_value PORT "$PORT_OVERRIDE"
[ -n "$HTTPS_OVERRIDE" ] && set_env_value HTTPS "$HTTPS_OVERRIDE"

if [ "$START_AFTER_INSTALL" -eq 1 ]; then
  log "启动服务"
  if [ "$COMPOSE_AVAILABLE" -eq 1 ]; then
    (cd "$INSTALL_DIR" && "${COMPOSE_CMD[@]}" -f docker-compose.yml up -d)
  else
    RUN_PORT="$(get_env_value PORT)"
    RUN_PORT="${RUN_PORT:-8000}"
    docker rm -f "$APP_NAME" >/dev/null 2>&1 || true
    docker run -d \
      --name "$APP_NAME" \
      --restart unless-stopped \
      --env-file "$INSTALL_DIR/.env" \
      -p "${RUN_PORT}:8000" \
      "$IMAGE_REF" >/dev/null
  fi
else
  log "已按 --no-start 跳过启动"
fi

PORT_VALUE="$(get_env_value PORT)"
PORT_VALUE="${PORT_VALUE:-8000}"
HTTPS_VALUE="$(get_env_value HTTPS)"
SCHEME="http"
case "$HTTPS_VALUE" in
  1|true|TRUE|yes|YES) SCHEME="https" ;;
esac
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

log "安装完成"
printf '  安装目录: %s\n' "$INSTALL_DIR"
printf '  本机访问: %s://localhost:%s/home\n' "$SCHEME" "$PORT_VALUE"
[ -n "$LAN_IP" ] && printf '  局域网访问: %s://%s:%s/home\n' "$SCHEME" "$LAN_IP" "$PORT_VALUE"
printf '  常用页面: /screen  /avatar  /control\n'
if [ "$COMPOSE_AVAILABLE" -eq 1 ]; then
  printf '  管理命令: cd %s && %s -f docker-compose.yml ps\n' "$INSTALL_DIR" "${COMPOSE_CMD[*]}"
else
  printf '  管理命令: docker ps --filter name=%s\n' "$APP_NAME"
fi

exit 0
__MEDTEACH_PAYLOAD_BELOW__
