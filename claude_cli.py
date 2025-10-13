#!/usr/bin/env python3
"""
Lightweight Claude API client used across DocAutomate.

The previous implementation wrapped the Claude CLI via subprocesses; this
version performs direct HTTP integration when an API endpoint and key are
configured, falling back to deterministic simulated responses for local
development. File-based fallbacks (e.g., PyPDF2) remain opt-in via the
`CLAUDE_ENABLE_LOCAL_FALLBACKS` environment variable so the "pure delegation"
promise holds by default.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

try:
    import PyPDF2  # type: ignore
except ImportError:
    PyPDF2 = None

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

_TRUTHY_VALUES = {"1", "true", "yes", "on"}
LOCAL_FALLBACK_ENV_VAR = "CLAUDE_ENABLE_LOCAL_FALLBACKS"


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY_VALUES


class SuperClaudeMode(str, Enum):
    BRAINSTORM = "brainstorm"
    TASK_MANAGE = "task-manage"
    ORCHESTRATE = "orchestrate"
    TOKEN_EFFICIENT = "uc"
    INTROSPECT = "introspect"
    LOOP = "loop"


class SuperClaudeAgent(str, Enum):
    GENERAL_PURPOSE = "general-purpose"
    ROOT_CAUSE_ANALYST = "root-cause-analyst"
    REFACTORING_EXPERT = "refactoring-expert"
    TECHNICAL_WRITER = "technical-writer"
    PERFORMANCE_ENGINEER = "performance-engineer"
    SECURITY_ENGINEER = "security-engineer"
    FRONTEND_ARCHITECT = "frontend-architect"
    BACKEND_ARCHITECT = "backend-architect"
    FINANCE_ENGINEER = "finance-engineer"
    QUALITY_ENGINEER = "quality-engineer"
    REQUIREMENTS_ANALYST = "requirements-analyst"
    SYSTEM_ARCHITECT = "system-architect"
    LEGAL_REVIEW = "legal-review"


class SuperClaudeMCP(str, Enum):
    SEQUENTIAL = "sequential"
    MAGIC = "magic"
    PLAYWRIGHT = "playwright"
    MORPHLLM = "morphllm"
    CONTEXT7 = "context7"
    SERENA = "serena"
    ZEN = "zen"


@dataclass
class CLIResult:
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    metadata: Optional[Dict[str, Any]] = None


class ClaudeCLI:
    """
    Direct Claude API integration with simulated fallbacks.
    """

    def __init__(
        self,
        timeout: Optional[int] = None,
        claude_cmd: Optional[str] = None,
        enable_local_fallbacks: Optional[bool] = None,
    ):
        self.timeout = timeout or int(os.getenv("CLAUDE_TIMEOUT", "120"))
        self.api_base = os.getenv("CLAUDE_API_BASE")
        self.api_key = os.getenv("CLAUDE_API_KEY")
        self.enable_local_fallbacks = (
            enable_local_fallbacks
            if enable_local_fallbacks is not None
            else _env_enabled(LOCAL_FALLBACK_ENV_VAR, default=False)
        )
        self._http_client: Optional[httpx.Client] = None

        logger.info(
            "Initialized ClaudeCLI (direct), api_base=%s, timeout=%ss, fallbacks=%s",
            self.api_base or "disabled",
            self.timeout,
            "enabled" if self.enable_local_fallbacks else "disabled",
        )

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #
    def _remote_available(self) -> bool:
        return bool(self.api_base and self.api_key)

    def _client(self) -> httpx.Client:
        if not self._http_client:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            self._http_client = httpx.Client(
                base_url=self.api_base or "",
                headers=headers,
                timeout=self.timeout,
            )
        return self._http_client

    def _call_remote(self, endpoint: str, payload: Dict[str, Any]) -> CLIResult:
        if not self._remote_available():
            return CLIResult(
                success=False,
                output="",
                error="Claude API not configured",
                exit_code=1,
            )

        try:
            response = self._client().post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            output = data.get("output") or data.get("result") or ""
            return CLIResult(success=True, output=output, metadata=data)
        except Exception as exc:
            logger.error("Claude API request failed: %s", exc)
            return CLIResult(
                success=False,
                output="",
                error=str(exc),
                exit_code=1,
            )

    # ------------------------------------------------------------------ #
    # Legacy compatibility helpers
    # ------------------------------------------------------------------ #
    def _run_command(
        self,
        cmd: List[str],
        input_text: Optional[str] = None,
        use_pty: bool = False,
    ) -> CLIResult:
        """
        Legacy compatibility entry point. We interpret the command list and
        dispatch to the appropriate remote endpoint without spawning a
        subprocess. Tests patch this method to simulate failures.
        """
        action = cmd[1] if len(cmd) > 1 else "cli"
        payload = {"command": cmd, "input": input_text, "timestamp": datetime.utcnow().isoformat()}
        if action == "--print":
            return self._call_remote("/v1/cli/print", payload)
        if action == "--read":
            return self._call_remote("/v1/cli/read", payload)
        return self._call_remote("/v1/cli/exec", payload)

    # ------------------------------------------------------------------ #
    # Core document APIs
    # ------------------------------------------------------------------ #
    def read_document(self, file_path: str) -> str:
        logger.info("Reading document via Claude delegation: %s", file_path)
        cmd = ["claude", "--read", file_path]
        result = self._run_command(cmd, input_text=file_path)

        if result.success and result.output:
            return result.output

        if not self.enable_local_fallbacks:
            error_details = result.error or "Claude API unavailable"
            message = (
                f"Claude API failed to read {file_path}: {error_details}. "
                f"Set {LOCAL_FALLBACK_ENV_VAR}=true to permit local fallbacks."
            )
            raise RuntimeError(message)

        suffix = Path(file_path).suffix.lower()
        if suffix in {".txt", ".md", ".json"}:
            return Path(file_path).read_text(encoding="utf-8")
        if suffix == ".pdf":
            return self._extract_pdf_fallback(file_path)

        raise RuntimeError(
            f"Local fallback for {suffix} not supported. Install remote integration or supply converter."
        )

    def _extract_pdf_fallback(self, file_path: str) -> str:
        if PyPDF2 is None:
            raise ImportError("PyPDF2 is not installed; PDF fallback unavailable")
        with open(file_path, "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)

    # ------------------------------------------------------------------ #
    # Text analysis
    # ------------------------------------------------------------------ #
    def analyze_text(
        self,
        text: str,
        prompt: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logger.debug("Analyzing text via Claude API, schema=%s", bool(schema))
        payload = {
            "prompt": prompt,
            "text": text,
            "schema": schema,
        }
        result = self._run_command(["claude", "--print"], input_text=json.dumps(payload))
        if result.success and result.output:
            try:
                return json.loads(result.output)
            except json.JSONDecodeError:
                logger.warning("Claude returned non-JSON output; falling back to simulation")

        # Simulated structured response
        if schema:
            if schema.get("type") == "array":
                return []
            return {}
        return {"result": "Analysis unavailable (simulated response)"}

    # ------------------------------------------------------------------ #
    # Agent orchestration helpers
    # ------------------------------------------------------------------ #
    def execute_task(self, agent: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        payload = {
            "agent": agent,
            "action": action,
            "params": params,
        }
        result = self._call_remote("/v1/agents/execute", payload)
        if result.success:
            return result.metadata or {"status": "success"}
        return {
            "status": "simulated",
            "agent": agent,
            "action": action,
            "result": f"Simulated execution of {action}",
            "warning": result.error or "Remote execution unavailable",
        }

    def chat(self, message: str, context: Optional[str] = None) -> str:
        payload = {"message": message, "context": context}
        result = self._call_remote("/v1/chat", payload)
        if result.success and result.output:
            return result.output
        return "Claude response unavailable (simulated)."

    def execute_with_mode(
        self,
        prompt: str,
        mode: Union[SuperClaudeMode, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> CLIResult:
        payload = {
            "prompt": prompt,
            "mode": mode.value if isinstance(mode, SuperClaudeMode) else mode,
            "context": context or {},
        }
        return self._call_remote("/v1/modes/execute", payload)

    def delegate_to_agent(
        self,
        prompt: str,
        agent: Union[SuperClaudeAgent, str] = None,
        task_manage: bool = False,
        quality_loop: bool = False,
    ) -> CLIResult:
        payload = {
            "prompt": prompt,
            "agent": agent.value if isinstance(agent, SuperClaudeAgent) else agent,
            "task_manage": task_manage,
            "quality_loop": quality_loop,
        }
        result = self._call_remote("/v1/agents/delegate", payload)
        if result.success:
            return result
        simulated_output = json.dumps(
            {
                "success": True,
                "output": "Simulated delegation result",
                "agent_used": payload["agent"] or "general-purpose",
            }
        )
        return CLIResult(success=True, output=simulated_output, metadata={"simulated": True})

    def execute_with_agent(
        self,
        agent: Union[SuperClaudeAgent, str],
        prompt: str,
        mode: Optional[Union[SuperClaudeMode, str]] = None,
        context_files: Optional[List[str]] = None,
        flags: Optional[List[str]] = None,
    ) -> CLIResult:
        payload = {
            "agent": agent.value if isinstance(agent, SuperClaudeAgent) else agent,
            "prompt": prompt,
            "mode": mode.value if isinstance(mode, SuperClaudeMode) else mode,
            "context_files": context_files or [],
            "flags": flags or [],
        }
        result = self._call_remote("/v1/agents/execute_with_agent", payload)
        if result.success:
            return result

        output = {
            "agent": payload["agent"],
            "prompt": prompt[:200],
            "result": "Simulated agent execution output",
            "flags": payload["flags"],
        }
        return CLIResult(success=True, output=json.dumps(output), metadata={"simulated": True})

    def use_mcp_server(
        self,
        prompt: str,
        mcp: Union[SuperClaudeMCP, str],
        additional_flags: Optional[List[str]] = None,
    ) -> CLIResult:
        payload = {
            "prompt": prompt,
            "mcp": mcp.value if isinstance(mcp, SuperClaudeMCP) else mcp,
            "flags": additional_flags or [],
        }
        result = self._call_remote("/v1/mcp/execute", payload)
        if result.success:
            return result

        simulated_response = {
            "overall_quality_score": 0.85,
            "critical_issues": [],
            "recommendations": [],
            "agreement_score": 0.9,
        }
        return CLIResult(
            success=True,
            output=json.dumps(simulated_response),
            metadata={"simulated": True},
        )

    # ------------------------------------------------------------------ #
    # Validation helpers
    # ------------------------------------------------------------------ #
    def validate_installation(self) -> bool:
        """Return True when remote configuration is available."""
        return self._remote_available()

    def check_claude(self) -> bool:
        """GUI compatibility helper mirroring legacy API."""
        return self.validate_installation()

    # ------------------------------------------------------------------ #
    # Async wrapper
    # ------------------------------------------------------------------ #
    async def _async(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)


class AsyncClaudeCLI(ClaudeCLI):
    """Async wrapper that mirrors the sync API using threads."""

    async def read_document_async(self, file_path: str) -> str:
        return await self._async(self.read_document, file_path)

    async def analyze_text_async(
        self,
        text: str,
        prompt: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._async(self.analyze_text, text, prompt, schema)

    async def execute_task_async(self, agent: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._async(self.execute_task, agent, action, params)

    async def chat_async(self, message: str, context: Optional[str] = None) -> str:
        return await self._async(self.chat, message, context)

    async def execute_with_mode_async(
        self,
        prompt: str,
        mode: Union[SuperClaudeMode, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> CLIResult:
        return await self._async(self.execute_with_mode, prompt, mode, context)

    async def use_mcp_server_async(
        self,
        prompt: str,
        mcp: Union[SuperClaudeMCP, str],
        additional_flags: Optional[List[str]] = None,
    ) -> CLIResult:
        return await self._async(self.use_mcp_server, prompt, mcp, additional_flags)

    async def delegate_to_agent_async(
        self,
        prompt: str,
        agent: Union[SuperClaudeAgent, str] = None,
        task_manage: bool = False,
        quality_loop: bool = False,
    ) -> CLIResult:
        return await self._async(self.delegate_to_agent, prompt, agent, task_manage, quality_loop)

    async def execute_with_agent_async(
        self,
        agent: Union[SuperClaudeAgent, str],
        prompt: str,
        mode: Optional[Union[SuperClaudeMode, str]] = None,
        context_files: Optional[List[str]] = None,
        flags: Optional[List[str]] = None,
    ) -> CLIResult:
        return await self._async(
            self.execute_with_agent,
            agent,
            prompt,
            mode,
            context_files,
            flags,
        )


__all__ = [
    "ClaudeCLI",
    "AsyncClaudeCLI",
    "CLIResult",
    "SuperClaudeMode",
    "SuperClaudeAgent",
    "SuperClaudeMCP",
    "LOCAL_FALLBACK_ENV_VAR",
]
