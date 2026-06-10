"""可选：Claude Code CLI 集成（LLM_PROVIDER=claude_cli 时启用）。

默认 LLM_PROVIDER=deepseek 直连 DeepSeek API，本模块不会被调用。
若设为 claude_cli，则由 agent_brain 调用本模块，用本机 Claude Code CLI + DeepSeek 后端
完成意图识别与话术生成；任何失败都会回退到本地确定性编排，保证不影响演示。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger("claude_client")

# Claude 自主调工具通道暴露的真实只读工具（对应 medteach-agent-core/mcp_server.py）。
_MCP_TOOLS = (
    "get_data_board",
    "get_present_students",
    "search_students",
    "list_exams",
    "get_exam_result",
    "list_questions",
    "recommend_cases",
    "list_teaching_plans",
)

_AGENTIC_SYSTEM_PROMPT = """你是「巨鲨数字助教·鲨鲨」，医学教学展厅的语音数字助教。
老师刚说了一句话。请判断他想了解哪一项教学业务，调用合适的 medteach 工具获取**真实**数据，再用口语化、专业、简洁的中文（1~3 句，适合朗读）回答老师。

规则：
- 必须先调用工具拿到真实数据再回答，不能凭空编造任何数字。
- 工具返回里若 fallback=true，说明用的是演示兑底数据，请如实说明（可说"这是演示数据"），不要谎称是真实平台数据。
- 用第一人称"我"、称呼老师"您"，像现场助教自然接话；不要出现"工具、接口、JSON、系统、字段"等工程术语。
- 不输出针对真实病人的临床诊断建议，只做教学与训练分析。

