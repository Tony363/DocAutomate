# Implementation Plan (Four-Week Alignment)

## Week 1 – Truth & Fallback Hygiene
- [x] Update README with “What Works Now” vs “Roadmap,” delegation metadata, and fallback flag documentation.
- [x] Add `ROADMAP.md` capturing future ambitions and assumptions.
- [x] Embed current architecture diagram (including Claude delegation plus optional local fallback path) in README/docs.
- [x] Ensure delegation metadata is surfaced across API responses and document the `CLAUDE_ENABLE_LOCAL_FALLBACKS` flag.

## Week 2 – Core Execution Gaps
- [x] Replace the Zen MCP consensus stub with working multi-model consensus for the three highest-impact workflows, including prompts and tests.
- [x] Expand executable workflows from 3 to 6 by fleshing out DSL steps for the most common ingestion scenarios.
- [x] Implement API-key authentication (FastAPI dependency/middleware) with sample `.env` configuration and tests.

## Week 3 – Production Foundations
- [x] Harden SQLite persistence (route all write paths through `storage/database.py`, document migrations/initialization).
- [x] Introduce environment-based configuration management for Claude credentials, persistence URLs, and fallback behaviour.
- [x] Provide a minimal Docker Compose stack (API + SQLite) for local/CI runs.
- [x] Add structured logging for delegation status, auth principal, and failure reasons.

## Week 4 – Polish & Examples
- [ ] Finalize API reference (OpenAPI descriptions, curl snippets, FastAPI docs reflecting delegation metadata).
- [ ] Create two end-to-end ingestion examples and store assets in `docs/examples/`.
- [x] Publish a concise deployment guide (local Compose + BYO Claude credentials) with screenshots or terminal captures.
