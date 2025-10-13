FROM python:3.11-slim

# System dependencies for building optional libraries and Tk (for GUI container)
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    tk \
    && rm -rf /var/lib/apt/lists/*

# Optional: install Claude CLI when API delegation unavailable
RUN curl -sSf https://claude.ai/install.sh | sh && \
    ln -sf /root/.local/bin/claude /usr/local/bin/claude

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p storage logs state workflows docs/generated dsl templates

ENV PYTHONPATH=/app \
    API_PORT=8000 \
    CLAUDE_TIMEOUT=600 \
    CLAUDE_AUDIT_LOG=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
