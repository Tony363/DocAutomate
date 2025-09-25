#!/usr/bin/env python3
"""
Python client for DocAutomate orchestration API
Provides a clean interface for document orchestration workflows
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import aiohttp
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OrchestrationClient:
    """Client for DocAutomate orchestration API"""
    
    def __init__(self, api_url: str = "http://localhost:8001"):
        """
        Initialize orchestration client
        
        Args:
            api_url: Base URL for DocAutomate API
        """
        self.api_url = api_url.rstrip('/')
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def upload_document(self, file_path: str, auto_process: bool = True) -> str:
        """
        Upload a document to the API
        
        Args:
            file_path: Path to document file
            auto_process: Whether to auto-process the document
            
        Returns:
            Document ID
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        logger.info(f"Uploading document: {file_path}")
        
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=file_path.name)
            data.add_field('auto_process', str(auto_process).lower())
            
            async with self.session.post(
                f"{self.api_url}/documents/upload",
                data=data
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
        document_id = result.get('document_id')
        logger.info(f"Document uploaded: {document_id}")
        return document_id
    
    async def orchestrate(
        self,
        document_id: str,
        workflow_type: str = "full",
        agents: Optional[List[str]] = None,
        models: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start orchestration workflow
        
        Args:
            document_id: Document ID
            workflow_type: Type of workflow (full, analysis_only, remediation_only)
            agents: List of agents to use
            models: List of models for consensus
            config: Additional configuration
            
        Returns:
            Orchestration ID
        """
        logger.info(f"Starting orchestration for document {document_id}")
        
        payload = {
            "document_id": document_id,
            "workflow_type": workflow_type,
            "agents": agents or [
                "general-purpose",
                "technical-writer",
                "security-engineer",
                "quality-engineer",
                "requirements-analyst"
            ],
            "models": models or ["gpt-5", "claude-opus-4.1", "gpt-4.1"],
            "config": config or {}
        }
        
        async with self.session.post(
            f"{self.api_url}/orchestrate/workflow",
            json=payload
        ) as response:
            response.raise_for_status()
            result = await response.json()
        
        orchestration_id = result.get('orchestration_id')
        logger.info(f"Orchestration started: {orchestration_id}")
        return orchestration_id
    
    async def wait_for_completion(
        self,
        orchestration_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """
        Wait for orchestration to complete
        
        Args:
            orchestration_id: Orchestration ID
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
            
        Returns:
            Final orchestration status
        """
        logger.info(f"Waiting for orchestration {orchestration_id} to complete...")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            async with self.session.get(
                f"{self.api_url}/orchestrate/runs/{orchestration_id}"
            ) as response:
                response.raise_for_status()
                status = await response.json()
            
            current_status = status.get('status')
            
            if current_status == 'completed':
                logger.info("Orchestration completed successfully")
                return status
            elif current_status == 'failed':
                logger.error("Orchestration failed")
                return status
            else:
                logger.debug(f"Status: {current_status}, waiting...")
                await asyncio.sleep(poll_interval)
        
        raise TimeoutError(f"Orchestration timed out after {timeout} seconds")
    
    async def get_document_status(self, document_id: str) -> Dict[str, Any]:
        """
        Get document status including orchestration results
        
        Args:
            document_id: Document ID
            
        Returns:
            Document status and results
        """
        async with self.session.get(
            f"{self.api_url}/documents/{document_id}"
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def analyze_document(
        self,
        document_id: str,
        agents: Optional[List[str]] = None,
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Perform multi-agent analysis on document
        
        Args:
            document_id: Document ID
            agents: List of agents to use
            parallel: Whether to run agents in parallel
            
        Returns:
            Analysis results
        """
        logger.info(f"Analyzing document {document_id}")
        
        payload = {
            "document_id": document_id,
            "agents": agents,
            "parallel": parallel
        }
        
        async with self.session.post(
            f"{self.api_url}/documents/{document_id}/analyze",
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def remediate_document(
        self,
        document_id: str,
        issues: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate remediated document
        
        Args:
            document_id: Document ID
            issues: List of issues to remediate
            
        Returns:
            Remediation results
        """
        logger.info(f"Remediating document {document_id}")
        
        payload = {
            "document_id": document_id,
            "issues": issues
        }
        
        async with self.session.post(
            f"{self.api_url}/documents/{document_id}/remediate",
            json=payload
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def process_document(
        self,
        file_path: str,
        workflow_type: str = "full",
        wait: bool = True,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Complete end-to-end document processing
        
        Args:
            file_path: Path to document file
            workflow_type: Type of workflow
            wait: Whether to wait for completion
            timeout: Maximum wait time
            
        Returns:
            Processing results
        """
        # Upload document
        document_id = await self.upload_document(file_path)
        
        # Start orchestration
        orchestration_id = await self.orchestrate(document_id, workflow_type)
        
        if wait:
            # Wait for completion
            status = await self.wait_for_completion(orchestration_id, timeout)
            
            # Get final results
            document_status = await self.get_document_status(document_id)
            
            return {
                "document_id": document_id,
                "orchestration_id": orchestration_id,
                "status": status,
                "results": document_status
            }
        else:
            return {
                "document_id": document_id,
                "orchestration_id": orchestration_id,
                "status": "queued"
            }

def format_results(results: Dict[str, Any]):
    """Format results for display"""
    print("\n" + "="*60)
    print("ORCHESTRATION RESULTS")
    print("="*60)
    
    print(f"Document ID: {results.get('document_id')}")
    print(f"Orchestration ID: {results.get('orchestration_id')}")
    print(f"Status: {results['status'].get('status', 'unknown')}")
    
    if 'results' in results:
        doc_results = results['results']
        
        # Extract orchestration results if available
        if 'metadata' in doc_results and 'orchestration_results' in doc_results['metadata']:
            orch_results = doc_results['metadata']['orchestration_results']
            
            print(f"\nQuality Score: {orch_results.get('final_quality_score', 'N/A')}%")
            
            if 'steps' in orch_results:
                print("\nWorkflow Steps:")
                for step_name, step_data in orch_results['steps'].items():
                    status = step_data.get('status', 'unknown')
                    icon = "✓" if status == 'completed' else "✗" if status == 'failed' else "?"
                    print(f"  [{icon}] {step_name}: {status}")
            
            print(f"\nDuration: {orch_results.get('duration_seconds', 'N/A')} seconds")
    
    print("\n" + "="*60)

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="DocAutomate Orchestration Client"
    )
    parser.add_argument(
        "document",
        help="Path to document file"
    )
    parser.add_argument(
        "--type",
        default="full",
        choices=["full", "analysis_only", "remediation_only"],
        help="Workflow type"
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8001",
        help="API URL"
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Don't wait for completion"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds"
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        help="List of agents to use"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="List of models for consensus"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        async with OrchestrationClient(args.api) as client:
            results = await client.process_document(
                file_path=args.document,
                workflow_type=args.type,
                wait=not args.no_wait,
                timeout=args.timeout
            )
            
            if args.json:
                print(json.dumps(results, indent=2, default=str))
            else:
                format_results(results)
                
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())