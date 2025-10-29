# PDF Submission Example (Placeholder)

1. Upload broker PDF via `POST /documents/upload` with `X-API-Key` header.
2. Wait for background processing or call `POST /documents/{id}/extract`.
3. Run `scripts/accuracy_benchmark.py` with the labelled target to compute accuracy.

Artifacts will be populated once benchmark assets are anonymized.
