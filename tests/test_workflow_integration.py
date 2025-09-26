#!/usr/bin/env python3
"""
Integration tests for new workflow functionality
Tests the workflow engine with new file operation actions
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Import test dependencies
import sys
sys.path.append(str(Path(__file__).parent.parent))

from workflow import WorkflowEngine, WorkflowStatus
from utils.file_operations import FileOperations


class TestWorkflowIntegration:
    """Test workflow engine integration with new file operations"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Create test workflow directory
        self.workflow_dir = self.temp_path / "workflows"
        self.workflow_dir.mkdir()
        
        # Create test state directory
        self.state_dir = self.temp_path / "state"
        self.state_dir.mkdir()
        
        # Initialize workflow engine with test directories
        self.engine = WorkflowEngine(
            workflows_dir=str(self.workflow_dir),
            state_dir=str(self.state_dir)
        )
        
        # Create test folder structure
        self.test_folder = self.temp_path / "test_data"
        self.test_folder.mkdir()
        (self.test_folder / "test1.txt").write_text("Test file 1")
        (self.test_folder / "test2.docx").write_text("Mock DOCX content")
    
    def teardown_method(self):
        """Cleanup test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_action_registry_includes_new_actions(self):
        """Test that new action handlers are registered"""
        registry = self.engine.action_registry
        
        assert 'compress_folder' in registry
        assert 'convert_document' in registry
        assert 'batch_convert' in registry
        
        # Verify they are callable
        assert callable(registry['compress_folder'])
        assert callable(registry['convert_document']) 
        assert callable(registry['batch_convert'])
    
    @patch('utils.file_operations.FileOperations.compress_folder')
    @pytest.mark.asyncio
    async def test_compress_folder_action(self, mock_compress):
        """Test the compress_folder workflow action"""
        # Mock the compression result
        mock_compress.return_value = {
            'success': True,
            'output_path': str(self.temp_path / "test.zip"),
            'files_compressed': 2,
            'compression_ratio': "30.5%"
        }
        
        config = {
            'folder_path': str(self.test_folder),
            'output_filename': 'test.zip',
            'include_patterns': ['*.txt'],
            'compression_level': 6
        }
        
        state = {}
        
        result = await self.engine._execute_compress_folder(config, state)
        
        assert result['success'] == True
        assert result['output_path'] == str(self.temp_path / "test.zip")
        assert result['files_compressed'] == 2
        
        # Verify mock was called with correct parameters
        mock_compress.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_compress_folder_action_missing_params(self):
        """Test compress_folder action with missing parameters"""
        config = {}  # Missing required parameters
        state = {}
        
        result = await self.engine._execute_compress_folder(config, state)
        
        assert result['success'] == False
        assert 'error' in result
        assert 'folder_path is required' in result['error']
    
    @patch('utils.file_operations.FileOperations.convert_docx_to_pdf')
    @pytest.mark.asyncio
    async def test_convert_document_action(self, mock_convert):
        """Test the convert_document workflow action"""
        # Create a test DOCX file
        test_docx = self.test_folder / "test.docx"
        test_docx.write_text("Mock DOCX content")
        
        # Mock the conversion result
        mock_convert.return_value = {
            'success': True,
            'output_path': str(self.test_folder / "test.pdf"),
            'method': 'claude_intelligent'
        }
        
        config = {
            'input_path': str(test_docx),
            'output_format': 'pdf',
            'quality': 'high',
            'preserve_formatting': True
        }
        
        state = {}
        
        result = await self.engine._execute_convert_document(config, state)
        
        assert result['success'] == True
        assert result['output_path'] == str(self.test_folder / "test.pdf")
        assert result['method'] == 'claude_intelligent'
        
        # Verify mock was called with correct parameters
        mock_convert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_convert_document_action_nonexistent_file(self):
        """Test convert_document action with non-existent input file"""
        config = {
            'input_path': '/nonexistent/file.docx'
        }
        state = {}
        
        result = await self.engine._execute_convert_document(config, state)
        
        assert result['success'] == False
        assert 'error' in result
        assert 'does not exist' in result['error']
    
    @patch('utils.file_operations.FileOperations.batch_convert_documents')
    @pytest.mark.asyncio
    async def test_batch_convert_action(self, mock_batch):
        """Test the batch_convert workflow action"""
        # Create test files
        docx1 = self.test_folder / "doc1.docx"
        docx2 = self.test_folder / "doc2.docx"
        docx1.write_text("Mock DOCX 1")
        docx2.write_text("Mock DOCX 2")
        
        output_dir = self.temp_path / "output"
        
        # Mock the batch conversion result
        mock_batch.return_value = {
            'success': True,
            'total_files': 2,
            'successful_conversions': 2,
            'failed_conversions': 0
        }
        
        config = {
            'input_files': [str(docx1), str(docx2)],
            'output_directory': str(output_dir),
            'conversion_type': 'docx_to_pdf',
            'parallel': True,
            'max_workers': 2
        }
        
        state = {}
        
        result = await self.engine._execute_batch_convert(config, state)
        
        assert result['success'] == True
        assert result['total_files'] == 2
        assert result['successful_conversions'] == 2
        
        # Verify mock was called with correct parameters
        mock_batch.assert_called_once()
    
    def test_workflow_loading_new_workflows(self):
        """Test that new workflow YAML files are loaded correctly"""
        # Create a simple test workflow
        test_workflow = {
            'name': 'test_compression',
            'description': 'Test compression workflow',
            'parameters': [
                {'name': 'folder_path', 'type': 'string', 'required': True}
            ],
            'steps': [
                {
                    'id': 'compress',
                    'type': 'compress_folder',
                    'config': {
                        'folder_path': '{{ folder_path }}',
                        'output_filename': 'test.zip'
                    }
                }
            ]
        }
        
        # Write workflow to file
        import yaml
        workflow_file = self.workflow_dir / "test_compression.yaml"
        with open(workflow_file, 'w') as f:
            yaml.dump(test_workflow, f)
        
        # Reload workflows
        new_engine = WorkflowEngine(
            workflows_dir=str(self.workflow_dir),
            state_dir=str(self.state_dir)
        )
        
        assert 'test_compression' in new_engine.workflows
        assert new_engine.workflows['test_compression']['name'] == 'test_compression'
    
    @patch('utils.file_operations.FileOperations.compress_folder')
    @pytest.mark.asyncio
    async def test_end_to_end_compression_workflow(self, mock_compress):
        """Test end-to-end execution of compression workflow"""
        # Mock the compression result
        mock_compress.return_value = {
            'success': True,
            'output_path': str(self.temp_path / "end_to_end.zip"),
            'files_compressed': 2,
            'compression_ratio': "35.0%"
        }
        
        # Create a simple compression workflow
        workflow_def = {
            'name': 'simple_compress',
            'description': 'Simple compression test',
            'parameters': [
                {'name': 'folder_path', 'type': 'string', 'required': True},
                {'name': 'output_filename', 'type': 'string', 'required': True}
            ],
            'steps': [
                {
                    'id': 'compress_step',
                    'type': 'compress_folder',
                    'config': {
                        'folder_path': '{{ folder_path }}',
                        'output_filename': '{{ output_filename }}',
                        'compression_level': 6
                    }
                }
            ]
        }
        
        # Add workflow to engine
        self.engine.workflows['simple_compress'] = workflow_def
        
        # Execute workflow
        parameters = {
            'folder_path': str(self.test_folder),
            'output_filename': 'end_to_end.zip'
        }
        
        run = await self.engine.execute_workflow(
            workflow_name='simple_compress',
            document_id='test_doc_123',
            initial_parameters=parameters
        )
        
        assert run.status == WorkflowStatus.SUCCESS
        assert 'compress_step' in run.outputs
        assert run.outputs['compress_step']['success'] == True
        
        # Verify compression was called
        mock_compress.assert_called_once()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])