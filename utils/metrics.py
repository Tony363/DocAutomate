"""
Utility helpers for aggregating runtime metrics exposed via the API.

The collect_* functions avoid heavy dependencies so they can run safely in
health checks and background tasks without blocking the main event loop.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os
from typing import Any, Dict, Iterable, Optional, Sequence


APPLICATION_START_TIME = datetime.now(timezone.utc)


def format_duration(seconds: Optional[float]) -> Optional[str]:
    """Convert raw seconds into a compact human-readable string."""
    if seconds is None:
        return None
    try:
        total_seconds = int(round(float(seconds)))
    except (TypeError, ValueError):
        return None

    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def get_application_uptime(
    start_time: datetime = APPLICATION_START_TIME,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return uptime information in seconds and formatted string."""
    current = now or datetime.now(timezone.utc)
    if current < start_time:
        current = start_time
    uptime_seconds = int((current - start_time).total_seconds())
    return {
        "uptime_seconds": uptime_seconds,
        "uptime": format_duration(uptime_seconds),
    }


def summarize_document_counts(documents: Sequence[Any]) -> Dict[str, Any]:
    """Aggregate document counts by status."""
    statuses = [
        (getattr(doc, "status", None) or "unknown").lower()
        for doc in documents
    ]
    status_counts = Counter(statuses)

    processed_statuses = {"processed", "processed_no_actions", "success", "completed"}
    failed_statuses = {"failed", "error", "extraction_failed"}
    pending_statuses = {"pending", "queued"}

    processed = sum(status_counts.get(status, 0) for status in processed_statuses)
    failed = sum(status_counts.get(status, 0) for status in failed_statuses)
    pending = sum(status_counts.get(status, 0) for status in pending_statuses)

    return {
        "total": len(documents),
        "pending": pending,
        "processed": processed,
        "failed": failed,
        "by_status": dict(status_counts),
    }


def summarize_workflow_runs(runs: Sequence[Any]) -> Dict[str, Any]:
    """Produce aggregate statistics for workflow executions."""
    total_runs = len(runs)
    if total_runs == 0:
        return {
            "total_runs": 0,
            "running": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "success_rate": None,
            "average_duration_seconds": None,
            "average_duration_formatted": None,
        }

    def _status_equals(run: Any, expected: str) -> bool:
        value = getattr(run, "status", None)
        if value is None:
            return False
        status_str = value.value if hasattr(value, "value") else str(value)
        return status_str.lower() == expected

    successful = sum(1 for run in runs if _status_equals(run, "success"))
    failed = sum(1 for run in runs if _status_equals(run, "failed"))
    running = sum(1 for run in runs if _status_equals(run, "running"))

    durations = [
        float(getattr(run, "total_duration_seconds", 0))
        for run in runs
        if getattr(run, "total_duration_seconds", None) not in (None, "")
    ]
    average_duration = (
        sum(durations) / len(durations)
        if durations
        else None
    )

    success_rate = successful / total_runs if total_runs else None

    return {
        "total_runs": total_runs,
        "running": running,
        "successful_runs": successful,
        "failed_runs": failed,
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "average_duration_seconds": average_duration,
        "average_duration_formatted": format_duration(average_duration),
    }


def _collect_values_for_key(data: Any, key: str) -> Iterable[Any]:
    """Recursively yield values for the given key within nested structures."""
    if isinstance(data, dict):
        for item_key, item_value in data.items():
            if item_key == key:
                yield item_value
            else:
                yield from _collect_values_for_key(item_value, key)
    elif isinstance(data, (list, tuple, set)):
        for item in data:
            yield from _collect_values_for_key(item, key)


def _collect_models(data: Any) -> Sequence[str]:
    """Gather distinct model identifiers from nested configuration data."""
    models = set()
    for value in _collect_values_for_key(data, "models"):
        if isinstance(value, (list, tuple, set)):
            models.update(str(item) for item in value if item)
        else:
            models.add(str(value))
    return sorted(models)


def collect_claude_integration_summary(claude_service: Any) -> Dict[str, Any]:
    """Summarize the Claude integration state and defaults."""
    dsl_config = getattr(claude_service, "dsl_config", {}) or {}
    agent_mappings = getattr(claude_service, "agent_mappings", {}) or {}

    models = _collect_models(dsl_config) or _collect_models(agent_mappings)
    default_model = os.getenv("CLAUDE_DEFAULT_MODEL")
    if not default_model and models:
        default_model = models[0]

    consensus_enabled = any(
        bool(value)
        for value in _collect_values_for_key(dsl_config, "consensus_required")
    ) or any(
        bool(value)
        for value in _collect_values_for_key(agent_mappings, "consensus_required")
    )

    parallel_enabled = any(
        bool(value)
        for value in _collect_values_for_key(dsl_config, "parallel")
    ) or any(
        bool(value)
        for value in _collect_values_for_key(dsl_config, "parallel_agents")
    )

    if not parallel_enabled:
        env_parallel = os.getenv("CLAUDE_PARALLEL_PROCESSING")
        if env_parallel is not None:
            parallel_enabled = env_parallel.lower() not in {"0", "false", "no"}

    return {
        "models_available": models,
        "default_model": default_model,
        "consensus_enabled": bool(consensus_enabled),
        "parallel_processing": bool(parallel_enabled),
    }


def build_system_metrics(
    document_counts: Dict[str, Any],
    workflow_metrics: Dict[str, Any],
    uptime: Dict[str, Any],
) -> Dict[str, Any]:
    """Compose a flattened metrics payload for health consumers."""
    return {
        "uptime": uptime.get("uptime"),
        "uptime_seconds": uptime.get("uptime_seconds"),
        "documents_total": document_counts.get("total", 0),
        "documents_processed": document_counts.get("processed", 0),
        "documents_pending": document_counts.get("pending", 0),
        "documents_failed": document_counts.get("failed", 0),
        "workflow_runs_total": workflow_metrics.get("total_runs", 0),
        "workflow_success_rate": workflow_metrics.get("success_rate"),
        "average_workflow_duration_seconds": workflow_metrics.get("average_duration_seconds"),
        "average_workflow_duration": workflow_metrics.get("average_duration_formatted"),
        "average_processing_time": workflow_metrics.get("average_duration_formatted"),
    }


def collect_health_metrics(
    document_ingester: Any,
    workflow_engine: Any,
    claude_service: Any,
    start_time: datetime = APPLICATION_START_TIME,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Gather aggregated metrics used by the /health endpoint.

    Direct file-system access may fail (e.g. during first boot), so we handle
    exceptions gracefully and default to empty collections.
    """
    try:
        documents = document_ingester.list_documents()
    except Exception:
        documents = []

    try:
        runs = workflow_engine.list_runs()
    except Exception:
        runs = []

    document_counts = summarize_document_counts(documents)
    workflow_metrics = summarize_workflow_runs(runs)

    uptime = get_application_uptime(start_time=start_time, now=now)
    claude_integration = collect_claude_integration_summary(claude_service)
    system_metrics = build_system_metrics(document_counts, workflow_metrics, uptime)

    return {
        "document_counts": document_counts,
        "workflow_metrics": workflow_metrics,
        "claude_integration": claude_integration,
        "system_metrics": system_metrics,
        "uptime": uptime["uptime"],
        "uptime_seconds": uptime["uptime_seconds"],
    }
