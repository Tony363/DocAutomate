# Spreadsheet Submission Example (Placeholder)

Steps (to be expanded with real data):

1. Upload `samples/sample_submission.csv` using `POST /documents/upload`.
   ```bash
   curl -X POST \"http://localhost:8000/documents/upload\" \\\n     -H \"X-API-Key: $DOC_AUTOMATE_API_KEY\" \\\n     -F \"file=@samples/sample_submission.csv\" \\\n     -F \"auto_process=true\"\n+   ```\n+2. Verify `delegation_status` becomes `preprocessed` and `document_type` is `spreadsheet` via `GET /documents/{id}`.\n+3. Review extracted actions, validate consensus output, and capture metrics with `scripts/accuracy_benchmark.py`.\n+4. Document accuracy and manual review notes here after anonymizing production samples.\n*** End Patch
