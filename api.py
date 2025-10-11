#!/usr/bin/env python3
"""
REST API for DocAutomate Framework
Provides endpoints for document ingestion and workflow management
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Body
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
from services.claude_service import claude_service
from claude_cli import SuperClaudeMCP
from utils.file_operations import FileOperations
from enum import Enum

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

# In-memory orchestration status tracking
orchestration_status = {}

class OrchestrationStatus(Enum):
    """Orchestration status enumeration"""
    QUEUED = "queued"
    RUNNING = "running"
    ANALYSIS = "analysis"
    CONSENSUS = "consensus"
    REMEDIATION = "remediation"
    VALIDATION = "validation"
    COMPLETED = "completed"
    FAILED = "failed"

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
    content_type: str
    size_bytes: Optional[int]
    claude_agent: Optional[str]
    quality_score: Optional[float]
    claude_analysis: Optional[Dict]
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
    steps_completed: Optional[List[Dict[str, Any]]]
    duration_seconds: Optional[float]
    error: Optional[str]

class OrchestrationRequest(BaseModel):
    document_id: str
    workflow_type: str = "full"  # full, analysis_only, remediation_only
    agents: Optional[List[str]] = None
    models: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = None

class OrchestrationResponse(BaseModel):
    orchestration_id: str
    document_id: str
    status: str
    message: str
    results: Optional[Dict[str, Any]] = None

class AnalysisRequest(BaseModel):
    agents: Optional[List[str]] = None
    parallel: bool = True

class ConsensusRequest(BaseModel):
    analysis_data: Dict[str, Any]
    models: Optional[List[str]] = None

class RemediationRequest(BaseModel):
    issues: List[Dict[str, Any]]
    template: Optional[str] = None

class ValidationRequest(BaseModel):
    original_content: str
    remediated_content: str
    validation_type: str = "quality"  # quality, security, compliance

class FolderCompressionRequest(BaseModel):
    folder_path: str
    output_name: Optional[str] = None
    output_filename: Optional[str] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    compression_level: int = 6
    use_dsl: bool = True

class FolderCompressionResponse(BaseModel):
    success: bool
    output_path: Optional[str]
    archive_path: Optional[str]
    files_compressed: Optional[int]
    files_included: Optional[int]
    original_size_bytes: Optional[int]
    compressed_size_bytes: Optional[int]
    compression_ratio: Optional[str]
    duration_seconds: Optional[float]
    error: Optional[str]
    workflow_run_id: Optional[str]

class ActionExtractionResponse(BaseModel):
    document_id: str
    status: str
    extracted_actions: List[Dict[str, Any]]
    auto_triggered_workflows: int
    analysis_summary: Dict[str, Any]

class ActionExtractionRequest(BaseModel):
    auto_execute: bool = False

class DocumentConversionRequest(BaseModel):
    document_id: Optional[str] = None
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    output_format: str = "pdf"
    target_format: Optional[str] = None
    quality: str = "high"
    preserve_formatting: bool = True
    use_dsl: bool = True

class DocumentConversionResponse(BaseModel):
    success: bool
    output_path: Optional[str]
    archive_path: Optional[str]
    conversion_method: Optional[str]
    original_file: Optional[str]
    file_size_bytes: Optional[int]
    conversion_time_seconds: Optional[float]
    error: Optional[str]
    workflow_run_id: Optional[str]

class BatchConversionRequest(BaseModel):
    input_files: List[str]
    document_ids: Optional[List[str]] = None
    output_directory: str
    conversion_type: str = "docx_to_pdf"
    target_format: Optional[str] = None
    parallel: bool = True
    max_workers: int = 4
    use_dsl: bool = True

EXTRACTION_ERROR_PHRASES = [
    'i need your permission',
    'please grant permission',
    'permission to read',
    'allow access',
    'grant access',
    'claude code is required'
]


async def _extract_actions_for_document(
    document: Document,
    request_id: str,
    run_workflows: bool = True
) -> Dict[str, Any]:
    """Shared extraction workflow for background and synchronous requests"""
    logger.info(f"[{request_id}] Extracting actions for document {document.id}")

    text_content = document.text or ""
    if len(text_content) < 50:
        logger.error(f"[{request_id}] Document {document.id} has insufficient text content ({len(text_content)} chars)")
        document.status = "failed"
        document.error = "Insufficient text content extracted"
        await document_ingester._store_document(document)
        return {"actions": [], "auto_runs": 0, "analysis_summary": {}, "status": document.status}

    text_lower = text_content.lower()
    for phrase in EXTRACTION_ERROR_PHRASES:
        if phrase in text_lower:
            logger.error(f"[{request_id}] Document {document.id} contains extraction error: '{phrase}'")
            document.status = "extraction_failed"
            document.error = "Text extraction failed - permission or processing error detected"
            await document_ingester._store_document(document)
            return {"actions": [], "auto_runs": 0, "analysis_summary": {}, "status": document.status}

    document_type = (document.metadata or {}).get('document_type', 'general')
    actions = await action_extractor.extract_actions(
        text_content,
        document_type=document_type
    )

    actions_payload: List[Dict[str, Any]] = []
    high_confidence = 0
    for index, action in enumerate(actions, start=1):
        if action.confidence_score >= 0.85:
            high_confidence += 1

        if not action.action_id:
            action.action_id = f"{document.id}-act-{uuid.uuid4().hex[:8]}"

        logger.debug(
            f"[{request_id}] Action {index}: id={action.action_id}, type={action.action_type}, "
            f"workflow={action.workflow_name}, confidence={action.confidence_score:.2f}"
        )
        actions_payload.append(action.dict())

    analysis_summary = {
        "total_actions": len(actions_payload),
        "high_confidence": high_confidence,
        "document_type": document_type
    }

    document.metadata = document.metadata or {}
    document.metadata.setdefault('document_type', document_type)
    document.metadata['last_extracted_at'] = datetime.utcnow().isoformat()
    document.metadata['claude_analysis'] = analysis_summary
    document.metadata['quality_score'] = max(
        (action.confidence_score for action in actions),
        default=0.0
    )
    document.metadata.setdefault('claude_agent', 'requirements-analyst')

    document.extracted_actions = actions_payload
    document.status = "processed" if len(text_content) > 100 else "partial"
    if not actions_payload:
        document.status = "processed_no_actions"

    document.quality_score = document.metadata['quality_score']
    document.primary_agent = document.metadata['claude_agent']
    document.analysis_summary = analysis_summary

    auto_executed_count = 0
    if run_workflows and actions:
        for action in actions:
            if action.confidence_score < 0.85:
                continue

            try:
                match_context = {
                    'action_type': action.action_type,
                    'parameters': action.parameters,
                    'document_type': document.metadata.get('document_type', 'general')
                }

                match_result = await workflow_matcher.match(action.workflow_name, match_context)
                resolved_workflow = match_result.matched_workflow

                if resolved_workflow != action.workflow_name:
                    logger.info(
                        f"[{request_id}] Workflow matched: '{action.workflow_name}' -> '{resolved_workflow}' "
                        f"(confidence: {match_result.confidence:.2f}, reason: {match_result.reason})"
                    )
                    if match_result.reasoning:
                        logger.debug(f"[{request_id}] Match reasoning: {match_result.reasoning}")

                if match_result.confidence < 0.3:
                    logger.warning(
                        f"[{request_id}] No suitable workflow match for '{action.workflow_name}' "
                        f"(confidence: {match_result.confidence:.2f})"
                    )
                    continue

                if match_result.confidence < 0.7:
                    logger.warning(
                        f"[{request_id}] Low confidence match: '{action.workflow_name}' -> '{resolved_workflow}' "
                        f"(confidence: {match_result.confidence:.2f})"
                    )

                if resolved_workflow not in workflow_engine.workflows:
                    logger.warning(f"[{request_id}] Resolved workflow '{resolved_workflow}' not found in engine")
                    continue

                params = dict(action.parameters)
                params['document_id'] = document.id

                if resolved_workflow == 'document_signature':
                    if 'parties' not in params:
                        if 'party1' in params and 'party2' in params:
                            params['parties'] = [params.pop('party1'), params.pop('party2')]
                        elif 'party' in params:
                            params['parties'] = [params.pop('party')]

                if 'document_type' not in params:
                    params['document_type'] = document.metadata.get('document_type', 'general')

                logger.info(
                    f"[{request_id}] Auto-executing workflow {resolved_workflow} "
                    f"(confidence: {action.confidence_score:.2f})"
                )

                run = await workflow_engine.execute_workflow(
                    workflow_name=resolved_workflow,
                    document_id=document.id,
                    initial_parameters=params
                )

                if document.workflow_runs is None:
                    document.workflow_runs = []
                document.workflow_runs.append(run.run_id)
                auto_executed_count += 1
            except ValueError as e:
                logger.warning(f"[{request_id}] Validation error for workflow {action.workflow_name}: {e}")
                logger.debug(f"[{request_id}] Stack trace:", exc_info=True)
            except Exception as exc:
                logger.error(f"[{request_id}] Failed to auto-execute workflow {action.workflow_name}: {exc}")
                logger.debug(f"[{request_id}] Stack trace:", exc_info=True)

    document.metadata['auto_triggered_workflows'] = auto_executed_count
    await document_ingester._store_document(document)

    return {
        "actions": actions_payload,
        "auto_runs": auto_executed_count,
        "analysis_summary": analysis_summary,
        "status": document.status
    }

# Background task for processing document
async def process_document_background(document: Document, request_id: str = None):
    """Background task to extract actions from document"""
    request_id = request_id or generate_request_id()
    start_time = datetime.now()
    
    logger.info(f"[{request_id}] Starting background processing for document {document.id}")
    logger.debug(f"[{request_id}] Document details: filename={document.filename}, size={len(document.text) if document.text else 0} chars")
    
    try:
        result = await _extract_actions_for_document(document, request_id, run_workflows=True)
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"[{request_id}] Successfully processed document {document.id} in {processing_time:.2f}s: "
            f"{len(result['actions'])} actions extracted (auto workflows: {result['auto_runs']})"
        )
        
    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Failed to process document {document.id} after {processing_time:.2f}s: {e}")
        logger.debug(f"[{request_id}] Stack trace:", exc_info=True)
        
        document.status = "failed"
        await document_ingester._store_document(document)

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint with API information aligned to README contract"""
    api_port = int(os.getenv("API_PORT", "8000"))
    base_url = f"http://localhost:{api_port}"

    return {
        "name": "DocAutomate API",
        "version": "2.0.0",
        "description": "Enterprise Document Processing via Claude Code Delegation",
        "documentation": f"{base_url}/docs",
        "health": f"{base_url}/health",
        "features": [
            "Universal document processing",
            "Pure Claude Code delegation",
            "Multi-agent orchestration",
            "DSL-driven configuration",
            "Multi-model consensus validation",
            "Desktop GUI application"
        ],
        "endpoints": {
            "upload": "/documents/upload",
            "list_documents": "/documents",
            "document_status": "/documents/{document_id}",
            "execute_workflow": "/workflows/execute",
            "list_workflows": "/workflows",
            "workflow_status": "/workflows/runs/{run_id}",
            "compress_folder": "/documents/compress-folder",
            "convert_document": "/documents/convert/docx-to-pdf",
            "batch_convert": "/documents/convert/batch",
            "orchestrate": "/orchestrate/workflow"
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
                content_type=doc.content_type,
                size_bytes=(doc.metadata or {}).get('size_bytes'),
                claude_agent=doc.primary_agent or (doc.metadata or {}).get('claude_agent'),
                quality_score=doc.quality_score if doc.quality_score is not None else (doc.metadata or {}).get('quality_score'),
                claude_analysis=doc.analysis_summary or (doc.metadata or {}).get('claude_analysis'),
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
        
        metadata = document.metadata or {}
        
        return DocumentStatusResponse(
            document_id=document.id,
            filename=document.filename,
            status=document.status,
            ingested_at=document.ingested_at,
            content_type=document.content_type,
            size_bytes=metadata.get('size_bytes'),
            claude_agent=document.primary_agent or metadata.get('claude_agent'),
            quality_score=document.quality_score if document.quality_score is not None else metadata.get('quality_score'),
            claude_analysis=document.analysis_summary or metadata.get('claude_analysis'),
            workflow_runs=document.workflow_runs or [],
            extracted_actions=document.extracted_actions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/extract", response_model=ActionExtractionResponse)
async def extract_actions(document_id: str, request: Optional[ActionExtractionRequest] = None):
    """Manually trigger action extraction for a document and return structured results"""
    request_id = generate_request_id()
    logger.info(f"[{request_id}] Manual action extraction requested for document {document_id}")

    try:
        document = document_ingester.get_document(document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        extraction_request = request or ActionExtractionRequest()

        result = await _extract_actions_for_document(
            document=document,
            request_id=request_id,
            run_workflows=extraction_request.auto_execute
        )

        return ActionExtractionResponse(
            document_id=document.id,
            status=result["status"],
            extracted_actions=result["actions"],
            auto_triggered_workflows=result["auto_runs"],
            analysis_summary=result["analysis_summary"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Failed to extract actions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/{document_id}/actions", response_model=ActionExtractionResponse)
async def get_document_actions(document_id: str):
    """Retrieve previously extracted actions for a document"""
    document = document_ingester.get_document(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    actions = document.extracted_actions or []
    analysis_summary = document.analysis_summary or (document.metadata or {}).get('claude_analysis') or {}
    auto_runs = (document.metadata or {}).get('auto_triggered_workflows', 0)

    return ActionExtractionResponse(
        document_id=document.id,
        status=document.status,
        extracted_actions=actions,
        auto_triggered_workflows=auto_runs,
        analysis_summary=analysis_summary
    )

@app.get("/workflows")
async def list_workflows():
    """List available workflows"""
    try:
        workflow_details = []
        for name, workflow in workflow_engine.workflows.items():
            steps = workflow.get("steps", [])
            metadata = workflow.get("metadata", {})

            workflow_details.append({
                "name": name,
                "description": workflow.get("description", ""),
                "version": workflow.get("version", "1.0.0"),
                "parameters": workflow.get("parameters", []),
                "step_count": len(steps),
                "steps": [
                    {
                        "id": step.get("id"),
                        "type": step.get("type"),
                        "description": step.get("description", "")
                    }
                    for step in steps
                ],
                "metadata": metadata,
                "tags": metadata.get("tags", []),
                "sla_hours": metadata.get("sla_hours")
            })
        
        return {
            "workflows": workflow_details,
            "total": len(workflow_details)
        }
        
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workflows/{workflow_name}")
async def get_workflow(workflow_name: str):
    """Get detailed definition of a specific workflow"""
    try:
        if workflow_name not in workflow_engine.workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        workflow = workflow_engine.workflows[workflow_name]
        steps = workflow.get("steps", [])
        metadata = workflow.get("metadata", {})
        
        return {
            "name": workflow.get("name", workflow_name),
            "description": workflow.get("description", ""),
            "version": workflow.get("version", "1.0.0"),
            "parameters": workflow.get("parameters", []),
            "step_count": len(steps),
            "steps": steps,
            "metadata": metadata,
            "tags": metadata.get("tags", [])
        }
        
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
async def list_workflow_runs(
    workflow_name: Optional[str] = None,
    status: Optional[str] = None,
    document_id: Optional[str] = None
):
    """List all workflow runs"""
    try:
        runs = workflow_engine.list_runs(workflow_name=workflow_name)
        run_details = []

        for run in runs:
            if status and run.status.value != status:
                continue
            if document_id and run.document_id != document_id:
                continue

            duration_seconds = None
            if run.started_at and run.completed_at:
                try:
                    duration_seconds = (
                        datetime.fromisoformat(run.completed_at) -
                        datetime.fromisoformat(run.started_at)
                    ).total_seconds()
                except ValueError:
                    duration_seconds = None

            run_details.append({
                "run_id": run.run_id,
                "workflow_name": run.workflow_name,
                "document_id": run.document_id,
                "status": run.status.value,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "current_step": run.current_step,
                "duration_seconds": duration_seconds,
                "result": run.outputs.get('final_result') if isinstance(run.outputs, dict) else None
            })
        
        return {
            "runs": run_details,
            "total": len(run_details)
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
            steps_completed=[
                {
                    "step_id": step_id,
                    "status": payload.get("status", "completed") if isinstance(payload, dict) else "completed",
                    "result": payload
                }
                for step_id, payload in (run.outputs.items() if isinstance(run.outputs, dict) else [])
            ],
            duration_seconds=(
                (
                    datetime.fromisoformat(run.completed_at) -
                    datetime.fromisoformat(run.started_at)
                ).total_seconds()
                if run.started_at and run.completed_at else None
            ),
            error=run.error
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow run status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Orchestration Endpoints

@app.post("/orchestrate/workflow", response_model=OrchestrationResponse)
async def orchestrate_workflow(request: OrchestrationRequest, background_tasks: BackgroundTasks):
    """Execute complete document orchestration workflow using Claude Code"""
    request_id = generate_request_id()
    orchestration_id = f"orch_{request_id}"
    
    logger.info(f"[{request_id}] Orchestration requested for document {request.document_id}, type: {request.workflow_type}")
    
    try:
        # Get document
        document = document_ingester.get_document(request.document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Initialize orchestration status tracking
        orchestration_status[orchestration_id] = {
            "orchestration_id": orchestration_id,
            "document_id": request.document_id,
            "status": OrchestrationStatus.QUEUED.value,
            "message": "Orchestration queued for execution",
            "steps_completed": [],
            "current_step": None,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "results": None
        }
        
        # Prepare orchestration task
        async def run_orchestration():
            try:
                orchestration_status[orchestration_id]["status"] = OrchestrationStatus.RUNNING.value
                orchestration_status[orchestration_id]["current_step"] = "starting"
                
                logger.info(f"[{orchestration_id}] Starting orchestration workflow")
                
                # Get document metadata
                metadata = document.metadata or {}
                metadata["document_id"] = document.id
                metadata["content_type"] = document.content_type
                
                # Update status for each step
                orchestration_status[orchestration_id]["current_step"] = "analysis"
                orchestration_status[orchestration_id]["status"] = OrchestrationStatus.ANALYSIS.value
                
                # Run orchestration through Claude service
                results = await claude_service.orchestrate_workflow(
                    document_id=document.id,
                    document_content=document.text,
                    document_metadata=metadata,
                    workflow_config=request.config
                )
                
                logger.info(f"[{orchestration_id}] Orchestration completed with quality score: {results.get('final_quality_score', 0)}")
                
                # Save remediated document to filesystem if available
                remediated_content = None
                remediation_path = None
                
                # Extract remediated content from the orchestration results
                remediation_step = results.get('steps', {}).get('remediation', {})
                if remediation_step.get('status') == 'completed':
                    # Get the actual remediated content from claude_service
                    # This should be available in the orchestration workflow results
                    if 'remediated_content' in results:
                        remediated_content = results['remediated_content']
                    elif hasattr(claude_service, '_last_remediation_result'):
                        # Fallback to get content from service if stored there
                        remediated_content = getattr(claude_service, '_last_remediation_result', None)
                        
                    if remediated_content:
                        # Save remediated document to filesystem
                        output_dir = Path(f"docs/generated/{document.id}")
                        output_dir.mkdir(parents=True, exist_ok=True)
                        
                        output_file = output_dir / "remediated_document.md"
                        output_file.write_text(remediated_content, encoding='utf-8')
                        remediation_path = str(output_file)
                        
                        logger.info(f"[{orchestration_id}] Saved remediated document to {remediation_path}")
                
                # Store results with remediation path
                document.metadata = document.metadata or {}
                document.metadata["orchestration_results"] = results
                
                # Store remediation path in document metadata
                if remediation_path:
                    document.metadata["remediation_path"] = remediation_path
                    results["remediation_path"] = remediation_path
                
                await document_ingester._store_document(document)
                
                # Update final orchestration status
                orchestration_status[orchestration_id].update({
                    "status": OrchestrationStatus.COMPLETED.value,
                    "current_step": "completed",
                    "completed_at": datetime.now().isoformat(),
                    "results": results,
                    "steps_completed": list(results.get('steps', {}).keys())
                })
                
            except Exception as e:
                logger.error(f"[{orchestration_id}] Orchestration failed: {e}")
                orchestration_status[orchestration_id].update({
                    "status": OrchestrationStatus.FAILED.value,
                    "current_step": "failed",
                    "completed_at": datetime.now().isoformat(),
                    "error": str(e)
                })
        
        # Queue orchestration
        background_tasks.add_task(run_orchestration)
        
        return OrchestrationResponse(
            orchestration_id=orchestration_id,
            document_id=request.document_id,
            status="queued",
            message="Orchestration workflow queued for execution"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Failed to start orchestration: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/analyze")
async def analyze_document(document_id: str, request: AnalysisRequest):
    """Perform multi-agent analysis on document using Claude Code"""
    request_id = generate_request_id()
    
    logger.info(f"[{request_id}] Analysis requested for document {document_id}")
    
    try:
        # Get document
        document = document_ingester.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Perform multi-agent analysis
        metadata = {"document_id": document_id, "content_type": document.content_type}
        results = await claude_service.multi_agent_analysis(
            document_content=document.text,
            document_metadata=metadata,
            agents=request.agents
        )
        
        # Convert results to serializable format
        analysis_results = {}
        for agent, result in results.items():
            analysis_results[agent] = {
                "success": result.success,
                "confidence": result.confidence,
                "analysis": result.analysis
            }
        
        return {
            "document_id": document_id,
            "analysis": analysis_results,
            "agent_count": len(results),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/synthesize")
async def synthesize_issues(document_id: str, request: ConsensusRequest):
    """Synthesize issues with multi-model consensus using Claude Code"""
    request_id = generate_request_id()
    
    logger.info(f"[{request_id}] Synthesis requested for document {document_id}")
    
    try:
        # Convert analysis data to proper format
        from services.claude_service import AnalysisResult
        analysis_results = {}
        for agent, data in request.analysis_data.items():
            analysis_results[agent] = AnalysisResult(
                success=data.get("success", True),
                analysis=data.get("analysis", {}),
                agent_used=agent,
                confidence=data.get("confidence", 0.5)
            )
        
        # Perform consensus validation
        consensus = await claude_service.consensus_validation(
            analysis_results=analysis_results,
            document_id=document_id,
            models=request.models
        )
        
        return {
            "document_id": document_id,
            "consensus": consensus.consensus,
            "agreement_score": consensus.agreement_score,
            "models_used": consensus.models_used,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/remediate")
async def remediate_document(document_id: str, request: RemediationRequest):
    """Generate remediated document using Claude Code"""
    request_id = generate_request_id()
    
    logger.info(f"[{request_id}] Remediation requested for document {document_id}")
    
    try:
        # Get document
        document = document_ingester.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Generate remediation
        remediation = await claude_service.generate_remediation(
            document_content=document.text,
            issues=request.issues,
            document_id=document_id
        )
        
        if remediation.success:
            # Store remediated content to filesystem with UTF-8 encoding
            output_dir = Path(f"docs/generated/{document_id}")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_file = output_dir / "remediated_document.md"
            output_file.write_text(remediation.remediated_content, encoding='utf-8')
            
            # Store remediation path in document metadata
            document.metadata = document.metadata or {}
            document.metadata["remediation_path"] = str(output_file)
            await document_ingester._store_document(document)
            
            return {
                "document_id": document_id,
                "remediation_path": str(output_file),
                "issues_resolved": remediation.issues_resolved,
                "quality_score": remediation.quality_score,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise Exception("Remediation failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Remediation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/validate")
async def validate_document(document_id: str, request: ValidationRequest):
    """Perform quality validation on document using Claude Code"""
    request_id = generate_request_id()
    
    logger.info(f"[{request_id}] Validation requested for document {document_id}")
    
    try:
        # Perform quality validation
        validation = await claude_service.quality_validation(
            remediated_content=request.remediated_content,
            original_content=request.original_content,
            document_id=document_id
        )
        
        return {
            "document_id": document_id,
            "validation": validation,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] Validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/orchestrate/runs/{orchestration_id}")
async def get_orchestration_status(orchestration_id: str):
    """Get status of an orchestration run"""
    try:
        if orchestration_id not in orchestration_status:
            raise HTTPException(status_code=404, detail="Orchestration run not found")
        
        status_info = orchestration_status[orchestration_id].copy()
        
        # Add progress information
        if status_info["status"] == OrchestrationStatus.RUNNING.value:
            current_step = status_info.get("current_step")
            if current_step == "analysis":
                status_info["message"] = "Performing multi-agent analysis"
            elif current_step == "consensus":
                status_info["message"] = "Validating findings through multi-model consensus"
                status_info["steps_completed"] = ["analysis"]
            elif current_step == "remediation":
                status_info["message"] = "Generating remediated document"
                status_info["steps_completed"] = ["analysis", "consensus"]
            elif current_step == "validation":
                status_info["message"] = "Performing quality validation"
                status_info["steps_completed"] = ["analysis", "consensus", "remediation"]
            else:
                status_info["message"] = "Orchestration in progress"
        
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get orchestration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/compress-folder", response_model=FolderCompressionResponse)
async def compress_folder(request: FolderCompressionRequest, background_tasks: BackgroundTasks):
    """Compress a folder into a zip file using DSL workflow"""
    request_id = generate_request_id()
    start_time = datetime.now()
    
    logger.info(f"[{request_id}] Folder compression requested: {request.folder_path}")
    
    try:
        # Validate folder path
        folder_path = Path(request.folder_path)
        if not folder_path.exists():
            raise HTTPException(status_code=404, detail=f"Folder not found: {request.folder_path}")
        
        if not folder_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {request.folder_path}")
        
        # Generate output filename if not provided
        output_filename = (
            request.output_name
            or request.output_filename
            or f"{folder_path.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )
        
        if request.use_dsl:
            # Execute via DSL workflow
            logger.info(f"[{request_id}] Executing compression via DSL workflow")
            
            # Create a temporary document to track this operation
            temp_document = Document(
                id=f"compress_{request_id}",
                filename=f"compression_{folder_path.name}",
                text=f"Compress folder: {request.folder_path}",
                metadata={
                    "operation_type": "folder_compression",
                    "folder_path": str(folder_path),
                    "output_filename": output_filename,
                    "include_patterns": request.include_patterns,
                    "exclude_patterns": request.exclude_patterns,
                    "compression_level": request.compression_level
                }
            )
            
            # Execute compression workflow
            workflow_params = {
                "folder_path": str(folder_path),
                "output_filename": output_filename,
                "include_patterns": request.include_patterns or [],
                "exclude_patterns": request.exclude_patterns or [],
                "compression_level": request.compression_level,
                "document_id": temp_document.id
            }
            
            run = await workflow_engine.execute_workflow(
                workflow_name="folder_compression",
                document_id=temp_document.id,
                initial_parameters=workflow_params
            )
            
            if run.status == WorkflowStatus.SUCCESS:
                compression_result = run.outputs.get('compress_folder', {})
                
                return FolderCompressionResponse(
                    success=True,
                    output_path=compression_result.get('output_path'),
                    archive_path=compression_result.get('output_path'),
                    files_compressed=compression_result.get('files_compressed'),
                    files_included=compression_result.get('files_compressed'),
                    original_size_bytes=compression_result.get('original_size_bytes'),
                    compressed_size_bytes=compression_result.get('compressed_size_bytes'),
                    compression_ratio=compression_result.get('compression_ratio'),
                    duration_seconds=compression_result.get('duration_seconds'),
                    workflow_run_id=run.run_id
                )
            else:
                return FolderCompressionResponse(
                    success=False,
                    error=run.error or "Workflow execution failed",
                    workflow_run_id=run.run_id
                )
        else:
            # Direct execution using file operations
            logger.info(f"[{request_id}] Executing compression directly")
            
            output_path = str(folder_path.parent / output_filename)
            
            result = await FileOperations.compress_folder(
                folder_path=str(folder_path),
                output_path=output_path,
                include_patterns=request.include_patterns,
                exclude_patterns=request.exclude_patterns,
                compression_level=request.compression_level
            )
            
            return FolderCompressionResponse(
                success=result['success'],
                output_path=result.get('output_path'),
                archive_path=result.get('output_path'),
                files_compressed=result.get('files_compressed'),
                files_included=result.get('files_compressed'),
                original_size_bytes=result.get('original_size_bytes'),
                compressed_size_bytes=result.get('compressed_size_bytes'),
                compression_ratio=result.get('compression_ratio'),
                duration_seconds=result.get('duration_seconds'),
                error=result.get('error')
            )
        
    except HTTPException:
        raise
    except Exception as e:
        total_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Folder compression failed after {total_time:.2f}s: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/convert/docx-to-pdf", response_model=DocumentConversionResponse)
async def convert_docx_to_pdf(
    request: Optional[DocumentConversionRequest] = Body(default=None),
    file: UploadFile = File(None)
):
    """Convert DOCX document to PDF using DSL workflow"""
    request_id = generate_request_id()
    start_time = datetime.now()
    
    logger.info(f"[{request_id}] DOCX to PDF conversion requested")
    
    try:
        input_path = None
        temp_file_path: Optional[str] = None
        original_filename: Optional[str] = None
        
        request_payload = request.dict() if request else {}
        
        if file:
            original_filename = file.filename or "uploaded_document.docx"
            suffix = Path(original_filename).suffix or ".docx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                file_contents = await file.read()
                tmp_file.write(file_contents)
                temp_file_path = tmp_file.name
            request_payload["input_path"] = temp_file_path
            request_payload.setdefault("output_path", str(Path(temp_file_path).with_suffix('.pdf')))
            logger.info(f"[{request_id}] Received upload for conversion: {original_filename} -> {request_payload['output_path']}")
        
        conversion_request = DocumentConversionRequest(**request_payload)
        
        # Determine input path
        if conversion_request.document_id:
            # Get document from ingester
            document = document_ingester.get_document(conversion_request.document_id)
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # For this example, assume document has a file_path in metadata
            input_path = document.metadata.get('file_path') if document.metadata else None
            if not input_path:
                raise HTTPException(status_code=400, detail="Document does not have associated file path")
        
        elif conversion_request.input_path:
            input_path = conversion_request.input_path
        else:
            raise HTTPException(status_code=400, detail="Either document_id, input_path, or file upload must be provided")
        
        # Validate input file
        input_file = Path(input_path)
        if not input_file.exists():
            raise HTTPException(status_code=404, detail=f"Input file not found: {input_path}")
        
        if input_file.suffix.lower() not in ['.docx', '.doc']:
            raise HTTPException(status_code=400, detail="Input file must be a Word document (.docx or .doc)")
        
        # Determine output path
        output_format = conversion_request.target_format or conversion_request.output_format or "pdf"
        output_path = conversion_request.output_path or str(input_file.with_suffix(f".{output_format}"))
        
        if conversion_request.use_dsl:
            # Execute via DSL workflow
            logger.info(f"[{request_id}] Executing conversion via DSL workflow")
            
            # Create a temporary document to track this operation
            temp_document = Document(
                id=f"convert_{request_id}",
                filename=f"conversion_{input_file.name}",
                text=f"Convert document: {input_path}",
                metadata={
                    "operation_type": "document_conversion",
                    "input_path": input_path,
                    "output_path": output_path,
                    "output_format": output_format,
                    "quality": conversion_request.quality,
                    "preserve_formatting": conversion_request.preserve_formatting
                }
            )
            
            # Execute conversion workflow
            workflow_params = {
                "input_path": input_path,
                "output_path": output_path,
                "output_format": output_format,
                "quality": conversion_request.quality,
                "preserve_formatting": conversion_request.preserve_formatting,
                "document_id": temp_document.id
            }
            
            run = await workflow_engine.execute_workflow(
                workflow_name="document_conversion",
                document_id=temp_document.id,
                initial_parameters=workflow_params
            )
            
            if run.status == WorkflowStatus.SUCCESS:
                conversion_result = run.outputs.get('convert_document', {})
                
                return DocumentConversionResponse(
                    success=True,
                    output_path=conversion_result.get('output_path'),
                    archive_path=conversion_result.get('output_path'),
                    conversion_method="dsl_workflow",
                    original_file=original_filename or str(input_file),
                    file_size_bytes=input_file.stat().st_size if input_file.exists() else None,
                    conversion_time_seconds=(datetime.now() - start_time).total_seconds(),
                    workflow_run_id=run.run_id
                )
            else:
                return DocumentConversionResponse(
                    success=False,
                    error=run.error or "Workflow execution failed",
                    workflow_run_id=run.run_id
                )
        else:
            # Direct execution using file operations
            logger.info(f"[{request_id}] Executing conversion directly")
            
            result = await FileOperations.convert_docx_to_pdf(
                input_path=input_path,
                output_path=output_path,
                quality=conversion_request.quality,
                preserve_formatting=conversion_request.preserve_formatting,
                use_claude=False  # Direct mode doesn't use Claude
            )
            
            return DocumentConversionResponse(
                success=result['success'],
                output_path=result.get('output_path'),
                archive_path=result.get('output_path'),
                conversion_method=result.get('method'),
                original_file=original_filename or str(input_file),
                file_size_bytes=input_file.stat().st_size if input_file.exists() else None,
                conversion_time_seconds=result.get('duration_seconds'),
                error=result.get('error')
            )
        
    except HTTPException:
        raise
    except Exception as e:
        total_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Document conversion failed after {total_time:.2f}s: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if file and temp_file_path and Path(temp_file_path).exists():
            try:
                Path(temp_file_path).unlink()
            except Exception:
                logger.debug(f"[{request_id}] Failed to remove temporary file {temp_file_path}")

@app.post("/documents/convert/batch")
async def batch_convert_documents(request: BatchConversionRequest, background_tasks: BackgroundTasks):
    """Batch convert multiple documents"""
    request_id = generate_request_id()
    start_time = datetime.now()
    
    input_files: List[str] = list(request.input_files or [])
    
    if request.document_ids:
        for document_id in request.document_ids:
            document = document_ingester.get_document(document_id)
            if not document:
                raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
            file_path = (document.metadata or {}).get('file_path')
            if not file_path:
                raise HTTPException(status_code=400, detail=f"Document {document_id} has no associated file path")
            input_files.append(file_path)
    
    if not input_files:
        raise HTTPException(status_code=400, detail="No input files provided for batch conversion")
    
    logger.info(f"[{request_id}] Batch conversion requested: {len(input_files)} files")
    
    try:
        # Validate input files exist
        for file_path in input_files:
            if not Path(file_path).exists():
                raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        
        # Validate output directory
        output_dir = Path(request.output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if request.use_dsl:
            # Execute batch conversion in background via DSL
            logger.info(f"[{request_id}] Queuing batch conversion via DSL workflow")
            
            async def execute_batch_workflow():
                bg_request_id = f"{request_id}-batch"
                logger.info(f"[{bg_request_id}] Starting batch workflow execution")
                
                try:
                    # Create temporary document for batch operation
                    temp_document = Document(
                        id=f"batch_{request_id}",
                        filename=f"batch_conversion_{len(input_files)}_files",
                        text=f"Batch convert {len(input_files)} files",
                        metadata={
                            "operation_type": "batch_conversion",
                            "input_files": input_files,
                            "output_directory": str(output_dir),
                            "conversion_type": request.conversion_type,
                            "parallel": request.parallel,
                            "max_workers": request.max_workers
                        }
                    )
                    
                    # Execute batch conversion workflow
                    workflow_params = {
                        "input_files": input_files,
                        "output_directory": str(output_dir),
                        "conversion_type": request.conversion_type,
                        "parallel": request.parallel,
                        "max_workers": request.max_workers,
                        "document_id": temp_document.id
                    }
                    
                    run = await workflow_engine.execute_workflow(
                        workflow_name="batch_document_conversion",
                        document_id=temp_document.id,
                        initial_parameters=workflow_params
                    )
                    
                    logger.info(f"[{bg_request_id}] Batch workflow completed: {run.status.value}")
                    
                except Exception as e:
                    logger.error(f"[{bg_request_id}] Batch workflow failed: {e}")
            
            background_tasks.add_task(execute_batch_workflow)
            
            return {
                "message": "Batch conversion queued for processing",
                "request_id": request_id,
                "files_queued": len(input_files),
                "output_directory": str(output_dir),
                "processing_mode": "dsl_workflow"
            }
        else:
            # Direct batch conversion
            result = await FileOperations.batch_convert_documents(
                input_files=input_files,
                output_dir=str(output_dir),
                conversion_type=request.conversion_type,
                parallel=request.parallel,
                max_workers=request.max_workers
            )
            
            return {
                "success": result['success'],
                "total_files": result['total_files'],
                "successful_conversions": result['successful_conversions'],
                "failed_conversions": result['failed_conversions'],
                "output_directory": result['output_directory'],
                "duration_seconds": result['duration_seconds'],
                "processing_mode": "direct"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        total_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"[{request_id}] Batch conversion failed after {total_time:.2f}s: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint with component metadata as described in README"""
    try:
        documents = document_ingester.list_documents()
    except Exception:
        documents = []

    total_workflows = len(workflow_engine.workflows)
    runs = workflow_engine.list_runs()
    active_runs = [run for run in runs if run.status == WorkflowStatus.RUNNING]

    # Lazy import to avoid circular dependencies at module load
    from agent_providers import agent_registry, AgentCapability  # type: ignore

    available_agents = [provider["name"] for provider in agent_registry.list_providers()]
    capabilities = sorted({cap for provider in agent_registry.list_providers() for cap in provider["capabilities"]})

    claude_components = {
        "status": "operational",
        "dsl_loaded": bool(getattr(claude_service, "dsl_config", {})),
        "agent_mappings_loaded": bool(getattr(claude_service, "agent_mappings", {})),
        "default_timeout_seconds": getattr(claude_service.cli, "timeout", None)
    }

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "api": {"status": "operational"},
            "ingester": {
                "status": "operational",
                "stored_documents": len(documents)
            },
            "extractor": {"status": "operational"},
            "workflow_engine": {
                "status": "operational",
                "workflows_loaded": total_workflows,
                "active_runs": len(active_runs)
            },
            "claude_service": claude_components,
            "agent_registry": {
                "status": "operational",
                "registered_agents": available_agents,
                "capabilities": capabilities
            },
            "mcp_servers": {
                "status": "operational",
                "available": [member.value for member in SuperClaudeMCP],
                "active": []  # Real-time active MCP tracking not yet implemented
            }
        }
    }

# Run the API
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8001"))  # Configurable port
    print(f"Starting DocAutomate API on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
