#!/usr/bin/env python3
"""
Document Ingester Module
Handles various document formats (PDF, images, text) and prepares them for processing
"""

import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import queue

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Document:
    """Represents an ingested document"""
    id: str
    filename: str
    content_type: str
    text: str
    metadata: Dict[str, Any]
    ingested_at: str
    status: str = "pending"
    extracted_actions: Optional[List[Dict]] = None
    workflow_runs: Optional[List[str]] = None

class DocumentIngester:
    """
    Handles document ingestion from various sources
    Leverages Claude's Read tool for PDF and image processing
    """
    
    def __init__(self, storage_dir: str = "./storage", max_workers: int = 4):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Job queue for async processing
        self.job_queue = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Supported formats
        self.supported_formats = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
    
    def generate_document_id(self, content: str) -> str:
        """Generate unique document ID based on content hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def ingest_file(self, file_path: str) -> Document:
        """
        Ingest a single document file
        Uses Claude's Read tool for PDF/image processing
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Check if format is supported
        file_ext = path.suffix.lower()
        if file_ext not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        # Extract text based on file type
        try:
            # For this implementation, we'll simulate Claude's Read tool
            # In production, this would call the actual Claude Read API
            text = await self._extract_text(path)
            
            # Create document object
            doc = Document(
                id=self.generate_document_id(text),
                filename=path.name,
                content_type=self.supported_formats[file_ext],
                text=text,
                metadata={
                    'size_bytes': path.stat().st_size,
                    'file_path': str(path.absolute()),
                    'extension': file_ext
                },
                ingested_at=datetime.utcnow().isoformat(),
                workflow_runs=[]
            )
            
            # Store document
            await self._store_document(doc)
            
            # Queue for processing
            self.job_queue.put(doc.id)
            
            logger.info(f"Document ingested: {doc.id} ({doc.filename})")
            return doc
            
        except Exception as e:
            logger.error(f"Failed to ingest {file_path}: {str(e)}")
            raise
    
    async def _extract_text(self, file_path: Path) -> str:
        """
        Extract text from document
        In production, this would use Claude's Read tool
        """
        # Simplified implementation for demo
        if file_path.suffix in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # Simulate extraction for other formats
            # In reality, would use: claude_read_tool(file_path)
            return f"[Extracted text from {file_path.name}]\\n\\nThis is where the actual document content would appear after processing with Claude's Read tool."
    
    async def _store_document(self, doc: Document):
        """Store document metadata and content"""
        doc_dir = self.storage_dir / doc.id
        doc_dir.mkdir(exist_ok=True)
        
        # Store metadata
        metadata_file = doc_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(asdict(doc), f, indent=2)
        
        # Store raw text
        text_file = doc_dir / "content.txt"
        with open(text_file, 'w') as f:
            f.write(doc.text)
    
    async def ingest_directory(self, dir_path: str, recursive: bool = True) -> List[Document]:
        """Ingest all supported documents in a directory"""
        documents = []
        path = Path(dir_path)
        
        if not path.is_dir():
            raise ValueError(f"Not a directory: {dir_path}")
        
        pattern = "**/*" if recursive else "*"
        
        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                try:
                    doc = await self.ingest_file(str(file_path))
                    documents.append(doc)
                except Exception as e:
                    logger.error(f"Failed to ingest {file_path}: {e}")
        
        return documents
    
    def get_document(self, doc_id: str) -> Optional[Document]:
        """Retrieve document by ID"""
        doc_dir = self.storage_dir / doc_id
        metadata_file = doc_dir / "metadata.json"
        
        if not metadata_file.exists():
            return None
        
        with open(metadata_file, 'r') as f:
            data = json.load(f)
            return Document(**data)
    
    def list_documents(self, status: Optional[str] = None) -> List[Document]:
        """List all documents, optionally filtered by status"""
        documents = []
        
        for doc_dir in self.storage_dir.iterdir():
            if doc_dir.is_dir():
                metadata_file = doc_dir / "metadata.json"
                if metadata_file.exists():
                    doc = self.get_document(doc_dir.name)
                    if doc and (status is None or doc.status == status):
                        documents.append(doc)
        
        return documents
    
    def get_pending_jobs(self) -> List[str]:
        """Get list of document IDs pending processing"""
        pending = []
        while not self.job_queue.empty():
            try:
                doc_id = self.job_queue.get_nowait()
                pending.append(doc_id)
                # Put it back for actual processing
                self.job_queue.put(doc_id)
            except queue.Empty:
                break
        return pending

# Example usage
if __name__ == "__main__":
    async def main():
        ingester = DocumentIngester()
        
        # Example: Ingest a single file
        # doc = await ingester.ingest_file("/path/to/document.pdf")
        # print(f"Ingested: {doc.id}")
        
        # Example: Ingest directory
        # docs = await ingester.ingest_directory("/path/to/documents")
        # print(f"Ingested {len(docs)} documents")
        
        print("Document Ingester initialized")
        print(f"Storage directory: {ingester.storage_dir}")
        print(f"Supported formats: {list(ingester.supported_formats.keys())}")
    
    asyncio.run(main())