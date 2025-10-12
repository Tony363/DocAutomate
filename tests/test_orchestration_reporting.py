#!/usr/bin/env python3
"""Integration tests for orchestration reporting."""

import asyncio
import time
import types
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.background import BackgroundTasks

from api import app, document_ingester, claude_service, orchestration_status
from ingester import Document
from services.claude_service import AnalysisResult, ConsensusResult, RemediationResult


def _create_document(text: str = "Sample content") -> str:
    doc_id = document_ingester.generate_document_id(text)
    doc = Document(
        id=doc_id,
        filename="test.txt",
        content_type="text/plain",
        text=text,
        metadata={},
        ingested_at=datetime.now(timezone.utc).isoformat(),
        status="processed",
        extracted_actions=[],
        workflow_runs=[]
    )
    asyncio.run(document_ingester._store_document(doc))
    return doc_id


@pytest.fixture
def client():
    return TestClient(app)


def _patch_method(monkeypatch, name, func):
    monkeypatch.setattr(claude_service, name, types.MethodType(func, claude_service))


def test_orchestration_reporting_success(client, monkeypatch):
    doc_id = _create_document()

    async def fake_multi(self, document_content, document_metadata, agents=None, claude_config=None, parallel=True):
        return {
            "general-purpose": AnalysisResult(
                success=True,
                analysis={
                    "issues": [{"issue": "Missing authentication docs", "severity": "high"}],
                    "recommendations": [{"recommendation": "Add auth section"}]
                },
                agent_used="general-purpose",
                confidence=0.92,
                metadata={"document_id": document_metadata.get("document_id")},
                processing_time=0.2,
                claude_command="--delegate general-purpose"
            )
        }

    async def fake_consensus(self, analysis_results, document_id, models=None, consensus_config=None):
        return ConsensusResult(
            success=True,
            consensus={
                "overall_quality_score": 0.86,
                "critical_issues": [{"issue": "Missing authentication docs", "severity": "high"}],
                "recommendations": [{"recommendation": "Add auth section"}]
            },
            models_used=models or ["gpt-5"],
            agreement_score=0.92,
            metadata={"document_id": document_id},
            agreement_details=[{"model": "gpt-5", "success": True, "latency_seconds": 0.1}]
        )

    async def fake_remediation(self, document_content, issues, document_id):
        return RemediationResult(
            success=True,
            remediated_content="Improved content",
            issues_resolved=[issue.get("issue", "issue") for issue in issues],
            quality_score=0.91,
            metadata={"document_id": document_id}
        )

    async def fake_validation(self, original_content, remediated_content, document_id):
        return {
            "success": True,
            "quality_score": 0.94,
            "improvements": ["Added authentication documentation"],
            "remaining_issues": []
        }

    _patch_method(monkeypatch, "multi_agent_analysis", fake_multi)
    _patch_method(monkeypatch, "consensus_validation", fake_consensus)
    _patch_method(monkeypatch, "generate_remediation", fake_remediation)
    _patch_method(monkeypatch, "quality_validation", fake_validation)

    def immediate_add_task(self, func, *args, **kwargs):
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            asyncio.run(result)

    monkeypatch.setattr(BackgroundTasks, "add_task", immediate_add_task, raising=True)

    response = client.post(
        "/orchestrate/workflow",
        json={"document_id": doc_id, "workflow_type": "full", "config": {}}
    )
    assert response.status_code == 200
    orchestration_id = response.json()["orchestration_id"]

    status_payload = client.get(f"/orchestrate/runs/{orchestration_id}").json()
    assert status_payload["status"] == "completed"

    results = status_payload["results"]
    workflow_tree = results["claude_workflow"]
    assert workflow_tree["analysis"]["status"] == "completed"
    assert workflow_tree["consensus"]["status"] == "completed"
    assert workflow_tree["remediation"]["status"] == "completed"
    assert workflow_tree["validation"]["status"] == "completed"
    assert results["status"] == "completed"
    assert results["quality_metrics"]["final_quality_score"] == 0.94
    assert "duration_seconds" in results


def test_orchestration_reporting_failure(client, monkeypatch):
    doc_id = _create_document()

    async def fake_multi(self, document_content, document_metadata, agents=None, claude_config=None, parallel=True):
        return {
            "general-purpose": AnalysisResult(
                success=True,
                analysis={"issues": [], "recommendations": []},
                agent_used="general-purpose",
                confidence=0.9,
                metadata={"document_id": document_metadata.get("document_id")},
                processing_time=0.1,
                claude_command="--delegate general-purpose"
            )
        }

    async def failing_consensus(self, *args, **kwargs):
        raise RuntimeError("Consensus service unavailable")

    _patch_method(monkeypatch, "multi_agent_analysis", fake_multi)
    _patch_method(monkeypatch, "consensus_validation", failing_consensus)

    def immediate_add_task(self, func, *args, **kwargs):
        result = func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            asyncio.run(result)

    monkeypatch.setattr(BackgroundTasks, "add_task", immediate_add_task, raising=True)

    response = client.post(
        "/orchestrate/workflow",
        json={"document_id": doc_id, "workflow_type": "full", "config": {}}
    )
    assert response.status_code == 200
    orchestration_id = response.json()["orchestration_id"]

    status_payload = client.get(f"/orchestrate/runs/{orchestration_id}").json()
    assert status_payload["status"] == "failed"

    results = status_payload["results"]
    workflow_tree = results["claude_workflow"]
    assert workflow_tree["analysis"]["status"] == "completed"
    assert workflow_tree["consensus"]["status"] == "failed"
    assert workflow_tree["remediation"]["status"] == "skipped"
    assert workflow_tree["validation"]["status"] == "skipped"
    assert results["status"] == "failed"
    assert "Consensus service unavailable" in results.get("error", "")
