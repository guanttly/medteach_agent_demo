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
from typing import Any

from .config import settings

logger = logging.getLogger("claude_client")


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


claude_client = ClaudeCodeClient()
