"""Demo Shell 配置：从环境变量 / .env 读取。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# 加载 backend/.env（如存在）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")

# 项目根目录
_ROOT = _BACKEND_DIR.parent


class Settings:
    # 演示模式：mock | real | hybrid
    DEMO_MODE: str = os.getenv("DEMO_MODE", "hybrid")

    # Agent 核心模式：simulated（确定性编排，默认稳定）| claude（调用真实 Claude Code CLI）
    AGENT_MODE: str = os.getenv("AGENT_MODE", "simulated")

    # Claude Code 工作目录
    _CLAUDE_CORE_DIR_RAW: Path = Path(
        os.getenv("CLAUDE_CORE_DIR", str(_ROOT / "medteach-agent-core"))
    )
    CLAUDE_CORE_DIR: Path = (
        _CLAUDE_CORE_DIR_RAW
        if _CLAUDE_CORE_DIR_RAW.is_absolute()
        else (_BACKEND_DIR / _CLAUDE_CORE_DIR_RAW).resolve()
    )
    CLAUDE_TIMEOUT_SECONDS: int = int(os.getenv("CLAUDE_TIMEOUT_SECONDS", "30"))

    # ---- 真实智能体大脑：Claude Code + DeepSeek（cc + ds）----
    # 只要填了 API Key，智能体就强制优先走大模型；任何失败自动回退本地确定性编排。
    LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    # deepseek = 直连 DeepSeek API（最稳）；claude_cli = 调用本机 Claude Code CLI + DeepSeek 后端。
    # 注意：该开关只影响「执行层（Agent 任务）」。进入技能前的「对话层」始终用 flash 直连 DeepSeek。
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    # DeepSeek（cc+ds 的 ds）密钥；兼容旧的 ANTHROPIC_AUTH_TOKEN
    DEEPSEEK_API_KEY: str = (
        os.getenv("DEEPSEEK_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or ""
    ).strip()
    DEEPSEEK_BASE_URL: str = (
        os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("ANTHROPIC_BASE_URL")
        or "https://api.deepseek.com"
    ).strip()
    # 执行层（Agent 任务）模型：CC + DeepSeek 的强模型，默认 deepseek-v4-pro。
    # 兼容旧字段 DEEPSEEK_MODEL / ANTHROPIC_MODEL。
    DEEPSEEK_AGENT_MODEL: str = (
        os.getenv("DEEPSEEK_AGENT_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or "deepseek-v4-pro"
    ).strip()
    # 对话层（进入技能前的自然聊天 / 意图识别）模型：flash 直连，默认 deepseek-v4-flash。
    DEEPSEEK_CHAT_MODEL: str = (
        os.getenv("DEEPSEEK_CHAT_MODEL") or "deepseek-v4-flash"
    ).strip()
    # 兼容别名：旧代码里引用的 DEEPSEEK_MODEL 一律指向执行层模型。
    DEEPSEEK_MODEL: str = DEEPSEEK_AGENT_MODEL
    # 对话层是否开启思考模式（默认关闭：低延迟、可流式、temperature 生效）。
    DEEPSEEK_CHAT_THINKING: bool = os.getenv(
        "DEEPSEEK_CHAT_THINKING", "false"
    ).strip().lower() in ("1", "true", "yes", "on")
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.5"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "400"))
    # 对话层流式回复的最大 token（控制语音播报时长，2~3 句即可）。
    LLM_CHAT_MAX_TOKENS: int = int(os.getenv("LLM_CHAT_MAX_TOKENS", "300"))
    # 语音交互关键路径的外部 LLM 预算。超出即使用确定性话术，避免用户等模型。
    VOICE_LLM_BUDGET_SECONDS: float = float(os.getenv("VOICE_LLM_BUDGET_SECONDS", "0.35"))

    # ---- 智能体编排引擎（让「意图→调真实工具→总结」真正由智能体驱动）----
    # deepseek = DeepSeek 直连编排（意图 LLM + 真实工具 + LLM 总结，秒级，最流畅）
    # claude   = 关键问答交给 Claude Code CLI 自主调真实工具（MCP），最贴合「交给 Claude」，但有 5~30s 延迟
    # hybrid   = 常规语音问答走 DeepSeek 快路径保流畅，复杂/显式任务可切 Claude 自主编排（默认）
    AGENT_ENGINE: str = os.getenv("AGENT_ENGINE", "hybrid").strip().lower()
    # 语音意图识别是否用 LLM 语义理解（正则始终作为零延迟优先 + 兜底）
    VOICE_INTENT_LLM: bool = os.getenv("VOICE_INTENT_LLM", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )
    # 业务回答是否用 LLM 基于真实数据自然改写（确定性模板始终作为事实基线 + 兜底）
    VOICE_SUMMARY_LLM: bool = os.getenv("VOICE_SUMMARY_LLM", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )
    # 意图识别的 LLM 预算（秒）：超时回退正则路由，避免语音卡顿
    VOICE_INTENT_LLM_BUDGET: float = float(os.getenv("VOICE_INTENT_LLM_BUDGET", "1.5"))
    # 业务总结的 LLM 预算（秒）：超时回退确定性模板话术
    VOICE_SUMMARY_LLM_BUDGET: float = float(os.getenv("VOICE_SUMMARY_LLM_BUDGET", "3.0"))
    # Claude Code 自主调工具（agentic）超时（秒）
    CLAUDE_AGENTIC_TIMEOUT: int = int(os.getenv("CLAUDE_AGENTIC_TIMEOUT", "45"))
    # Claude Code 权限模式：headless `-p` 下普通调用留空（依赖 --allowedTools 已足够，
    # 且 claude 2.x headless 不会卡在权限提示）；获授权后的重试用 bypassPermissions 放行。
    # 可选值：default / acceptEdits / bypassPermissions（留空=不显式传，用 CLI 默认）。
    CLAUDE_PERMISSION_MODE: str = os.getenv("CLAUDE_PERMISSION_MODE", "").strip()
    # 语音授权：开启后，本场首次「Claude 自主访问真实教学平台数据」需先经语音授权
    # （把原先 TEACHING_PLATFORM_ALLOW_WRITE 这类「文字/配置授权」搬到自然语音交互）。
    # 默认关闭：常规展厅读类问答零摩擦、不打断流畅度；需要演示授权链路时设 true。
    CLAUDE_VOICE_AUTH: bool = os.getenv("CLAUDE_VOICE_AUTH", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )

    # 前台占用保护窗口（秒）：用户刚说话/打断后的这段时间内，后台「过程类」主动播报
    # （进度安抚 / heartbeat）主动让路，不抢占语音交互通道。语音交互即 UI，必须始终优先。
    FOREGROUND_HOLD_SECONDS: float = float(os.getenv("FOREGROUND_HOLD_SECONDS", "6"))

    # 演示节奏（每个子步骤之间的动画停顿，秒）
    STEP_DELAY: float = float(os.getenv("STEP_DELAY", "0.9"))
    PROGRESS_DELAY: float = float(os.getenv("PROGRESS_DELAY", "1.4"))

    # ---- 阿里云智能语音交互 TTS ----
    # 方式 A：直接提供 NLS AccessToken（不是 sk- 开头的大模型 API Key）
    ALIYUN_NLS_TOKEN: str = os.getenv("ALIYUN_NLS_TOKEN", "").strip()
    # 方式 B：提供 AccessKey，由服务端自动换取 NLS Token
    ALIYUN_AK_ID: str = os.getenv("ALIYUN_AK_ID", "").strip()
    ALIYUN_AK_SECRET: str = os.getenv("ALIYUN_AK_SECRET", "").strip()
    # 两种方式都需要 AppKey
    ALIYUN_NLS_APPKEY: str = os.getenv("ALIYUN_NLS_APPKEY", "").strip()
    ALIYUN_NLS_REGION: str = os.getenv("ALIYUN_NLS_REGION", "cn-shanghai").strip()
    ALIYUN_NLS_VOICE: str = os.getenv("ALIYUN_NLS_VOICE", "zhixiaobai").strip()
    ALIYUN_NLS_FORMAT: str = os.getenv("ALIYUN_NLS_FORMAT", "mp3").strip()
    ALIYUN_NLS_SAMPLE_RATE: int = int(os.getenv("ALIYUN_NLS_SAMPLE_RATE", "16000"))

    @staticmethod
    def _looks_like_general_api_key(value: str) -> bool:
        """NLS Token is an access token, not a DashScope/DeepSeek/OpenAI-style API key."""
        return value.startswith("sk-")

    @property
    def aliyun_nls_token_valid(self) -> bool:
        return bool(self.ALIYUN_NLS_TOKEN) and not self._looks_like_general_api_key(
            self.ALIYUN_NLS_TOKEN
        )

    @property
    def aliyun_ak_configured(self) -> bool:
        return bool(self.ALIYUN_AK_ID and self.ALIYUN_AK_SECRET)

    @property
    def aliyun_tts_disabled_reason(self) -> Literal[
        "missing_appkey",
        "missing_credentials",
        "invalid_nls_token",
    ] | None:
        if not self.ALIYUN_NLS_APPKEY:
            return "missing_appkey"
        if self.aliyun_nls_token_valid or self.aliyun_ak_configured:
            return None
        if self.ALIYUN_NLS_TOKEN:
            return "invalid_nls_token"
        return "missing_credentials"

    @property
    def aliyun_tts_enabled(self) -> bool:
        return self.aliyun_tts_disabled_reason is None

    # ---- 大模型智能体 ----
    @property
    def chat_llm_configured(self) -> bool:
        """对话层（flash 直连 DeepSeek）是否可用：取决于是否填了 DeepSeek Key。"""
        return self.LLM_ENABLED and bool(self.DEEPSEEK_API_KEY)

    @property
    def voice_intent_llm_enabled(self) -> bool:
        """语音意图是否用 LLM 语义识别（需开关开启且 DeepSeek 可用）。"""
        return self.VOICE_INTENT_LLM and self.chat_llm_configured

    @property
    def voice_summary_llm_enabled(self) -> bool:
        """业务回答是否用 LLM 自然改写（需开关开启且 DeepSeek 可用）。"""
        return self.VOICE_SUMMARY_LLM and self.chat_llm_configured

    @property
    def claude_agentic_enabled(self) -> bool:
        """是否启用 Claude Code 自主调真实工具通道（agentic）。"""
        return (
            self.AGENT_ENGINE in ("claude", "hybrid")
            and self.LLM_ENABLED
            and bool(self.DEEPSEEK_API_KEY)
        )

    @property
    def claude_voice_auth_enabled(self) -> bool:
        """是否启用「语音授权」链路（需开关开启且 agentic 通道可用）。"""
        return self.CLAUDE_VOICE_AUTH and self.claude_agentic_enabled

    @property
    def llm_configured(self) -> bool:
        """智能体是否具备真实接入条件（决定现场控制台显示「真实接入」还是「兜底」）。

        对话层与执行层都基于 DeepSeek，只要填了 Key 即视为已接入。
        """
        return self.chat_llm_configured

    @property
    def agent_provider_label(self) -> str:
        """执行层（Agent 任务）标签。"""
        if self.LLM_PROVIDER == "claude_cli":
            return f"CC + DeepSeek · {self.DEEPSEEK_AGENT_MODEL}"
        return f"DeepSeek · {self.DEEPSEEK_AGENT_MODEL}"

    @property
    def llm_provider_label(self) -> str:
        if not self.llm_configured:
            return "本地编排"
        return f"对话 DeepSeek·{self.DEEPSEEK_CHAT_MODEL} ｜ 执行 {self.agent_provider_label}"

    @property
    def deepseek_chat_url(self) -> str:
        """由 base url 推导 OpenAI 兼容的 chat/completions 端点。"""
        base = self.DEEPSEEK_BASE_URL.rstrip("/")
        if base.endswith("/anthropic"):
            base = base[: -len("/anthropic")].rstrip("/")
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"


settings = Settings()
