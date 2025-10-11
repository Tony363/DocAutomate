#!/usr/bin/env python3
"""
Unit tests for enhanced analysis and consensus pipelines.
"""

import json
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def stub_service(monkeypatch):
    """Create a ClaudeService instance with stubbed CLI behaviour."""
    from claude_cli import CLIResult
    import importlib

    analyze_payload = {
        "findings": ["Summary insight"],
        "issues": [],
        "recommendations": ["Add examples"],
        "confidence": 0.9
    }

    def create_service(payloads):
        class StubCLI:
            def __init__(self):
                self._consensus_iter = iter(list(payloads))

            async def analyze_text_async(self, text, prompt, schema):
                return analyze_payload

            async def use_mcp_server_async(self, prompt, mcp, additional_flags):
                try:
                    payload = next(self._consensus_iter)
                except StopIteration:
                    payload = {}
                return CLIResult(success=True, output=json.dumps(payload))

        module = importlib.import_module("services.claude_service")
        monkeypatch.setattr(module, "AsyncClaudeCLI", lambda *args, **kwargs: StubCLI())
        from services.claude_service import ClaudeService
        return ClaudeService()

    return create_service


@pytest.mark.asyncio
async def test_multi_agent_analysis_records_metadata(stub_service):
    service = stub_service([])
    result = await service.multi_agent_analysis(
        document_content="Sample content",
        document_metadata={"document_id": "doc-1", "content_type": "text/plain"},
        agents=["general-purpose"],
        claude_config={"flags": ["--delegate"], "superclaude_modes": ["--parallel"]},
        parallel=True
    )

    analysis = result["general-purpose"]
    assert analysis.claude_command == "--delegate --parallel"
    assert analysis.processing_time is not None
    assert analysis.metadata is not None
    assert analysis.metadata["execution_mode"] == "parallel"


@pytest.mark.asyncio
async def test_consensus_validation_multi_model(stub_service):
    payload_model_one = {
        "overall_quality_score": 0.82,
        "critical_issues": [
            {"issue": "Missing authentication docs", "severity": "high"}
        ],
        "recommendations": [
            {"recommendation": "Add auth section", "priority": "high"}
        ],
        "agreement_score": 0.9
    }

    payload_model_two = {
        "overall_quality_score": 0.88,
        "critical_issues": [
            {"issue": "Missing authentication docs", "severity": "high"}
        ],
        "recommendations": [
            {"recommendation": "Add auth section", "priority": "high"},
            {"recommendation": "Provide error handling examples", "priority": "medium"}
        ],
        "agreement_score": 0.95
    }

    service = stub_service([payload_model_one, payload_model_two])

    from services.claude_service import AnalysisResult

    analysis_results = {
        "general-purpose": AnalysisResult(
            success=True,
            analysis={"issues": [{"issue": "Missing authentication docs"}], "recommendations": []},
            agent_used="general-purpose",
            confidence=0.9
        )
    }

    consensus = await service.consensus_validation(
        analysis_results=analysis_results,
        document_id="doc-123",
        models=["gpt-5", "claude-opus-4.1"],
        consensus_config={"agreement_threshold": 0.8}
    )

    assert consensus.success is True
    assert consensus.agreement_score >= 0.79
    assert len(consensus.agreement_details) == 2
    critical_issues = consensus.consensus.get("critical_issues", [])
    assert critical_issues
    assert critical_issues[0]["support"] == 1.0
    assert critical_issues[0]["agreed_by"] == ["gpt-5", "claude-opus-4.1"]
