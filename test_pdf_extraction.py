#!/usr/bin/env python3
"""
Test script to validate PDF extraction fixes
"""

import asyncio
import logging
from pathlib import Path
from claude_cli import ClaudeCLI, AsyncClaudeCLI
import sys

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_pdf_extraction():
    """Test PDF extraction with the fixed implementation"""
    
    # Find a PDF file to test with
    pdf_files = list(Path('.').glob('*.pdf'))
    if not pdf_files:
        logger.error("No PDF files found in current directory")
        logger.info("Please provide a PDF file for testing")
        return False
    
    test_pdf = pdf_files[0]
    logger.info(f"Testing with PDF file: {test_pdf}")
    
    # Test 1: Synchronous extraction with PTY
    logger.info("\n=== Test 1: Synchronous extraction with PTY ===")
    try:
        cli = ClaudeCLI()
        text = cli.read_document(str(test_pdf))
        
        if text and len(text) > 100:
            # Check for permission errors
            if 'i need your permission' in text.lower():
                logger.error("❌ Test 1 FAILED: Permission error in extracted text")
                logger.debug(f"Extracted text preview: {text[:200]}...")
                return False
            else:
                logger.info(f"✅ Test 1 PASSED: Extracted {len(text)} characters")
                logger.debug(f"Text preview: {text[:200]}...")
        else:
            logger.error(f"❌ Test 1 FAILED: Insufficient text extracted ({len(text)} chars)")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test 1 FAILED with exception: {e}")
        return False
    
    # Test 2: Async extraction
    logger.info("\n=== Test 2: Async extraction ===")
    try:
        async_cli = AsyncClaudeCLI()
        text = await async_cli.read_document_async(str(test_pdf))
        
        if text and len(text) > 100:
            if 'i need your permission' in text.lower():
                logger.error("❌ Test 2 FAILED: Permission error in extracted text")
                return False
            else:
                logger.info(f"✅ Test 2 PASSED: Extracted {len(text)} characters")
        else:
            logger.error(f"❌ Test 2 FAILED: Insufficient text extracted")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test 2 FAILED with exception: {e}")
        return False
    
    # Test 3: Direct PyPDF2 fallback
    logger.info("\n=== Test 3: PyPDF2 fallback test ===")
    try:
        cli = ClaudeCLI()
        text = cli._extract_pdf_fallback(str(test_pdf))
        
        if text and len(text) > 100:
            logger.info(f"✅ Test 3 PASSED: PyPDF2 extracted {len(text)} characters")
            logger.debug(f"Text preview: {text[:200]}...")
        else:
            logger.error(f"❌ Test 3 FAILED: PyPDF2 extraction insufficient")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test 3 FAILED with exception: {e}")
        return False
    
    logger.info("\n=== All tests completed successfully! ===")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_pdf_extraction())
    sys.exit(0 if success else 1)