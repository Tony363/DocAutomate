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
import os
from pathlib import Path
import tempfile
import shutil

# Import our modules
from ingester import DocumentIngester, Document
from extractor import ActionExtractor, ExtractedAction
from workflow import WorkflowEngine, WorkflowRun, WorkflowStatus
from workflow_matcher import WorkflowMatcher

# Set up logging with more detail
import uuid
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Request tracking
def generate_request_id():
    """Generate unique request ID for tracking"""
    return str(uuid.uuid4())[:8]

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
workflow_matcher = WorkflowMatcher(workflow_engine)

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
async def process_document_background(document: Document, request_id: str = None):
    """Background task to extract actions from document"""
    request_id = request_id or generate_request_id()
    start_time = datetime.now()
    
    logger.info(f"[{request_id}] Starting background processing for document {document.id}")
    logger.debug(f"[{request_id}] Document details: filename={document.filename}, size={len(document.text) if document.text else 0} chars")
    
    try:
        # First validate that we have actual content to process
        if not document.text or len(document.text) < 50:
            logger.error(f"[{request_id}] Document {document.id} has insufficient text content ({len(document.text) if document.text else 0} chars)")
            document.status = "failed"
            document.error = "Insufficient text content extracted"
            await document_ingester._store_document(document)
            return
        
        # Check for extraction error patterns
        error_phrases = ['i need your permission', 'please grant permission', 'permission to read', 
                        'allow access', 'grant access', 'claude code is required']
        text_lower = document.text.lower()
        
        for phrase in error_phrases:
            if phrase in text_lower:
                logger.error(f"[{request_id}] Document {document.id} contains extraction error: '{phrase}'")
                document.status = "extraction_failed"
                document.error = f"Text extraction failed - permission or processing error detected"
                await document_ingester._store_document(document)
                return
        
        # Extract actions
        logger.info(f"[{request_id}] Extracting actions from document {document.id} ({len(document.text)} chars)")
        actions = await action_extractor.extract_actions(
            document.text,
            document_type='general'
        )
        
        logger.info(f"[{request_id}] Extracted {len(actions)} actions from document {document.id}")
        
        # Log each extracted action
        for i, action in enumerate(actions):
            logger.debug(f"[{request_id}] Action {i+1}: type={action.action_type}, workflow={action.workflow_name}, confidence={action.confidence_score:.2f}")
        
        # Update document with extracted actions - only mark as processed if extraction was successful
        document.extracted_actions = [action.dict() for action in actions]
        document.status = "processed" if len(document.text) > 100 else "partial"
        
        # Save updated document
        logger.debug(f"[{request_id}] Saving processed document {document.id}")
        await document_ingester._store_document(document)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Successfully processed document {document.id} in {processing_time:.2f}s: {len(actions)} actions extracted")
        
        # Auto-execute workflows if configured
        auto_executed_count = 0
        for action in actions:
            if action.confidence_score >= 0.85:  # High confidence threshold for auto-execution
                try:
                    # Use intelligent workflow matching
                    match_context = {
                        'action_type': action.action_type,
                        'parameters': action.parameters,
                        'document_type': document.metadata.get('type', 'general') if document.metadata else 'general'
                    }
                    
                    match_result = await workflow_matcher.match(action.workflow_name, match_context)
                    resolved_workflow = match_result.matched_workflow
                    
                    # Log the matching decision
                    if resolved_workflow != action.workflow_name:
                        logger.info(f"[{request_id}] Workflow matched: '{action.workflow_name}' -> '{resolved_workflow}' "
                                  f"(confidence: {match_result.confidence:.2f}, reason: {match_result.reason})")
                        if match_result.reasoning:
                            logger.debug(f"[{request_id}] Match reasoning: {match_result.reasoning}")
                    
                    # Check confidence threshold
                    if match_result.confidence < 0.3:
                        logger.error(f"[{request_id}] No suitable workflow match for '{action.workflow_name}' "
                                   f"(confidence: {match_result.confidence:.2f})")
                        continue
                    
                    # Warn on low confidence matches
                    if match_result.confidence < 0.7:
                        logger.warning(f"[{request_id}] Low confidence match: '{action.workflow_name}' -> '{resolved_workflow}' "
                                     f"(confidence: {match_result.confidence:.2f})")
                    
                    # Check if resolved workflow exists (should always exist if confidence > 0)
                    if resolved_workflow not in workflow_engine.workflows:
                        logger.error(f"[{request_id}] Resolved workflow '{resolved_workflow}' not found in engine")
                        continue
                    
                    logger.info(f"[{request_id}] Auto-executing workflow {resolved_workflow} (confidence: {action.confidence_score:.2f})")
                    
                    # Include document_id in parameters
                    params = dict(action.parameters)
                    params['document_id'] = document.id
                    
                    run = await workflow_engine.execute_workflow(
                        workflow_name=resolved_workflow,
                        document_id=document.id,
                        initial_parameters=params
                    )
                    auto_executed_count += 1
                    logger.info(f"[{request_id}] Auto-executed workflow {action.workflow_name}: run_id={run.run_id}")
                except Exception as e:
                    logger.error(f"[{request_id}] Failed to auto-execute workflow {action.workflow_name}: {e}")
                    logger.debug(f"[{request_id}] Stack trace:", exc_info=True)
        
        if auto_executed_count > 0:
            logger.info(f"[{request_id}] Auto-executed {auto_executed_count} workflows for document {document.id}")
        
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Failed to process document {document.id} after {processing_time:.2f}s: {e}")
        logger.debug(f"[{request_id}] Stack trace:", exc_info=True)
        
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
    request_id = generate_request_id()
    start_time = datetime.now()
    
    logger.info(f"[{request_id}] Document upload started: filename={file.filename}, content_type={file.content_type}, auto_process={auto_process}")
    
    tmp_path = None
    try:
        # Get file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        logger.info(f"[{request_id}] File size: {file_size} bytes ({file_size / 1024:.2f} KB)")
        
        # Save uploaded file to temp location
        logger.debug(f"[{request_id}] Saving uploaded file to temporary location")
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name
            logger.debug(f"[{request_id}] Temporary file created: {tmp_path}")
        
        # Ingest document
        logger.info(f"[{request_id}] Starting document ingestion for: {file.filename}")
        ingestion_start = datetime.now()
        document = await document_ingester.ingest_file(tmp_path)
        ingestion_time = (datetime.now() - ingestion_start).total_seconds()
        logger.info(f"[{request_id}] Document ingested in {ingestion_time:.2f}s: id={document.id}, status={document.status}")
        
        # Clean up temp file
        logger.debug(f"[{request_id}] Cleaning up temporary file: {tmp_path}")
        Path(tmp_path).unlink()
        tmp_path = None  # Mark as cleaned
        
        # Process in background if requested
        if auto_process:
            logger.info(f"[{request_id}] Queuing document {document.id} for background processing")
            background_tasks.add_task(process_document_background, document, request_id)
            message = "Document uploaded and queued for processing"
        else:
            logger.info(f"[{request_id}] Document {document.id} uploaded without auto-processing")
            message = "Document uploaded successfully"
        
        upload_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Document upload completed in {upload_time:.2f}s: {file.filename} -> {document.id}")
        
        return DocumentUploadResponse(
            document_id=document.id,
            filename=document.filename,
            status=document.status,
            message=message,
            extracted_actions=None
        )
        
    except Exception as e:
        upload_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Failed to upload document after {upload_time:.2f}s: {file.filename}")
        logger.error(f"[{request_id}] Error details: {e}")
        logger.debug(f"[{request_id}] Stack trace:", exc_info=True)
        
        # Clean up temp file if it exists
        if tmp_path and Path(tmp_path).exists():
            logger.debug(f"[{request_id}] Cleaning up temporary file after error: {tmp_path}")
            Path(tmp_path).unlink()
        
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

