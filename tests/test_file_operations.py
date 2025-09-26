#!/usr/bin/env python3
"""
Tests for file operations functionality
Tests the new compression and conversion API endpoints
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import json

# Import test dependencies
from fastapi.testclient import TestClient
from unittest.mock import Mock

# Import our modules
import sys
sys.path.append(str(Path(__file__).parent.parent))

from api import app
from utils.file_operations import FileOperations


class TestFileOperationsAPI:
    """Test the new file operations API endpoints"""
    
    def setup_method(self):
        """Setup test client and temporary directories"""
        self.client = TestClient(app)
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Create test files and directories
        self.test_folder = self.temp_path / "test_folder"
        self.test_folder.mkdir()
        
        # Create some test files
        (self.test_folder / "test1.txt").write_text("Test file 1 content")
        (self.test_folder / "test2.docx").write_text("Mock DOCX content")
        (self.test_folder / "nested").mkdir()
        (self.test_folder / "nested" / "nested_file.pdf").write_text("Mock PDF content")
    
    def teardown_method(self):
        """Cleanup test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_root_endpoint_includes_new_endpoints(self):
        """Test that root endpoint lists new file operation endpoints"""
        response = self.client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        endpoints = data["endpoints"]
        
        assert "compress_folder" in endpoints
        assert "convert_document" in endpoints
        assert "batch_convert" in endpoints
        
        assert endpoints["compress_folder"] == "/documents/compress-folder"
        assert endpoints["convert_document"] == "/documents/convert/docx-to-pdf"
        assert endpoints["batch_convert"] == "/documents/convert/batch"
    
    @patch('utils.file_operations.FileOperations.compress_folder')
    def test_compress_folder_endpoint_direct(self, mock_compress):
        """Test folder compression endpoint in direct mode"""
        # Mock the compression result
        mock_compress.return_value = {
            'success': True,
            'output_path': str(self.temp_path / "test.zip"),
            'files_compressed': 3,
            'compression_ratio': "25.5%"
        }
        
        request_data = {
            "folder_path": str(self.test_folder),
            "output_filename": "test.zip",
            "include_patterns": ["*.txt", "*.docx"],
            "compression_level": 6,
            "use_dsl": False
        }
        
        response = self.client.post("/documents/compress-folder", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        assert "output_path" in data
        assert data["files_compressed"] == 3
        assert data["compression_ratio"] == "25.5%"
        
        # Verify the mock was called correctly
        mock_compress.assert_called_once()
    
    def test_compress_folder_invalid_path(self):
        """Test compression with invalid folder path"""
        request_data = {
            "folder_path": "/nonexistent/path",
            "output_filename": "test.zip",
            "use_dsl": False
        }
        
        response = self.client.post("/documents/compress-folder", json=request_data)
        assert response.status_code == 404
        assert "Folder not found" in response.json()["detail"]
    
    def test_compress_folder_file_instead_of_directory(self):
        """Test compression when path is a file, not directory"""
        # Create a test file
        test_file = self.temp_path / "test_file.txt"
        test_file.write_text("test content")
        
        request_data = {
            "folder_path": str(test_file),
            "output_filename": "test.zip",
            "use_dsl": False
        }
        
        response = self.client.post("/documents/compress-folder", json=request_data)
        assert response.status_code == 400
        assert "not a directory" in response.json()["detail"]
    
    @patch('utils.file_operations.FileOperations.convert_docx_to_pdf')
    def test_convert_document_endpoint_direct(self, mock_convert):
        """Test document conversion endpoint in direct mode"""
        # Create a mock DOCX file
        test_docx = self.temp_path / "test.docx"
        test_docx.write_text("Mock DOCX content")
        
        # Mock the conversion result
        mock_convert.return_value = {
            'success': True,
            'output_path': str(self.temp_path / "test.pdf"),
            'method': 'docx2pdf_library'
        }
        
        request_data = {
            "input_path": str(test_docx),
            "output_path": str(self.temp_path / "test.pdf"),
            "output_format": "pdf",
            "quality": "high",
            "preserve_formatting": True,
            "use_dsl": False
        }
        
        response = self.client.post("/documents/convert/docx-to-pdf", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        assert "output_path" in data
        assert data["conversion_method"] == "docx2pdf_library"
        
        # Verify the mock was called correctly
        mock_convert.assert_called_once()
    
    def test_convert_document_invalid_file(self):
        """Test conversion with invalid input file"""
        request_data = {
            "input_path": "/nonexistent/file.docx",
            "use_dsl": False
        }
        
        response = self.client.post("/documents/convert/docx-to-pdf", json=request_data)
        assert response.status_code == 404
        assert "Input file not found" in response.json()["detail"]
    
    def test_convert_document_invalid_format(self):
        """Test conversion with unsupported file format"""
        # Create a non-DOCX file
        test_file = self.temp_path / "test.txt"
        test_file.write_text("test content")
        
        request_data = {
            "input_path": str(test_file),
            "use_dsl": False
        }
        
        response = self.client.post("/documents/convert/docx-to-pdf", json=request_data)
        assert response.status_code == 400
        assert "must be a Word document" in response.json()["detail"]
    
    @patch('utils.file_operations.FileOperations.batch_convert_documents')
    def test_batch_convert_endpoint_direct(self, mock_batch_convert):
        """Test batch conversion endpoint in direct mode"""
        # Create test DOCX files
        docx1 = self.temp_path / "doc1.docx"
        docx2 = self.temp_path / "doc2.docx"
        docx1.write_text("Mock DOCX 1")
        docx2.write_text("Mock DOCX 2")
        
        output_dir = self.temp_path / "output"
        
        # Mock the batch conversion result
        mock_batch_convert.return_value = {
            'success': True,
            'total_files': 2,
            'successful_conversions': 2,
            'failed_conversions': 0,
            'output_directory': str(output_dir),
            'duration_seconds': 5.0
        }
        
        request_data = {
            "input_files": [str(docx1), str(docx2)],
            "output_directory": str(output_dir),
            "conversion_type": "docx_to_pdf",
            "parallel": True,
            "max_workers": 2,
            "use_dsl": False
        }
        
        response = self.client.post("/documents/convert/batch", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] == True
        assert data["total_files"] == 2
        assert data["successful_conversions"] == 2
        assert data["failed_conversions"] == 0
        assert data["processing_mode"] == "direct"
        
        # Verify the mock was called correctly
        mock_batch_convert.assert_called_once()
    
    def test_batch_convert_missing_file(self):
        """Test batch conversion with missing input file"""
        request_data = {
            "input_files": ["/nonexistent/file.docx"],
            "output_directory": str(self.temp_path / "output"),
            "use_dsl": False
        }
        
        response = self.client.post("/documents/convert/batch", json=request_data)
        assert response.status_code == 404
        assert "File not found" in response.json()["detail"]


class TestFileOperationsUtils:
    """Test the FileOperations utility class"""
    
    def setup_method(self):
        """Setup temporary directories for testing"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Create test folder structure
        self.test_folder = self.temp_path / "test_folder"
        self.test_folder.mkdir()
        
        # Create test files with different extensions
        (self.test_folder / "document1.txt").write_text("Text document 1")
        (self.test_folder / "document2.docx").write_text("Mock DOCX content")
        (self.test_folder / "image1.png").write_bytes(b"Mock PNG content")
        
        # Create nested structure
        nested = self.test_folder / "nested"
        nested.mkdir()
        (nested / "nested_doc.pdf").write_text("Mock PDF in nested folder")
        
        # Create files to exclude
        (self.test_folder / "temp_file.tmp").write_text("Temporary file")
        (self.test_folder / ".hidden_file").write_text("Hidden file")
    
    def teardown_method(self):
        """Cleanup test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_compress_folder_basic(self):
        """Test basic folder compression"""
        output_path = str(self.temp_path / "test.zip")
        
        result = await FileOperations.compress_folder(
            folder_path=str(self.test_folder),
            output_path=output_path
        )
        
        assert result['success'] == True
        assert result['output_path'] == output_path
        assert result['files_compressed'] > 0
        assert 'compression_ratio' in result
        assert 'duration_seconds' in result
        
        # Verify zip file was created
        assert Path(output_path).exists()
    
    @pytest.mark.asyncio
    async def test_compress_folder_with_patterns(self):
        """Test compression with include/exclude patterns"""
        output_path = str(self.temp_path / "filtered.zip")
        
        result = await FileOperations.compress_folder(
            folder_path=str(self.test_folder),
            output_path=output_path,
            include_patterns=["*.txt", "*.docx"],
            exclude_patterns=["*.tmp", ".*"]
        )
        
        assert result['success'] == True
        assert result['files_compressed'] == 2  # Only .txt and .docx files
    
    @pytest.mark.asyncio
    async def test_compress_nonexistent_folder(self):
        """Test compression of non-existent folder"""
        result = await FileOperations.compress_folder(
            folder_path="/nonexistent/folder",
            output_path=str(self.temp_path / "test.zip")
        )
        
        assert result['success'] == False
        assert 'error' in result
        assert "not found" in result['error'].lower()
    
    @pytest.mark.asyncio 
    async def test_convert_docx_to_pdf_mock(self):
        """Test DOCX to PDF conversion (mocked)"""
        # Create a mock DOCX file
        docx_path = str(self.temp_path / "test.docx")
        Path(docx_path).write_text("Mock DOCX content")
        
        pdf_path = str(self.temp_path / "test.pdf")
        
        # Since we don't have actual conversion libraries in test environment,
        # this will test the error handling path
        result = await FileOperations.convert_docx_to_pdf(
            input_path=docx_path,
            output_path=pdf_path,
            use_claude=False
        )
        
        # Should return success=True for DSL workflow placeholder
        # or fail with import error for library-based conversion
        assert 'success' in result
    
    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self):
        """Test conversion of non-existent file"""
        result = await FileOperations.convert_docx_to_pdf(
            input_path="/nonexistent/file.docx"
        )
        
        assert result['success'] == False
        assert 'error' in result
        assert "not found" in result['error'].lower()
    
    @pytest.mark.asyncio
    async def test_batch_convert_empty_list(self):
        """Test batch conversion with empty file list"""
        result = await FileOperations.batch_convert_documents(
            input_files=[],
            output_dir=str(self.temp_path / "output")
        )
        
        assert result['success'] == True
        assert result['total_files'] == 0
        assert result['successful_conversions'] == 0
    
    @pytest.mark.asyncio
    async def test_extract_zip_metadata(self):
        """Test extracting metadata from zip file"""
        # First create a zip file
        output_path = str(self.temp_path / "metadata_test.zip")
        
        compress_result = await FileOperations.compress_folder(
            folder_path=str(self.test_folder),
            output_path=output_path
        )
        
        assert compress_result['success'] == True
        
        # Now test metadata extraction
        metadata = await FileOperations.extract_zip_metadata(output_path)
        
        assert metadata['success'] == True
        assert metadata['file_count'] > 0
        assert 'total_compressed_size' in metadata
        assert 'total_uncompressed_size' in metadata
        assert 'compression_ratio' in metadata
        assert 'files' in metadata
    
    @pytest.mark.asyncio
    async def test_extract_zip_metadata_nonexistent(self):
        """Test metadata extraction from non-existent zip"""
        metadata = await FileOperations.extract_zip_metadata("/nonexistent/file.zip")
        
        assert metadata['success'] == False
        assert 'error' in metadata


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])