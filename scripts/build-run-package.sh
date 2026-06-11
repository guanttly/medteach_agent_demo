#!/usr/bin/env bash
# Build a self-extracting .run installer for server deployment.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="${APP_NAME:-medteach-agent-demo}"
IMAGE_REPO="${IMAGE_REPO:-medteach-agent-demo}"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
BUILD_PULL="${BUILD_PULL:-0}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-6}"
DOCKER_BUILD_PLATFORM="${DOCKER_BUILD_PLATFORM:-}"
SKIP_BUILD=0
RUN_FILE="${RUN_FILE:-}"
IMAGE_REF="${IMAGE_REF:-}"
VERSION="${VERSION:-}"

usage() {
  cat <<'EOF'
用法:
  ./scripts/build-run-package.sh [选项]

生成 dist/medteach-agent-demo-<version>.run。把该文件传到服务器后执行:
  bash medteach-agent-demo-<version>.run

选项:
  --version VERSION     指定版本号/文件名片段
  --image IMAGE         指定镜像名和标签，例如 registry/app:1.0.0
  --output FILE         指定输出 .run 文件路径
  --platform PLATFORM   传给 docker build --platform，例如 linux/amd64
  --pull                docker build 时拉取基础镜像
  --skip-build          不重新构建镜像，直接打包本地已有 --image/默认镜像
  -h, --help            显示帮助

常用环境变量:
  VERSION=20260611.1 DOCKER_BUILD_PLATFORM=linux/amd64 ./scripts/build-run-package.sh
EOF
}

log() {
  printf '[build-run] %s\n' "$*"
}

die() {
  printf '[build-run] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      [ "$#" -ge 2 ] || die "--version 需要参数"
      VERSION="$2"
      shift 2
      ;;
    --version=*)
      VERSION="${1#*=}"
      shift
      ;;
    --image)
      [ "$#" -ge 2 ] || die "--image 需要参数"
      IMAGE_REF="$2"
      shift 2
      ;;
    --image=*)
      IMAGE_REF="${1#*=}"
      shift
      ;;
    --output)
      [ "$#" -ge 2 ] || die "--output 需要参数"
      RUN_FILE="$2"
      shift 2
      ;;
    --output=*)
      RUN_FILE="${1#*=}"
      shift
      ;;
    --platform)
      [ "$#" -ge 2 ] || die "--platform 需要参数"
      DOCKER_BUILD_PLATFORM="$2"
      shift 2
      ;;
    --platform=*)
      DOCKER_BUILD_PLATFORM="${1#*=}"
      shift
      ;;
    --pull)
      BUILD_PULL=1
      shift
      ;;
    --skip-build)
      SKIP_BUILD=1
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
require_command date
require_command docker
require_command gzip
require_command mktemp
require_command tar

docker info >/dev/null 2>&1 || die "无法连接 Docker daemon。请确认 Docker 已启动，并用有 docker 权限的用户执行。"

GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
STAMP="$(date +%Y%m%d-%H%M%S)"
if [ -z "$VERSION" ]; then
  VERSION="$STAMP"
  [ -n "$GIT_SHA" ] && VERSION="${VERSION}-${GIT_SHA}"
fi

if [ -z "$IMAGE_REF" ]; then
  IMAGE_REF="${IMAGE_REPO}:${VERSION}"
fi

if [ -z "$RUN_FILE" ]; then
  RUN_FILE="$OUT_DIR/${APP_NAME}-${VERSION}.run"
fi

RUN_TEMPLATE="$ROOT/packaging/run-installer.sh"
COMPOSE_TEMPLATE="$ROOT/packaging/docker-compose.installer.yml"
ENV_TEMPLATE="$ROOT/.env.docker.example"
[ -f "$RUN_TEMPLATE" ] || die "缺少 $RUN_TEMPLATE"
[ -f "$COMPOSE_TEMPLATE" ] || die "缺少 $COMPOSE_TEMPLATE"
[ -f "$ENV_TEMPLATE" ] || die "缺少 $ENV_TEMPLATE"

if [ "$SKIP_BUILD" -eq 1 ]; then
  log "跳过构建，使用本地镜像: $IMAGE_REF"
  docker image inspect "$IMAGE_REF" >/dev/null || die "本地不存在镜像: $IMAGE_REF"
else
  build_args=(-t "$IMAGE_REF")
  [ "$BUILD_PULL" -eq 1 ] && build_args+=(--pull)
  [ -n "$DOCKER_BUILD_PLATFORM" ] && build_args+=(--platform "$DOCKER_BUILD_PLATFORM")
  log "构建镜像: $IMAGE_REF"
  docker build "${build_args[@]}" "$ROOT"
fi

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
PAYLOAD_DIR="$TMP_ROOT/payload"
mkdir -p "$PAYLOAD_DIR" "$OUT_DIR" "$(dirname "$RUN_FILE")"

log "导出镜像到 payload"
docker save "$IMAGE_REF" | gzip "-$COMPRESSION_LEVEL" > "$PAYLOAD_DIR/image.tar.gz"

awk -v image="$IMAGE_REF" '{ gsub(/__IMAGE_REF__/, image); print }' "$COMPOSE_TEMPLATE" > "$PAYLOAD_DIR/docker-compose.yml"
cp "$ENV_TEMPLATE" "$PAYLOAD_DIR/env.example"

BUILD_TIME="$(date '+%Y-%m-%d %H:%M:%S %z')"
{
  printf 'APP_NAME=%q\n' "$APP_NAME"
  printf 'IMAGE_REF=%q\n' "$IMAGE_REF"
  printf 'VERSION=%q\n' "$VERSION"
  printf 'BUILD_TIME=%q\n' "$BUILD_TIME"
  printf 'GIT_SHA=%q\n' "$GIT_SHA"
} > "$PAYLOAD_DIR/metadata.env"

PAYLOAD_TAR="$TMP_ROOT/payload.tar.gz"
tar -C "$PAYLOAD_DIR" -czf "$PAYLOAD_TAR" .

RUN_TMP="$RUN_FILE.tmp"
cat "$RUN_TEMPLATE" "$PAYLOAD_TAR" > "$RUN_TMP"
chmod +x "$RUN_TMP"
mv "$RUN_TMP" "$RUN_FILE"

SIZE="$(du -h "$RUN_FILE" | awk '{print $1}')"
log "完成: $RUN_FILE ($SIZE)"
log "上传到服务器后执行: bash $(basename "$RUN_FILE")"
