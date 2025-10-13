#!/usr/bin/env python3
"""
Regression tests for Claude CLI fallback behaviour.
Ensures local processing only occurs when explicitly enabled.
"""

from pathlib import Path
from typing import Dict, Any

import pytest

from claude_cli import (
    ClaudeCLI,
    CLIResult,
    LOCAL_FALLBACK_ENV_VAR,
    AsyncClaudeCLI,
)
from ingester import DocumentIngester


def test_pdf_fallback_disabled_by_default(monkeypatch, tmp_path):
    """ClaudeCLI should surface errors when fallbacks are disabled."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DocAutomate test\n")
    
    monkeypatch.delenv(LOCAL_FALLBACK_ENV_VAR, raising=False)
    
    cli = ClaudeCLI(enable_local_fallbacks=False)
    
    def fake_run_command(
        self,
        cmd,
        input_text=None,
        use_pty=False
    ) -> CLIResult:
        return CLIResult(
            success=False,
            output="",
            error="Mock CLI failure",
            exit_code=1,
        )
    
    monkeypatch.setattr(ClaudeCLI, "_run_command", fake_run_command)
    
    with pytest.raises(RuntimeError) as exc:
        cli.read_document(str(pdf_path))
    
    message = str(exc.value)
    assert LOCAL_FALLBACK_ENV_VAR in message
    assert "Mock CLI failure" in message


def test_pdf_fallback_opt_in(monkeypatch, tmp_path):
    """ClaudeCLI should use PyPDF2 fallback when explicitly enabled."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DocAutomate test\n")
    
    monkeypatch.setenv(LOCAL_FALLBACK_ENV_VAR, "true")
    
    cli = ClaudeCLI()
    
    def fake_run_command(
        self,
        cmd,
        input_text=None,
        use_pty=False
    ) -> CLIResult:
        return CLIResult(
            success=False,
            output="",
            error="Mock CLI failure",
            exit_code=1,
        )
    
    monkeypatch.setattr(ClaudeCLI, "_run_command", fake_run_command)
    
    fallback_called: Dict[str, Any] = {"value": False}
    
    def fake_extract_pdf(self, file_path: str) -> str:
        fallback_called["value"] = True
        return "fallback text"
    
    monkeypatch.setattr(ClaudeCLI, "_extract_pdf_fallback", fake_extract_pdf)
    
    result = cli.read_document(str(pdf_path))
    
    assert fallback_called["value"] is True
    assert result == "fallback text"


@pytest.mark.asyncio
async def test_ingester_raises_when_fallback_disabled(monkeypatch, tmp_path):
    """DocumentIngester should raise when CLI unavailable and fallback disabled."""
    monkeypatch.delenv(LOCAL_FALLBACK_ENV_VAR, raising=False)
    
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% DocAutomate test\n")
    
    async def fake_read_document(self, file_path: str) -> str:
        raise FileNotFoundError("Claude CLI unavailable")
    
    monkeypatch.setattr(
        AsyncClaudeCLI,
        "read_document_async",
        fake_read_document,
        raising=False,
    )
    
    ingester = DocumentIngester(storage_dir=str(tmp_path / "storage"))
    
    with pytest.raises(RuntimeError) as exc:
        await ingester.ingest_file(str(pdf_path))
    
    message = str(exc.value)
    assert LOCAL_FALLBACK_ENV_VAR in message
    
    ingester.executor.shutdown(wait=False)
