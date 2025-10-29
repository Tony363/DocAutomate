# DocAutomate Workflow Examples

This folder will store reproducible end-to-end examples once the 95% accuracy
benchmark is achieved. Planned examples:

1. **PDF Submission** – earthquake property submission with extraction metrics (see `pdf_submission.md`).
2. **Spreadsheet Supplement** – broker workbook normalized to canonical fields (see `spreadsheet_submission.md`).

Each example will include:
- Source artifacts (anonymized)
- Expected extraction results (JSON)
- Accuracy benchmark output (generated via `scripts/accuracy_benchmark.py`)

Interim placeholders reference sample assets in `samples/` and accuracy datasets in `datasets/benchmark.json`.
