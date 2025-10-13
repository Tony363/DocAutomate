#!/usr/bin/env python3
"""Contract-level tests for API payloads."""

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from extractor import ActionType, ConfidenceLevel, ExtractedAction
from ingester import Document
from utils.file_operations import FileOperations


def _load_fixture(name: str) -> dict:
    fixture_path = Path("tests/samples") / name
    with open(fixture_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def api_module(monkeypatch):
    class DummyAsyncCLI:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def read_document_async(self, path):
            del path
            return "Synthetic document content " * 5

    monkeypatch.setattr("services.claude_service.AsyncClaudeCLI", DummyAsyncCLI)
    import sys
    sys.modules.pop("api", None)
    return importlib.import_module("api")


@pytest.mark.asyncio
async def test_claude_analysis_payload_shape(monkeypatch, api_module):
    """Ensure stored document metadata matches README analysis structure."""
    contract = _load_fixture("document_status_contract.json")

    document = Document(
        id="doc_contract_test",
        filename="sample.pdf",
        content_type="application/pdf",
        text="Comprehensive document content. " * 20,
        metadata={"claude_agent": "technical-writer"},
        ingested_at=datetime.now(timezone.utc).isoformat(),
        status="pending",
        extracted_actions=[],
        workflow_runs=[],
    )

    stored_documents: List[Document] = []

    async def fake_store(doc: Document):
        stored_documents.append(doc)

    async def fake_extract_actions(text: str, document_type: str = None):
        del text, document_type
        return [
            ExtractedAction(
                action_id="act_001",
                action_type=ActionType.DOCUMENT_REVIEW,
                workflow_name="document_review",
                description="Section 3.2 needs clarification",
                parameters={"section": "3.2", "lines": [45, 60]},
                entities=[],
                confidence_score=0.92,
                confidence_level=ConfidenceLevel.HIGH,
                priority=2,
                deadline=None,
            )
        ]

    monkeypatch.setattr(api_module.document_ingester, "_store_document", fake_store)
    monkeypatch.setattr(api_module.action_extractor, "extract_actions", fake_extract_actions)

    result = await api_module._extract_actions_for_document(
        document=document,
        request_id="req-test",
        run_workflows=False
    )
    assert result["status"] == "processed"

    assert stored_documents, "Document should be persisted via ingester"
    stored_doc = stored_documents[-1]
    analysis = stored_doc.metadata.get("claude_analysis")

    for key in contract["required_root_keys"]:
        if key == "claude_analysis":
            assert analysis is not None
            continue
        assert getattr(stored_doc, key, None) is not None

    for key in contract["required_analysis_keys"]:
        assert key in analysis, f"Missing analysis key: {key}"

    issues = analysis.get("issues_found") or []
    assert isinstance(issues, list)
    assert issues, "Expected at least one issue in analysis payload"
    for issue in issues:
        for key in contract["issue_required_keys"]:
            assert key in issue and issue[key] is not None

    assert analysis["quality_score"] == pytest.approx(0.92, abs=0.01)
    assert stored_doc.quality_score == analysis["quality_score"]
    assert analysis["primary_agent"] == "technical-writer"
    recommendations = analysis.get("recommendations") or []
    assert "Section 3.2 needs clarification" in recommendations


@pytest.mark.asyncio
async def test_conversion_response_includes_results_and_processing(monkeypatch, tmp_path, api_module):
    """Synchronous conversion should expose results list and processing time."""
    contract = _load_fixture("conversion_response_contract.json")

    input_path = tmp_path / "input.docx"
    output_path = tmp_path / "output.pdf"
    input_path.write_bytes(b"dummy docx content")

    async def fake_convert(input_path_arg, output_path_arg, quality, preserve_formatting, use_claude):
        del output_path_arg, quality, preserve_formatting, use_claude
        return {
            "success": True,
            "method": "docx2pdf_library",
            "input_path": input_path_arg,
            "output_path": str(output_path),
            "duration_seconds": 0.42,
            "quality": "high",
            "output_size_bytes": 2048,
        }

    monkeypatch.setattr(FileOperations, "convert_docx_to_pdf", staticmethod(fake_convert))

    request_body = api_module.DocumentConversionRequest(
        input_path=str(input_path),
        output_path=str(output_path),
        use_dsl=False,
        preserve_formatting=True,
        quality="high",
    )

    class DummyRequest:
        def __init__(self):
            self.headers = {"content-type": "application/json"}

        async def json(self):
            return {}

        async def body(self):
            return b""

        async def form(self):
            return {}

    response = await api_module.convert_docx_to_pdf(
        raw_request=DummyRequest(),
        request=request_body,
        file=None,
    )
    response_payload = response.model_dump()

    for key in contract["required_keys"]:
        assert key in response_payload
        assert response_payload[key] is not None

    results = response_payload["results"]
    assert isinstance(results, list) and results, "Results list should contain at least one entry"
    for key in contract["results_required_keys"]:
        assert key in results[0]

    assert results[0]["status"] == "success"
    assert results[0]["output_path"] == str(output_path)
    assert response_payload["processing_time_seconds"] >= 0.0
