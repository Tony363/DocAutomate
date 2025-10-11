# Repository Guidelines

## Project Structure & Module Organization
Core orchestration modules live at the repository root: `api.py` exposes the FastAPI surface, while `ingester.py`, `extractor.py`, `workflow.py`, and `workflow_matcher.py` manage document routing and agent-driven workflows. Shared utilities sit under `utils/`, Claude-specific helpers in `services/`, and reusable DSL assets in `dsl/`, `templates/`, and `workflows/`. GUI, CLI, and automation entry points are gathered in `scripts/`. Tests mirror the runtime layout inside `tests/`, with sample fixtures stored in `tests/samples/` and `samples/` for quick experimentation.

## Build, Test, and Development Commands
Install dependencies with `python -m pip install -r requirements.txt` (Python 3.11+). Run the API locally via `uvicorn api:app --reload` to exercise endpoints. Use `python scripts/orchestrate_client.py` for scripted orchestration runs or `python scripts/document-ingestion.py` to test ingestion workflows. Validate the suite with `pytest tests/ -v --cov=docautomate`, and lint before submitting changes using `black .` followed by `flake8`.

## Coding Style & Naming Conventions
Adopt Black’s default formatting (120-character line budget and 4-space indentation). Keep imports sorted per Black, favor type hints for new functions, and document public call paths with concise docstrings. Module names stay lowercase with underscores (`file_operations.py`), classes use CapWords (e.g., `WorkflowEngine`), and async helpers should end with `_async` when appropriate. External configuration or agent templates should retain their existing YAML naming patterns.

## Testing Guidelines
All new behavior needs targeted `pytest` coverage; async flows should leverage `pytest.mark.asyncio`. Mirror the module under test with filenames like `test_workflow_integration.py` and name test functions descriptively (`test_validates_uploaded_document`). Aim to maintain or raise the existing coverage reported by `--cov=docautomate`, and isolate slow or network-dependent cases behind marks so they can be skipped when running the default suite.

## Commit & Pull Request Guidelines
Follow the repository’s concise, present-tense commit style (`cleanup`, `add workflow trigger`). Group related edits together and include issue or ticket references in the body when applicable. Pull requests should summarize intent, call out affected workflows or templates, list any new scripts or configuration files, and attach screenshots or sample output when UI or CLI behavior changes. Ensure automated lint and test commands pass before requesting review.

## Security & Configuration Notes
Never hard-code provider credentials or API tokens; rely on environment variables read at runtime by the CLI and API layers. Review `.gitignore` before adding new files to avoid leaking workflow artifacts, and scrub documents placed in `samples/` or `tests/samples/` of sensitive data. When updating DSL or template files, flag any new external service dependencies in the PR description so reviewers can verify compliance impacts.
