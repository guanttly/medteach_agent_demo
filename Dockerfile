# syntax=docker/dockerfile:1
# =============================================================================
# 巨鲨医用教学智能体展厅 Demo —— 单镜像（前端 + 后端 + 预装 Claude Code）
# 运行：FastAPI 单端口 :8000 同时托管两套前端与 API/WS。
# =============================================================================

############################
# Stage 1: 构建前端静态资源 #
############################
FROM node:20-bookworm-slim AS frontend
WORKDIR /build/frontend
# 先装依赖，利用层缓存（package* 不变则跳过重装）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # 产出 /build/frontend/dist

############################
# Stage 2: 运行时镜像       #
############################
FROM node:20-bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
# 系统依赖：Python venv（后端 + MCP server）、openssl（自签证书）、tini（信号转发/收割僵尸进程）
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip openssl ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

# 预装 Claude Code CLI（满足「claude code 需预装好」）；按平台拉取对应原生二进制
RUN npm install -g @anthropic-ai/claude-code \
 && claude --version

ENV APP_HOME=/app \
    VENV=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # 关闭 Claude 非必要外联 / 自动更新：减少容器内偶发失败与额外延迟
    DISABLE_AUTOUPDATER=1 \
    DISABLE_TELEMETRY=1 \
    DISABLE_ERROR_REPORTING=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

WORKDIR /app

# Python 依赖（先装依赖，利用层缓存）；MCP server 用同一 venv 解释器，故依赖齐全
COPY backend/requirements.txt /app/backend/requirements.txt
RUN python3 -m venv "$VENV" \
 && "$VENV/bin/pip" install --upgrade pip \
 && "$VENV/bin/pip" install -r /app/backend/requirements.txt

# 非 root 运行用户（更安全）；先建用户，便于后续 COPY 落到其 HOME
RUN useradd --create-home --uid 10001 appuser

# 应用代码：严格保持 <root>/backend、<root>/medteach-agent-core、<root>/frontend/dist 的相对布局
# （config.py 依据该布局推导 CLAUDE_CORE_DIR 与前端 dist 目录）
COPY backend/ /app/backend/
COPY medteach-agent-core/ /app/medteach-agent-core/
COPY gen_cert.sh /app/gen_cert.sh
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/claude.seed.json /home/appuser/.claude.json
COPY --from=frontend /build/frontend/dist /app/frontend/dist

# 权限：运行时需写入 .mcp.json（core 目录）、certs/（HTTPS）、~/.claude.json
RUN chmod +x /usr/local/bin/entrypoint.sh /app/gen_cert.sh \
 && mkdir -p /app/backend/certs \
 && chown -R appuser:appuser /app /home/appuser

USER appuser
EXPOSE 8000

# 健康检查：后端 /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
