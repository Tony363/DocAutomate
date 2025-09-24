# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DocAutomate is an enterprise document ingestion and action automation framework that extracts actionable items from documents (PDFs, images, text) and executes YAML-defined workflows. It leverages Claude's NLP capabilities for intelligent action extraction and provides a REST API for integration.

## Commands

### Running the application
```bash
# Start the API server (default port 8000)
python api.py

# Run test with sample document
python test_sample.py

# Run tests (when available)
pytest
```

### Code formatting and linting
```bash
# Format code
black .

# Lint code
flake8
```

## Architecture

The framework follows a modular pipeline architecture:

1. **Document Ingestion** (`ingester.py`): Accepts documents → generates unique IDs → stores in `storage/` → queues for processing
2. **Action Extraction** (`extractor.py`): Uses Claude NLP → extracts structured actions via Pydantic models → validates with confidence scoring
3. **Workflow Execution** (`workflow.py`): Loads YAML definitions from `workflows/` → executes steps with Jinja2 templating → manages state in `state/` directory
4. **REST API** (`api.py`): FastAPI endpoints → background task processing → async document handling

### Key Design Patterns

- **Async-First**: All core operations are async (document processing, workflow execution, API calls)
- **Queue-Based Processing**: Documents are queued for background processing to avoid blocking API responses
- **State Management**: Workflow runs maintain persistent state in JSON files (`state/` directory)
- **Template-Driven**: Workflows use Jinja2 templating for dynamic parameter substitution
- **Action Registry**: Extensible system for registering new action types (api_call, mcp_task, conditional, parallel, etc.)

### Workflow Step Types

The workflow engine supports these step types:
- `api_call`: External API integration with template support
- `mcp_task`: Integration with Claude Code MCP agents
- `conditional`: If/else branching based on conditions
- `parallel`: Execute multiple tasks concurrently
- `data_transform`: Transform data between steps
- `send_email`: Email notifications
- `webhook`: External webhook calls
- `claude_analyze`: Use Claude for analysis/summarization

### Data Flow

1. Document upload → `POST /documents/upload`
2. Ingester stores document → returns document_id
3. Background: Extractor processes document → identifies actions
4. Actions trigger workflows → `POST /workflows/execute`
5. Workflow engine executes steps → updates state
6. Status tracking via → `GET /workflows/runs/{id}`

## Important Directories

- `workflows/`: YAML workflow definitions (e.g., `invoice.yaml`)
- `storage/`: Document storage (created at runtime, contains document metadata and content)
- `state/`: Workflow execution state (created at runtime, JSON files with run status)
- `samples/`: Sample documents for testing

## API Endpoints

- `POST /documents/upload`: Upload document for processing
- `GET /documents`: List all documents
- `GET /documents/{id}`: Get document details and extracted actions
- `POST /workflows/execute`: Execute workflow with parameters
- `GET /workflows`: List available workflows
- `GET /workflows/{name}`: Get workflow definition
- `GET /workflows/runs/{id}`: Get workflow run status

## Testing

Run the test script with a sample invoice:
```bash
python test_sample.py
```

This will:
1. Create a sample invoice document
2. Ingest the document
3. Extract actions using Claude
4. Execute the invoice processing workflow
5. Display results at each step

## Key Classes and Functions

### ingester.py
- `Document`: Dataclass representing ingested documents
- `DocumentIngester.ingest()`: Main entry point for document processing
- `DocumentIngester._generate_document_id()`: Creates unique SHA-256 based IDs

### extractor.py
- `ExtractedAction`: Pydantic model for structured action representation
- `ActionExtractor.extract_actions()`: Uses Claude to identify actions from text
- Confidence scoring system (high/medium/low)

### workflow.py
- `WorkflowEngine.load_workflow()`: Loads YAML workflow definitions
- `WorkflowEngine.execute()`: Main workflow execution with step orchestration
- `ActionRegistry`: Extensible registry for step type handlers
- Template rendering with Jinja2 for dynamic parameters

### api.py
- FastAPI application with CORS support
- Background task processing for async operations
- Comprehensive error handling with HTTPException

## Development Notes

- The framework uses Claude's Read tool for PDF and image processing (via native Claude Code capabilities)
- Workflow definitions support Jinja2 templating with access to parameters and previous step results
- State persistence uses JSON files - for production, consider Redis/database integration
- The action registry pattern allows easy extension with new step types
- All async operations use Python's asyncio for concurrent processing