最后只输出一个 JSON 对象（不要 Markdown、不要多余解释）：
{"assistant_text": "<要朗读给老师听的话>", "tool": "<你调用的主要工具名，没有则留空>", "fallback": <true 或 false，是否用了演示数据>}"""


class ClaudeCodeClient:
    def __init__(self) -> None:
        self.core_dir = settings.CLAUDE_CORE_DIR
        self.timeout = settings.CLAUDE_TIMEOUT_SECONDS

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        # DeepSeek via Anthropic 兼容接口：把 .env 里的 DeepSeek 配置注入给 claude CLI，
        # 这样 cc + ds 的组合无需用户再手动导出环境变量。
        if settings.DEEPSEEK_API_KEY:
            env.setdefault("ANTHROPIC_AUTH_TOKEN", settings.DEEPSEEK_API_KEY)
            env.setdefault("ANTHROPIC_API_KEY", settings.DEEPSEEK_API_KEY)
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        if base:
            if not base.endswith("/anthropic"):
                base = base + "/anthropic"
            env.setdefault("ANTHROPIC_BASE_URL", base)
        if settings.DEEPSEEK_AGENT_MODEL:
            env.setdefault("ANTHROPIC_MODEL", settings.DEEPSEEK_AGENT_MODEL)
        return env

    async def run_agent_turn(self, system_prompt: str, user_text: str) -> dict[str, Any]:
        """单轮意图路由：调用 claude -p，附加系统提示，返回解析后的 JSON。"""
        cmd = [
            "claude",
            "-p",
            user_text,
            "--output-format",
            "json",
            "--max-turns",
            "1",
            "--append-system-prompt",
            system_prompt,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.core_dir),
            env=self._env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError("Claude Code 调用超时")
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude 退出码 {proc.returncode}: {stderr.decode(errors='ignore')[:400]}"
            )
        raw = stdout.decode(errors="ignore").strip()
        try:
            outer = json.loads(raw)
            result_text = outer.get("result", raw) if isinstance(outer, dict) else raw
        except json.JSONDecodeError:
            result_text = raw
        return self._extract_json(result_text)

    async def run_turn(self, prompt: str) -> dict[str, Any]:
        """调用 claude -p，返回解析后的 JSON（要求 Core 输出 JSON）。"""
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            "8",
        ]
        rules = self.core_dir / "prompts" / "demo_runtime_rules.md"
        if rules.exists():
            cmd += ["--append-system-prompt-file", str(rules)]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.core_dir),
            env=self._env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError("Claude Code 调用超时")

        if proc.returncode != 0:
            raise RuntimeError(f"claude 退出码 {proc.returncode}: {stderr.decode(errors='ignore')[:400]}")

        raw = stdout.decode(errors="ignore").strip()
        # claude --output-format json 外层是元信息，result 字段为模型文本
        try:
            outer = json.loads(raw)
            result_text = outer.get("result", raw) if isinstance(outer, dict) else raw
        except json.JSONDecodeError:
            result_text = raw
        return self._extract_json(result_text)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        return json.loads(text)

    async def generate_plan_text(self, plan: dict[str, Any]) -> str | None:
        prompt = (
            "用户说：帮我给今天现场的规培学员安排一场胸部 CT 基础考试，时间控制在 15 分钟。"
            "请仅输出符合 output_schema 的 JSON，其中 assistant_text 用一段简洁的展厅播报话术，"
            f"描述如下方案并询问是否确认：{json.dumps(plan, ensure_ascii=False)}"
        )
        try:
            data = await self.run_turn(prompt)
            return data.get("assistant_text")
        except Exception as exc:  # noqa: BLE001
            logger.warning("generate_plan_text failed: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Claude 自主调工具（agentic）：让 Claude 自己选 MCP 工具、调真实平台、总结
    # ------------------------------------------------------------------ #
    def _ensure_mcp_config(self, mode: str | None = None) -> Path:
        """运行时生成 .mcp.json：让 claude CLI 以 stdio 启动真实工具 server。

        用当前后端解释器（venv，有 httpx）启动 MCP server；系统 python3 无 httpx。
        平台凭据（TEACHING_PLATFORM_*）随子进程环境传入，确保能直连真实平台。
        """
        server_py = self.core_dir / "mcp_server.py"
        server_env = {
            k: v for k, v in os.environ.items()
            if k.startswith("TEACHING_PLATFORM_") or k == "DEMO_MODE"
        }
        effective_mode = (
            mode or server_env.get("TEACHING_PLATFORM_MODE")
            or os.getenv("DEMO_MODE", "hybrid")
        )
        server_env["TEACHING_PLATFORM_MODE"] = effective_mode
        cfg = {
            "mcpServers": {
                "medteach": {
                    "command": sys.executable,
                    "args": [str(server_py)],
                    "env": server_env,
                }
            }
        }
        path = self.core_dir / ".mcp.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    async def run_agentic_query(
        self, user_text: str, *, mode: str | None = None
    ) -> dict[str, Any]:
        """Claude 自主选 MCP 工具 + 调真实工具箱 + 总结。

        返回 {assistant_text, tool, fallback}。任何失败向上抛，由网关回退 DeepSeek 快路径。
        """
        mcp_config = self._ensure_mcp_config(mode)
        allowed = ",".join(f"mcp__medteach__{t}" for t in _MCP_TOOLS)
        cmd = [
            "claude", "-p", user_text,
            "--output-format", "json",
            "--max-turns", "6",
            "--mcp-config", str(mcp_config),
            "--allowedTools", allowed,
            "--append-system-prompt", _AGENTIC_SYSTEM_PROMPT,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.core_dir),
            env=self._env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.CLAUDE_AGENTIC_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError("Claude 自主调工具超时")
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude 退出码 {proc.returncode}: {stderr.decode(errors='ignore')[:400]}"
            )
        raw = stdout.decode(errors="ignore").strip()
        try:
            outer = json.loads(raw)
            result_text = outer.get("result", raw) if isinstance(outer, dict) else raw
        except json.JSONDecodeError:
            result_text = raw
        return self._extract_json(result_text)


claude_client = ClaudeCodeClient()
