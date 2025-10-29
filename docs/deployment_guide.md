# Deployment Guide

1. Copy `.env.example` to `.env` and set the following values:
   ```env
   DOC_AUTOMATE_API_KEY=<your-api-key>
   CLAUDE_API_BASE=<optional-claude-endpoint>
   CLAUDE_API_KEY=<anthropic-api-key>
   DATABASE_URL=sqlite:///./state/docautomate.db
   CLAUDE_ENABLE_LOCAL_FALLBACKS=false
   ```

2. Build and run with Docker Compose:
   ```bash
   docker compose up --build
   ```

3. Access the API docs at `http://localhost:8000/docs` and include the header `X-API-Key`.

4. To run the accuracy benchmark:
   ```bash
   python scripts/accuracy_benchmark.py --dataset datasets/benchmark.json
   ```

Screenshots and recorded demos will be added after the expanded workflows are finalized.
