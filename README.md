# DocAutomate Framework

Enterprise-ready document ingestion and action automation framework with **full Claude Code integration** via command-line interface.

## Features

- **Claude Code Integration**: Real document processing using Claude Code CLI
- **Multi-format Document Ingestion**: PDF, images, text via Claude Read tool
- **Intelligent Action Extraction**: Claude's NLP for actionable item identification
- **Task Agent Execution**: Direct integration with Claude Task agents
- **YAML-based Workflows**: Define complex automation workflows declaratively
- **REST API**: Full-featured API for integration
- **Pydantic Validation**: Structured, validated action extraction
- **Async Processing**: Concurrent document processing with job queue
- **State Management**: Track workflow execution status
- **Extensible Action Registry**: Easy to add new action types

## Claude Code Integration

DocAutomate now features **full integration with Claude Code** via command-line interface:

- **Document Reading**: Uses `claude read` command for PDF/image text extraction
- **Action Extraction**: Calls Claude via CLI for intelligent NLP analysis
- **Task Execution**: Delegates to Claude Task agents via `claude --delegate`
- **Analysis**: Uses Claude for document summarization and insights

### How It Works

1. **CLI Wrapper** (`claude_cli.py`): Subprocess wrapper for Claude commands
2. **Automatic Detection**: Falls back gracefully if Claude Code not available
3. **Real Processing**: When Claude is available, all processing is real, not simulated

## Quick Start

### Prerequisites

```bash
# Install Claude Code (if not already installed)
# Visit: https://claude.ai/code

# Verify Claude Code is installed
claude --version
```

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Test Claude integration
python test_claude_integration.py
```

### Running the API

```bash
# Start the API server
python api.py
```

The API will be available at `http://localhost:8000`

### API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## Architecture

```
DocAutomate/
├── ingester.py      # Document ingestion and storage
├── extractor.py     # Action extraction with Claude NLP
├── workflow.py      # Workflow execution engine
├── api.py          # FastAPI REST endpoints
├── workflows/      # YAML workflow definitions
│   └── invoice.yaml
├── storage/        # Document storage (created at runtime)
└── state/         # Workflow state storage (created at runtime)
```

## Core Components

### 1. Document Ingester
- Handles multiple document formats
- Generates unique document IDs
- Manages document storage
- Queues documents for processing

### 2. Action Extractor
- Uses Claude's NLP capabilities
- Pydantic models for structured output
- Confidence scoring
- Validation and error handling

### 3. Workflow Engine
- YAML workflow definitions
- Jinja2 template support
- Action registry system
- State management
- Parallel execution support

### 4. REST API
- Document upload endpoint
- Workflow execution
- Status tracking
- Background processing

## Example Workflow

```yaml
name: "process_invoice"
parameters:
  - name: "invoice_id"
    type: "string"
    required: true

steps:
  - id: "validate_vendor"
    type: "api_call"
    config:
      url: "https://api.company.com/vendors"
      
  - id: "schedule_payment"
    type: "mcp_task"
    config:
      agent_name: "finance-agent"
      action: "schedule_payment"
```

## API Endpoints

- `POST /documents/upload` - Upload document for processing
- `GET /documents` - List all documents
- `GET /documents/{id}` - Get document status
- `POST /workflows/execute` - Execute workflow
- `GET /workflows` - List available workflows
- `GET /workflows/runs/{id}` - Get workflow run status

## Real Claude Code Integration

This framework now has **REAL integration** with Claude Code:

### Integrated Components

| Component | Simulated (Before) | Real (Now) | Claude Command |
|-----------|-------------------|------------|----------------|
| Document Reading | Placeholder text | Actual PDF/image extraction | `claude read <file>` |
| Action Extraction | Hardcoded JSON | Claude NLP analysis | `claude --json` with prompts |
| Task Execution | Logged only | Real Task agent calls | `claude --delegate <agent>` |
| Analysis | Mock insights | Claude analysis | `claude` with structured prompts |

### Integration Points

1. **ingester.py** (lines 119-126): Uses `claude read` for document extraction
2. **extractor.py** (lines 168-228): Calls Claude CLI for action extraction
3. **workflow.py** (lines 254-285): Executes Task agents via CLI
4. **workflow.py** (lines 352-395): Uses Claude for analysis

### Testing Integration

```bash
# Run integration test to verify Claude Code is working
python test_claude_integration.py

# Output will show:
# ✅ Claude Code Integration: ACTIVE (if installed)
# ⚠️ Claude Code Integration: SIMULATED (if not installed)
```

## Future Enhancements

- Redis/Celery for production job queue
- Database integration with SQLAlchemy
- Webhook support for external integrations
- Authentication and authorization
- Multi-tenant support
- Monitoring dashboard
- Scheduled workflow execution

## Testing

```bash
# Run tests
pytest

# Test with sample document
python test_sample.py
```

## License

MIT