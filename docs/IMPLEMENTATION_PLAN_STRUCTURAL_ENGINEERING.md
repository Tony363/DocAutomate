# Implementation Plan

1. **Complete Agent Coverage**
   - Implement provider classes for every agent referenced in the DSL/README (system-architect, backend-architect, frontend-architect, requirements-analyst, refactoring-expert, etc.) using the `execute_with_agent_async` integration.
   - Register the new providers in `AgentRegistry` and add smoke tests that confirm routing selects the correct agent for each mapped document type.

2. **Enhance Analysis/Consensus Pipelines**
   - Extend `AnalysisRequest` and handlers to accept and forward `claude_config`, capturing runtime flags (e.g., `claude_command`) and timing metrics.
   - Rework `consensus_validation` to iterate across the supplied model list, aggregate findings, and persist an `agreement_details` block mirroring the README examples; add unit tests covering multi-model consensus scenarios.

3. **Workflow Telemetry & Metadata**
   - Capture per-step timings and outcomes inside `WorkflowRun` (augment `WorkflowEngine.execute_workflow`) and surface averages/SLA metadata when listing workflows.
   - Update `/workflows`, `/workflows/runs`, and `/workflows/runs/{id}` responses to match the documented JSON structures, including formatted durations and final summary sections.

4. **Orchestration Reporting**
   - Extend `claude_service.orchestrate_workflow` to build the detailed `claude_workflow` tree (analysis → consensus → remediation → validation) with quality metrics, then persist it so `/orchestrate/runs/{id}` returns the README-style payload.
   - Add integration tests covering both success and failure paths for orchestration reporting.

5. **Health & Metrics Alignment**
   - Collect and expose the additional health data (document counts, uptime, Claude model defaults, system metrics) so `/health` matches the published schema.
   - Introduce a lightweight metrics module with tests validating the presence and accuracy of required keys.

6. **Eliminate Local Fallbacks (or Update Docs)**
   - To honor the “pure delegation” promise, remove or gate the PyPDF2/docx2pdf fallbacks behind an opt-in flag, ensuring CLI failures surface to the caller rather than silently switching to local processing.
   - Add regression tests verifying that unsupported formats trigger explicit errors instead of local processing.

7. **API Contract Parity**
   - Ensure batch and conversion endpoints return the richer result lists (`results[]`, `processing_time`) when running synchronously, or update the README to describe queued behaviour accurately.
   - Reconcile document status storage so `claude_analysis`, issue lists, and quality scores align with the README examples; add fixtures to confirm the payload shape.

8. **Spreadsheet & Email Ingestion Pilot**
   - Implement adapters that ingest `.xlsx/.csv` submissions and broker emails, normalising field names into the canonical property schema.
   - Add confidence-calibrated flagging for the pilot cohort so low-confidence fields automatically queue for review.

9. **Accuracy Benchmark Harness**
   - Build a reproducible regression harness that replays curated submissions nightly, persists per-field metrics, and surfaces them on the operations dashboard.
