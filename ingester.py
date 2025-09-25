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
    error: Optional[str] = None

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
    
    def _validate_extracted_text(self, text: str, file_path: Path) -> bool:
        """
        Validate that extracted text is valid content and not a permission error
        
        Args:
            text: Extracted text to validate
            file_path: Path to the original file
            
        Returns:
            True if text appears to be valid content, False if it's an error message
        """
        if not text or len(text) < 50:
            logger.warning(f"Extracted text too short ({len(text)} chars) for {file_path.name}")
            return False
        
        # Check for known error patterns
        error_phrases = [
            'i need your permission',
            'please grant permission',
            'permission to read',
            'allow access',
            'grant access',
            'claude code is required',
            '[document:',
            'please ensure claude code'
        ]
        
        text_lower = text.lower()
        for phrase in error_phrases:
            if phrase in text_lower:
                logger.warning(f"Extracted text contains error phrase: '{phrase}' for {file_path.name}")
                return False
        
        return True
    
    async def _extract_text(self, file_path: Path, max_retries: int = 3) -> str:
        """
        Extract text from document with validation and retry logic
        
        Args:
            file_path: Path to the document file
            max_retries: Maximum number of extraction attempts
            
        Returns:
            Extracted text content
            
        Raises:
            Exception if all extraction attempts fail
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Try to use Claude Code for all document types
                from claude_cli import AsyncClaudeCLI
                cli = AsyncClaudeCLI()
                
                logger.info(f"Extraction attempt {attempt + 1}/{max_retries} for: {file_path}")
                text = await cli.read_document_async(str(file_path))
                
                # Validate the extracted text
                if self._validate_extracted_text(text, file_path):
                    logger.info(f"Successfully extracted and validated {len(text)} characters from {file_path.name}")
                    return text
                else:
                    logger.warning(f"Attempt {attempt + 1} produced invalid text for {file_path.name}")
                    if attempt < max_retries - 1:
                        # Wait before retry with exponential backoff
                        await asyncio.sleep(2 ** attempt)
                    
            except (ImportError, FileNotFoundError) as e:
                # Fallback if Claude Code is not available
                logger.warning(f"Claude Code not available on attempt {attempt + 1}: {e}")
                
                if file_path.suffix in ['.txt', '.md']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                        if self._validate_extracted_text(text, file_path):
                            return text
                else:
                    # For PDF files, try PyPDF2 directly
                    if file_path.suffix.lower() == '.pdf':
                        try:
                            import PyPDF2
                            logger.info(f"Trying direct PyPDF2 extraction for: {file_path}")
                            
                            with open(file_path, 'rb') as f:
                                pdf_reader = PyPDF2.PdfReader(f)
                                text_parts = []
                                for page in pdf_reader.pages:
                                    text_parts.append(page.extract_text())
                                text = '\n'.join(text_parts)
                                
                                if self._validate_extracted_text(text, file_path):
                                    logger.info(f"PyPDF2 successfully extracted {len(text)} characters")
                                    return text
                        except Exception as pdf_error:
                            logger.error(f"Direct PyPDF2 extraction failed: {pdf_error}")
                            last_error = pdf_error
                    
                    # If all else fails, return error message
                    if attempt == max_retries - 1:
                        error_msg = f"Failed to extract text from {file_path.name} after {max_retries} attempts"
                        logger.error(error_msg)
                        return error_msg
                        
            except Exception as e:
                logger.error(f"Extraction attempt {attempt + 1} failed: {e}")
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        # All attempts failed
        raise Exception(f"Failed to extract text from {file_path} after {max_retries} attempts: {last_error}")
    
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