# PDF Submission Example (Placeholder)

1. Upload the sample submission via `POST /documents/upload` with `X-API-Key` header.
   ```bash
   curl -X POST "http://localhost:8000/documents/upload" \
     -H "X-API-Key: $DOC_AUTOMATE_API_KEY" \
     -F "file=@samples/sample_invoice.txt" \
     -F "auto_process=true"
   ```
2. Monitor `GET /documents/{id}` until the document leaves `pending` or `manual_review`.
3. Run `scripts/accuracy_benchmark.py --dataset datasets/benchmark.json` to capture accuracy metrics.
4. Record the resulting accuracy, delegation status, and manual-review flags in this folder once real samples are anonymized.
