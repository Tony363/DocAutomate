from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils.metrics import collect_health_metrics
from workflow import WorkflowStatus


class StubIngester:
    def __init__(self, documents):
        self._documents = documents

    def list_documents(self):
        return self._documents


class StubWorkflowEngine:
    def __init__(self, runs):
        self._runs = runs

    def list_runs(self):
        return self._runs


class StubClaudeService:
    def __init__(self, dsl_config, agent_mappings, timeout=300):
        self.dsl_config = dsl_config
        self.agent_mappings = agent_mappings
        self.cli = SimpleNamespace(timeout=timeout)


class StubWorkflowRun:
    def __init__(self, status, duration=None):
        self.status = status
        self.total_duration_seconds = duration


def make_document(status):
    return SimpleNamespace(status=status)


@pytest.mark.parametrize("default_model_env", [None, "env-model"])
def test_collect_health_metrics_captures_expected_keys(monkeypatch, default_model_env):
    if default_model_env is None:
        monkeypatch.delenv("CLAUDE_DEFAULT_MODEL", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_DEFAULT_MODEL", default_model_env)

    monkeypatch.delenv("CLAUDE_PARALLEL_PROCESSING", raising=False)

    documents = [
        make_document("processed"),
        make_document("pending"),
        make_document("failed"),
    ]
    runs = [
        StubWorkflowRun(WorkflowStatus.SUCCESS, duration=12.0),
        StubWorkflowRun(WorkflowStatus.FAILED, duration=18.0),
        StubWorkflowRun(WorkflowStatus.RUNNING, duration=None),
    ]

    ingester = StubIngester(documents)
    workflow_engine = StubWorkflowEngine(runs)

    dsl_config = {
        "operation_types": {
            "analysis": {
                "models": ["model-b", "model-a"],
                "parallel": True,
            }
        }
    }
    agent_mappings = {
        "document_type_mappings": {
            "report": {
                "consensus_required": True
            }
        }
    }
    claude_service = StubClaudeService(dsl_config, agent_mappings, timeout=240)

    start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    now = start_time + timedelta(hours=2, minutes=30)

    metrics = collect_health_metrics(
        ingester,
        workflow_engine,
        claude_service,
        start_time=start_time,
        now=now,
    )

    assert metrics["document_counts"]["total"] == 3
    assert metrics["document_counts"]["processed"] == 1
    assert metrics["document_counts"]["pending"] == 1
    assert metrics["document_counts"]["failed"] == 1
    assert metrics["document_counts"]["by_status"]["processed"] == 1

    assert metrics["workflow_metrics"]["total_runs"] == 3
    assert metrics["workflow_metrics"]["successful_runs"] == 1
    assert metrics["workflow_metrics"]["failed_runs"] == 1
    assert metrics["workflow_metrics"]["running"] == 1
    assert metrics["workflow_metrics"]["success_rate"] == pytest.approx(1 / 3, rel=1e-4)
    assert metrics["workflow_metrics"]["average_duration_seconds"] == pytest.approx(15.0)

    assert metrics["system_metrics"]["documents_total"] == 3
    assert metrics["system_metrics"]["documents_processed"] == 1
    assert metrics["system_metrics"]["documents_pending"] == 1
    assert metrics["system_metrics"]["workflow_runs_total"] == 3
    assert metrics["system_metrics"]["workflow_success_rate"] == pytest.approx(1 / 3, rel=1e-4)

    expected_models = ["model-a", "model-b"]
    assert metrics["claude_integration"]["models_available"] == expected_models
    if default_model_env is None:
        assert metrics["claude_integration"]["default_model"] == expected_models[0]
    else:
        assert metrics["claude_integration"]["default_model"] == default_model_env

    assert metrics["claude_integration"]["consensus_enabled"] is True
    assert metrics["claude_integration"]["parallel_processing"] is True

    assert metrics["uptime_seconds"] == 9000
    assert metrics["uptime"] == "2h 30m 0s"
