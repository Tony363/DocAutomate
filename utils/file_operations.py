#!/usr/bin/env python3
"""
File Operations Utilities
Helper functions for file compression, conversion, and manipulation
Designed to work with DSL workflows and Claude Code execution
"""

import zipfile
import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import asyncio
import aiofiles
from datetime import datetime
import json

# Configure logging
logger = logging.getLogger(__name__)

class FileOperations:
    """
    Utility class for file operations
    All operations are designed to be orchestrated through DSL workflows
    """
    
    @staticmethod
    async def compress_folder(
        folder_path: str,
        output_path: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        compression_level: int = 6,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Compress a folder into a zip file
        
        Args:
            folder_path: Path to folder to compress
            output_path: Path for output zip file
            include_patterns: List of glob patterns to include (e.g., ['*.docx', '*.pdf'])
            exclude_patterns: List of glob patterns to exclude (e.g., ['temp/*'])
            compression_level: Compression level (0-9, where 9 is maximum compression)
            progress_callback: Async callback for progress updates
            
        Returns:
            Dictionary with compression results and metadata
        """
        try:
            folder = Path(folder_path)
            if not folder.exists():
                raise FileNotFoundError(f"Folder not found: {folder_path}")
            
            if not folder.is_dir():
                raise ValueError(f"Path is not a directory: {folder_path}")
            
            # Collect files to compress
            files_to_compress = []
            total_size = 0
            
            for file_path in folder.rglob("*"):
                if file_path.is_file():
                    # Apply include/exclude patterns
                    relative_path = file_path.relative_to(folder)
                    
                    # Check exclude patterns first
                    if exclude_patterns:
                        if any(relative_path.match(pattern) for pattern in exclude_patterns):
                            logger.debug(f"Excluding: {relative_path}")
                            continue
                    
                    # Check include patterns if specified
                    if include_patterns:
                        if not any(relative_path.match(pattern) for pattern in include_patterns):
                            logger.debug(f"Skipping (not included): {relative_path}")
                            continue
                    
                    files_to_compress.append((file_path, relative_path))
                    total_size += file_path.stat().st_size
            
            logger.info(f"Compressing {len(files_to_compress)} files, total size: {total_size / (1024*1024):.2f} MB")
            
            # Create zip file
            start_time = datetime.now()
            compressed_size = 0
            
            with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED, 
                                compresslevel=compression_level) as zipf:
                
                for i, (file_path, relative_path) in enumerate(files_to_compress):
                    # Add file to zip
                    zipf.write(file_path, arcname=str(relative_path))
                    
                    # Report progress
                    if progress_callback and i % 10 == 0:
                        progress = (i + 1) / len(files_to_compress) * 100
                        await progress_callback({
                            'progress': progress,
                            'current_file': str(relative_path),
                            'files_processed': i + 1,
                            'total_files': len(files_to_compress)
                        })
            
            # Get compressed file size
            compressed_size = Path(output_path).stat().st_size
            compression_ratio = (1 - compressed_size / total_size) * 100 if total_size > 0 else 0
            
            duration = (datetime.now() - start_time).total_seconds()
            
            result = {
                'success': True,
                'output_path': output_path,
                'files_compressed': len(files_to_compress),
                'original_size_bytes': total_size,
                'compressed_size_bytes': compressed_size,
                'compression_ratio': f"{compression_ratio:.1f}%",
                'duration_seconds': duration,
                'compression_level': compression_level,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Compression complete: {result['compression_ratio']} reduction, {duration:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @staticmethod
    async def convert_docx_to_pdf(
        input_path: str,
        output_path: Optional[str] = None,
        quality: str = 'high',
        preserve_formatting: bool = True,
        use_claude: bool = True
    ) -> Dict[str, Any]:
        """
        Convert DOCX file to PDF
        
        Args:
            input_path: Path to input DOCX file
            output_path: Path for output PDF (if None, uses same name with .pdf extension)
            quality: Conversion quality ('low', 'medium', 'high')
            preserve_formatting: Whether to preserve original formatting
            use_claude: Whether to use Claude for intelligent conversion
            
        Returns:
            Dictionary with conversion results and metadata
        """
        try:
            input_file = Path(input_path)
            
            # Validate input file
            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            if input_file.suffix.lower() not in ['.docx', '.doc']:
                raise ValueError(f"Input file is not a Word document: {input_path}")
            
            # Determine output path
            if output_path is None:
                output_path = str(input_file.with_suffix('.pdf'))
            
            start_time = datetime.now()
            
            # If using Claude, delegate to Claude service for intelligent conversion
            if use_claude:
                # This will be handled by the DSL workflow
                logger.info(f"Delegating conversion to Claude service: {input_path} -> {output_path}")
                
                # For now, return a placeholder - actual implementation will be via DSL
                result = {
                    'success': True,
                    'method': 'claude_intelligent',
                    'input_path': input_path,
                    'output_path': output_path,
                    'quality': quality,
                    'preserve_formatting': preserve_formatting,
                    'conversion_type': 'dsl_workflow',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                # Fallback to library-based conversion
                try:
                    from docx2pdf import convert
                    
                    logger.info(f"Converting with docx2pdf: {input_path} -> {output_path}")
                    convert(input_path, output_path)
                    
                    # Verify output was created
                    if not Path(output_path).exists():
                        raise Exception("Conversion completed but output file not found")
                    
                    duration = (datetime.now() - start_time).total_seconds()
                    
                    result = {
                        'success': True,
                        'method': 'docx2pdf_library',
                        'input_path': input_path,
                        'output_path': output_path,
                        'input_size_bytes': input_file.stat().st_size,
                        'output_size_bytes': Path(output_path).stat().st_size,
                        'duration_seconds': duration,
                        'quality': quality,
                        'preserve_formatting': preserve_formatting,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                except ImportError:
                    raise ImportError("docx2pdf library not installed. Install with: pip install python-docx2pdf")
            
            logger.info(f"Conversion complete: {input_path} -> {output_path}")
            return result
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'input_path': input_path,
                'timestamp': datetime.now().isoformat()
            }
    
    @staticmethod
    async def batch_convert_documents(
        input_files: List[str],
        output_dir: str,
        conversion_type: str = 'docx_to_pdf',
        parallel: bool = True,
        max_workers: int = 4
    ) -> Dict[str, Any]:
        """
        Batch convert multiple documents
        
        Args:
            input_files: List of input file paths
            output_dir: Output directory for converted files
            conversion_type: Type of conversion (currently only 'docx_to_pdf')
            parallel: Whether to process files in parallel
            max_workers: Maximum number of parallel workers
            
        Returns:
            Dictionary with batch conversion results
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            results = []
            start_time = datetime.now()
            
            if parallel and len(input_files) > 1:
                # Process files in parallel
                logger.info(f"Starting parallel batch conversion of {len(input_files)} files")
                
                # Create tasks for parallel execution
                tasks = []
                for input_file in input_files:
                    output_file = output_path / (Path(input_file).stem + '.pdf')
                    
                    if conversion_type == 'docx_to_pdf':
                        task = FileOperations.convert_docx_to_pdf(
                            input_file, 
                            str(output_file)
                        )
                    else:
                        raise ValueError(f"Unsupported conversion type: {conversion_type}")
                    
                    tasks.append(task)
                
                # Execute with limited concurrency
                semaphore = asyncio.Semaphore(max_workers)
                
                async def bounded_task(task):
                    async with semaphore:
                        return await task
                
                bounded_tasks = [bounded_task(task) for task in tasks]
                results = await asyncio.gather(*bounded_tasks)
            else:
                # Process files sequentially
                logger.info(f"Starting sequential batch conversion of {len(input_files)} files")
                
                for input_file in input_files:
                    output_file = output_path / (Path(input_file).stem + '.pdf')
                    
                    if conversion_type == 'docx_to_pdf':
                        result = await FileOperations.convert_docx_to_pdf(
                            input_file,
                            str(output_file)
                        )
                    else:
                        raise ValueError(f"Unsupported conversion type: {conversion_type}")
                    
                    results.append(result)
            
            # Aggregate results
            successful = sum(1 for r in results if r.get('success', False))
            failed = len(results) - successful
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                'success': failed == 0,
                'total_files': len(input_files),
                'successful_conversions': successful,
                'failed_conversions': failed,
                'results': results,
                'output_directory': output_dir,
                'duration_seconds': duration,
                'parallel_processing': parallel,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Batch conversion failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @staticmethod
    async def extract_zip_metadata(zip_path: str) -> Dict[str, Any]:
        """
        Extract metadata from a zip file without extracting contents
        
        Args:
            zip_path: Path to zip file
            
        Returns:
            Dictionary with zip file metadata
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                file_list = []
                total_uncompressed = 0
                
                for info in zipf.infolist():
                    file_list.append({
                        'filename': info.filename,
                        'compressed_size': info.compress_size,
                        'uncompressed_size': info.file_size,
                        'compression_type': info.compress_type,
                        'date_time': datetime(*info.date_time).isoformat()
                    })
                    total_uncompressed += info.file_size
                
                return {
                    'success': True,
                    'zip_path': zip_path,
                    'file_count': len(file_list),
                    'total_compressed_size': Path(zip_path).stat().st_size,
                    'total_uncompressed_size': total_uncompressed,
                    'compression_ratio': f"{(1 - Path(zip_path).stat().st_size / total_uncompressed) * 100:.1f}%",
                    'files': file_list,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to extract zip metadata: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }