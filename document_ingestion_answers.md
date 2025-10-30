# Document Ingestion Notes

`document_ingestion.txt` does not currently include explicit questions. To keep progress transparent, this note captures the key DocAutomate document-ingestion capabilities you would leverage when prompts arrive.

## Core Pipeline Overview
- **DocumentIngester** (`ingester.py`) normalizes PDFs, DOCX, spreadsheets, images, and emails. It persists text extracts plus delegation metadata to SQLite so downstream workflows have consistent context.
- **Async Extraction**: Claude delegation is attempted first; when `CLAUDE_ENABLE_LOCAL_FALLBACKS=true`, PyPDF2 and docx2pdf fallbacks activate automatically with audit trails.
- **Job Queue & Executors**: ingestion enqueues jobs for background processing, letting the API respond quickly while workflows analyze documents in parallel.
- **Metadata Capture**: every record stores size, agent used, delegation status, and workflow run history—critical for compliance and debugging.

## Helpful Features to Tackle Future Questions
1. **Email Ingestion** – `email_ingester.py` splits message bodies and attachments, routing each through the same ingestion flow.
2. **Workflow Engine Hooks** – DSL workflows (for example, `multi_agent_analysis.yaml`) can auto-trigger after ingest to classify, remediate, or enrich documents.
3. **Conversion Utilities** – `utils.file_operations.FileOperations` exposes DOCX→PDF conversion and folder compression endpoints so unstructured submissions can be standardized prior to analysis.
4. **API Coverage** – FastAPI endpoints (`/documents/upload`, `/documents/{id}`, `/documents/convert/*`, `/emails/ingest`) expose ingestion features externally, with API-key gating and health checks.

Update this file once specific document-ingestion questions are provided so answers remain co-located with their prompts.
