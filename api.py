#!/usr/bin/env python3
"""
REST API for DocAutomate Framework
Provides endpoints for document ingestion and workflow management
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import logging
from pathlib import Path
import tempfile
import shutil

# Import our modules
from ingester import DocumentIngester, Document
from extractor import ActionExtractor, ExtractedAction
from workflow import WorkflowEngine, WorkflowRun, WorkflowStatus

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="DocAutomate API",
    description="Enterprise Document Ingestion and Action Automation Framework",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
document_ingester = DocumentIngester()
action_extractor = ActionExtractor()
workflow_engine = WorkflowEngine()

# Pydantic models for API

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str
    extracted_actions: Optional[List[Dict]]

class WorkflowExecutionRequest(BaseModel):
    document_id: str
    workflow_name: str
    parameters: Dict[str, Any]
    auto_execute: bool = False

class WorkflowExecutionResponse(BaseModel):
    run_id: str
    workflow_name: str
    document_id: str
    status: str
    message: str

class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    ingested_at: str
    workflow_runs: List[str]
    extracted_actions: Optional[List[Dict]]

class WorkflowRunStatusResponse(BaseModel):
    run_id: str
    workflow_name: str
    status: str
    started_at: str
    completed_at: Optional[str]
    current_step: Optional[str]
    outputs: Dict[str, Any]
    error: Optional[str]

# Background task for processing document
async def process_document_background(document: Document):
    """Background task to extract actions from document"""
    try:
        # Extract actions
        actions = await action_extractor.extract_actions(
            document.text,
            document_type='general'
        )
        
        # Update document with extracted actions
        document.extracted_actions = [action.dict() for action in actions]
        document.status = "processed"
        
        # Save updated document
        await document_ingester._store_document(document)
        
        logger.info(f"Processed document {document.id}: {len(actions)} actions extracted")
        
        # Auto-execute workflows if configured
        for action in actions:
            if action.confidence_score >= 0.85:  # High confidence threshold for auto-execution
                try:
                    run = await workflow_engine.execute_workflow(
                        workflow_name=action.workflow_name,
                        document_id=document.id,
                        initial_parameters=action.parameters
                    )
                    logger.info(f"Auto-executed workflow {action.workflow_name}: {run.run_id}")
                except Exception as e:
                    logger.error(f"Failed to auto-execute workflow: {e}")
        
    except Exception as e:
        logger.error(f"Failed to process document {document.id}: {e}")
        document.status = "failed"
        await document_ingester._store_document(document)

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "DocAutomate API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/documents/upload",
            "list_documents": "/documents",
            "document_status": "/documents/{document_id}",
            "execute_workflow": "/workflows/execute",
            "list_workflows": "/workflows",
            "workflow_status": "/workflows/runs/{run_id}"
        }
    }

@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_process: bool = True
):
    """Upload a document for processing"""
    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
        
        # Ingest document
        document = await document_ingester.ingest_file(tmp_path)
        
        # Clean up temp file
        Path(tmp_path).unlink()
        
        # Process in background if requested
        if auto_process:
            background_tasks.add_task(process_document_background, document)
            message = "Document uploaded and queued for processing"
        else:
            message = "Document uploaded successfully"
        
        return DocumentUploadResponse(
            document_id=document.id,
            filename=document.filename,
            status=document.status,
            message=message,
            extracted_actions=None
        )
        
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents", response_model=List[DocumentStatusResponse])
async def list_documents(status: Optional[str] = None):
    """List all documents, optionally filtered by status"""
    try:
        documents = document_ingester.list_documents(status=status)
        
        return [
            DocumentStatusResponse(
                document_id=doc.id,
                filename=doc.filename,
                status=doc.status,
                ingested_at=doc.ingested_at,
                workflow_runs=doc.workflow_runs or [],
                extracted_actions=doc.extracted_actions
            )
            for doc in documents
        ]
        
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(document_id: str):
    """Get status of a specific document"""
    try:
        document = document_ingester.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return DocumentStatusResponse(
            document_id=document.id,
            filename=document.filename,
            status=document.status,
            ingested_at=document.ingested_at,
            workflow_runs=document.workflow_runs or [],
            extracted_actions=document.extracted_actions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/extract")
async def extract_actions(document_id: str, background_tasks: BackgroundTasks):
    """Manually trigger action extraction for a document"""
    try:
        document = document_ingester.get_document(document_id)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        background_tasks.add_task(process_document_background, document)
        
        return {
            "message": "Action extraction queued",
            "document_id": document_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workflows")
async def list_workflows():
    """List available workflows"""
    try:
        workflows = []
        for name, workflow in workflow_engine.workflows.items():
            workflows.append({
                "name": name,
                "description": workflow.get("description", ""),
                "version": workflow.get("version", "1.0.0"),
                "parameters": workflow.get("parameters", []),
                "steps": len(workflow.get("steps", []))
            })
        
        return {"workflows": workflows}
        
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/workflows/execute", response_model=WorkflowExecutionResponse)
async def execute_workflow(request: WorkflowExecutionRequest, background_tasks: BackgroundTasks):
    """Execute a workflow for a document"""
    try:
        # Validate document exists
        document = document_ingester.get_document(request.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Validate workflow exists
        if request.workflow_name not in workflow_engine.workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Execute workflow
        if request.auto_execute:
            # Execute immediately
            run = await workflow_engine.execute_workflow(
                workflow_name=request.workflow_name,
                document_id=request.document_id,
                initial_parameters=request.parameters
            )
            
            # Update document with workflow run
            if document.workflow_runs is None:
                document.workflow_runs = []
            document.workflow_runs.append(run.run_id)
            await document_ingester._store_document(document)
            
            return WorkflowExecutionResponse(
                run_id=run.run_id,
                workflow_name=run.workflow_name,
                document_id=run.document_id,
                status=run.status.value,
                message="Workflow executed"
            )
        else:
            # Queue for background execution
            async def execute_in_background():
                run = await workflow_engine.execute_workflow(
                    workflow_name=request.workflow_name,
                    document_id=request.document_id,
                    initial_parameters=request.parameters
                )
                if document.workflow_runs is None:
                    document.workflow_runs = []
                document.workflow_runs.append(run.run_id)
                await document_ingester._store_document(document)
            
            background_tasks.add_task(execute_in_background)
            
            return WorkflowExecutionResponse(
                run_id="pending",
                workflow_name=request.workflow_name,
                document_id=request.document_id,
                status="queued",
                message="Workflow queued for execution"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workflows/runs")
async def list_workflow_runs(workflow_name: Optional[str] = None):
    """List all workflow runs"""
    try:
        runs = workflow_engine.list_runs(workflow_name=workflow_name)
        
        return {
            "runs": [
                {
                    "run_id": run.run_id,
                    "workflow_name": run.workflow_name,
                    "document_id": run.document_id,
                    "status": run.status.value,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at
                }
                for run in runs
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to list workflow runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workflows/runs/{run_id}", response_model=WorkflowRunStatusResponse)
async def get_workflow_run_status(run_id: str):
    """Get status of a specific workflow run"""
    try:
        run = workflow_engine.get_run_status(run_id)
        
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        
        return WorkflowRunStatusResponse(
            run_id=run.run_id,
            workflow_name=run.workflow_name,
            status=run.status.value,
            started_at=run.started_at,
            completed_at=run.completed_at,
            current_step=run.current_step,
            outputs=run.outputs,
            error=run.error
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow run status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "components": {
            "ingester": "operational",
            "extractor": "operational",
            "workflow_engine": "operational",
            "api": "operational"
        }
    }

# Run the API
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")