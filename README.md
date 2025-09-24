# DocAutomate Framework

Enterprise-ready document ingestion and action automation framework built on top of Claude Code capabilities.

## Features

- **Multi-format Document Ingestion**: PDF, images, text, Word documents
- **Intelligent Action Extraction**: Uses Claude's NLP to identify actionable items
- **YAML-based Workflows**: Define complex automation workflows declaratively
- **REST API**: Full-featured API for integration
- **Pydantic Validation**: Structured, validated action extraction
- **Async Processing**: Concurrent document processing with job queue
- **State Management**: Track workflow execution status
- **Extensible Action Registry**: Easy to add new action types

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
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

## Integration with Claude Code

This framework leverages Claude Code's existing capabilities:
- **Read Tool**: For PDF and image processing
- **Task Agents**: For complex workflow orchestration
- **MCP Servers**: For extensible functionality

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