# Delegation Alignment Plan

Workstreams track the effort required to make the codebase match the README promises. Milestones use GitHub-style checkboxes so we can mark them complete as we land changes.

## Workstream A – Restore “Pure Delegation”
- [x] **A1. Audit & gate local fallbacks** – ensure every ingestion/conversion fallback requires an explicit opt-in flag and surfaces clear errors by default.
- [x] **A2. Surface delegation status** – propagate success/failure of Claude delegation to API responses and logs instead of silently masking issues.
- [ ] **A3. Update operator docs** – document the delegation behavior and fallback flag usage in README and operational standards.

## Workstream B – Broaden Document Support
- [ ] **B1. Spreadsheet ingestion** – add adapters that normalize `.xlsx/.csv` submissions into the canonical property schema with tests covering broker samples.
- [ ] **B2. Email ingestion** – support broker submission emails (body + attachments) via an ingestion listener feeding the existing queue.
- [ ] **B3. Workflow routing upgrades** – tag new document types (“email_submission”, “broker_sheet”), extend prompts, and route through specialized workflows.
- [ ] **B4. README alignment** – update documentation to list supported formats and caveats once adapters ship.

## Workstream C – Operational Quality & Evaluation
- [ ] **C1. Accuracy harness** – nightly regression runner that replays labelled submissions and records per-field metrics.
- [ ] **C2. Confidence calibration & flagging** – wire per-field confidence thresholds to workflow quality gates and manual review queues.
- [ ] **C3. Telemetry & dashboards** – capture step timings/consensus scores and expose rolling accuracy dashboards.
- [ ] **C4. Documentation parity** – refresh README and supporting docs with real metrics, monitoring endpoints, and alerting behavior.