@app.get("/workflows/{workflow_name}")
async def get_workflow(workflow_name: str):
    """Get detailed definition of a specific workflow"""
    try:
        if workflow_name not in workflow_engine.workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return workflow_engine.workflows[workflow_name]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow {workflow_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/workflows/execute", response_model=WorkflowExecutionResponse)
async def execute_workflow(request: WorkflowExecutionRequest, background_tasks: BackgroundTasks):
    """Execute a workflow for a document"""
    request_id = generate_request_id()
    start_time = datetime.now()
    
    logger.info(f"[{request_id}] Workflow execution requested: workflow={request.workflow_name}, document={request.document_id}, auto={request.auto_execute}")
    logger.debug(f"[{request_id}] Parameters: {request.parameters}")
    
    try:
        # Validate document exists
        logger.debug(f"[{request_id}] Validating document {request.document_id}")
        document = document_ingester.get_document(request.document_id)
        if not document:
            logger.warning(f"[{request_id}] Document not found: {request.document_id}")
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Use intelligent workflow matching
        match_context = {
            'parameters': request.parameters,
            'document_id': request.document_id
        }
        
        match_result = await workflow_matcher.match(request.workflow_name, match_context)
        resolved_workflow = match_result.matched_workflow
        
        # Log the matching decision
        if resolved_workflow != request.workflow_name:
            logger.info(f"[{request_id}] Workflow matched: '{request.workflow_name}' -> '{resolved_workflow}' "
                      f"(confidence: {match_result.confidence:.2f}, reason: {match_result.reason})")
            if match_result.reasoning:
                logger.debug(f"[{request_id}] Match reasoning: {match_result.reasoning}")
        
        # Check confidence threshold
        if match_result.confidence < 0.3:
            logger.warning(f"[{request_id}] No suitable workflow match for '{request.workflow_name}' "
                         f"(confidence: {match_result.confidence:.2f})")
            raise HTTPException(status_code=404, 
                              detail=f"No suitable workflow match for '{request.workflow_name}' (confidence: {match_result.confidence:.2f})")
        
        # Warn on low confidence matches but proceed
        if match_result.confidence < 0.7:
            logger.warning(f"[{request_id}] Low confidence match: '{request.workflow_name}' -> '{resolved_workflow}' "
                         f"(confidence: {match_result.confidence:.2f})")
        
        # Validate workflow exists
        if resolved_workflow not in workflow_engine.workflows:
            logger.warning(f"[{request_id}] Resolved workflow not found: {resolved_workflow}")
            raise HTTPException(status_code=404, detail=f"Workflow '{resolved_workflow}' not found")
        
        # Execute workflow
        if request.auto_execute:
            # Execute immediately
            logger.info(f"[{request_id}] Executing workflow immediately: {request.workflow_name}")
            exec_start = datetime.now()
            
            # Include document_id in parameters
            params = dict(request.parameters)
            params['document_id'] = request.document_id
            
            run = await workflow_engine.execute_workflow(
                workflow_name=resolved_workflow,
                document_id=request.document_id,
                initial_parameters=params
            )
            
            exec_time = (datetime.now() - exec_start).total_seconds()
            logger.info(f"[{request_id}] Workflow executed in {exec_time:.2f}s: run_id={run.run_id}, status={run.status.value}")
            
            # Update document with workflow run
            if document.workflow_runs is None:
                document.workflow_runs = []
            document.workflow_runs.append(run.run_id)
            await document_ingester._store_document(document)
            
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"[{request_id}] Workflow execution completed in {total_time:.2f}s")
            
            return WorkflowExecutionResponse(
                run_id=run.run_id,
                workflow_name=run.workflow_name,
                document_id=run.document_id,
                status=run.status.value,
                message="Workflow executed"
            )
        else:
            # Queue for background execution
            logger.info(f"[{request_id}] Queueing workflow for background execution: {request.workflow_name}")
            
            async def execute_in_background():
                bg_request_id = f"{request_id}-bg"
                logger.info(f"[{bg_request_id}] Background workflow execution started: {request.workflow_name}")
                
                try:
                    # Include document_id in parameters
                    params = dict(request.parameters)
                    params['document_id'] = request.document_id
                    
                    run = await workflow_engine.execute_workflow(
                        workflow_name=resolved_workflow,
                        document_id=request.document_id,
                        initial_parameters=params
                    )
                    
                    if document.workflow_runs is None:
                        document.workflow_runs = []
                    document.workflow_runs.append(run.run_id)
                    await document_ingester._store_document(document)
                    
                    logger.info(f"[{bg_request_id}] Background workflow completed: run_id={run.run_id}")
                except Exception as e:
                    logger.error(f"[{bg_request_id}] Background workflow failed: {e}")
                    logger.debug(f"[{bg_request_id}] Stack trace:", exc_info=True)
            
            background_tasks.add_task(execute_in_background)
            
            logger.info(f"[{request_id}] Workflow queued successfully")
            
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
        total_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Failed to execute workflow after {total_time:.2f}s: {e}")
        logger.debug(f"[{request_id}] Stack trace:", exc_info=True)
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
    port = 8001  # Using 8001 since 8000 is in use
    print(f"Starting DocAutomate API on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")