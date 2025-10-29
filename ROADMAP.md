# DocAutomate Roadmap

_Last updated: October 29, 2025_

## 2025 Q4 (Alignment Phase)
- Expand executable workflows from 3 → 6 with highest-value ingestion flows.
- Ship multi-model consensus for priority workflows (GPT-5 + Claude Opus).
- Introduce API-key authentication and environment-based configuration.
- Deliver Docker Compose stack (API + SQLite) and deployment guide.

## 2026 H1 (Post-MVP Enhancements)
- Spreadsheet ingestion adapters (`.xlsx`, `.csv`) with schema normalization.
- Email submission listener (IMAP/O365/Gmail) feeding the ingestion queue.
- Observability improvements (Prometheus metrics, OpenTelemetry traces).
- Role-based access control layered on top of API-key foundation.

## Stretch Goals / Community Contributions
- Invoice-specific automation (external ERP integrations).
- E-signature flows (DocuSign/Adobe Sign connectors).
- Advanced Excel automation (pivot tables, macros) via plugin architecture.
- Domain-specific legal/compliance workflows authored by SMEs.

## Guiding Principles
- **Delegation-first**: Keep business logic in Claude agents; orchestration stays lightweight.
- **Transparency**: Surface delegation metadata and quality metrics for every run.
- **Config over code**: Prefer DSL/prompt changes to feature toggles.
- **Secure by default**: Ship authentication and audit trails before expanding scope.
