#!/usr/bin/env python3
"""
Claude Code CLI Integration Module
Wraps Claude Code command-line interface for DocAutomate
"""

import subprocess
import json
import tempfile
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import shlex
import asyncio
from dataclasses import dataclass

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CLIResult:
    """Result from CLI command execution"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0

class ClaudeCLI:
    """
    Wrapper for Claude Code CLI commands
    Uses subprocess to invoke Claude Code directly
    """
    
    def __init__(self, timeout: int = None, claude_cmd: str = None):
        """
        Initialize CLI wrapper
        
        Args:
            timeout: Command timeout in seconds (default from CLAUDE_TIMEOUT env or 120)
            claude_cmd: Path to claude executable (default from CLAUDE_CLI_PATH env or 'claude')
        """
        # Increased default timeout from 30 to 120 seconds for complex operations
        self.timeout = timeout if timeout is not None else int(os.getenv("CLAUDE_TIMEOUT", "120"))
        self.claude_cmd = claude_cmd if claude_cmd is not None else os.getenv("CLAUDE_CLI_PATH", "claude")
        
        logger.info(f"Initialized ClaudeCLI with timeout={self.timeout}s, command='{self.claude_cmd}'")
        
    def _run_command(self, cmd: List[str], input_text: Optional[str] = None, 
                    retries: int = 2, retry_delay: int = 5) -> CLIResult:
        """
        Execute Claude Code command with retry logic and extensive logging
        
        Args:
            cmd: Command and arguments as list
            input_text: Optional text to pipe to stdin
            retries: Number of retry attempts for timeout errors
            retry_delay: Delay between retries in seconds
            
        Returns:
            CLIResult with output, error, and status
        """
        # Log the command for debugging (without sensitive data)
        safe_cmd = ' '.join(cmd[:3]) + ' ...' if len(cmd) > 3 else ' '.join(cmd)
        input_preview = (input_text[:100] + '...') if input_text and len(input_text) > 100 else input_text
        
        for attempt in range(retries + 1):
            try:
                start_time = time.time()
                
                logger.info(f"[Attempt {attempt + 1}/{retries + 1}] Executing: {safe_cmd}")
                logger.debug(f"Full command: {' '.join(cmd)}")
                if input_text:
                    logger.debug(f"Input text preview: {input_preview}")
                    logger.debug(f"Input text size: {len(input_text)} characters")
                
                # Execute command
                result = subprocess.run(
                    cmd,
                    input=input_text if input_text else None,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False  # Don't raise on non-zero exit
                )
                
                elapsed = time.time() - start_time
                logger.info(f"Command completed in {elapsed:.2f}s with exit code {result.returncode}")
                
                if result.returncode == 0:
                    # Log the full output for debugging JSON issues
                    if len(result.stdout) < 500:
                        logger.debug(f"Full output: {result.stdout}")
                    else:
                        logger.debug(f"Output preview (first 500 chars): {result.stdout[:500]}...")
                    logger.debug(f"Output length: {len(result.stdout)} characters")
                else:
                    logger.warning(f"Command returned non-zero exit code: {result.returncode}")
                    if result.stderr:
                        logger.error(f"Error output: {result.stderr}")
                
                return CLIResult(
                    success=(result.returncode == 0),
                    output=result.stdout.strip(),
                    error=result.stderr.strip() if result.stderr else None,
                    exit_code=result.returncode
                )
                
            except subprocess.TimeoutExpired as e:
                elapsed = self.timeout
                logger.error(f"[Attempt {attempt + 1}/{retries + 1}] Command timed out after {self.timeout}s: {safe_cmd}")
                logger.debug(f"Partial stdout: {e.stdout if e.stdout else 'None'}")
                logger.debug(f"Partial stderr: {e.stderr if e.stderr else 'None'}")
                
                if attempt < retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"All retry attempts exhausted. Command failed after {retries + 1} attempts")
                    return CLIResult(
                        success=False,
                        output="",
                        error=f"Command timed out after {self.timeout} seconds (tried {retries + 1} times)",
                        exit_code=-1
                    )
                    
            except FileNotFoundError:
                logger.error(f"Claude command not found: {self.claude_cmd}")
                logger.info(f"Please check if Claude Code is installed and in PATH")
                logger.debug(f"Current PATH: {os.environ.get('PATH', 'Not set')}")
                return CLIResult(
                    success=False,
                    output="",
                    error=f"Claude command not found. Please ensure Claude Code is installed and '{self.claude_cmd}' is in PATH",
                    exit_code=-1
                )
                
            except Exception as e:
                logger.error(f"Unexpected error executing command: {e}")
                logger.debug(f"Exception type: {type(e).__name__}")
                import traceback
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")
                return CLIResult(
                    success=False,
                    output="",
                    error=str(e),
                    exit_code=-1
                )
    
    def read_document(self, file_path: str) -> str:
        """
        Use Claude Code Read tool to extract text from document
        Supports: PDF, images, text files, Word documents
        
        Args:
            file_path: Path to document file
            
        Returns:
            Extracted text content
            
        Raises:
            Exception: If document reading fails
        """
        start_time = time.time()
        logger.info(f"Starting document read for: {file_path}")
        
        # Verify file exists
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Get file info for logging
        file_size = file_path_obj.stat().st_size
        file_ext = file_path_obj.suffix.lower()
        logger.info(f"File details: size={file_size} bytes, extension={file_ext}")
        
        # For text files, read directly
        if file_ext in ('.txt', '.md', '.json', '.yaml', '.yml'):
            logger.info(f"Reading text file directly: {file_path}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                elapsed = time.time() - start_time
                logger.info(f"Successfully read text file in {elapsed:.2f}s: {file_path} ({len(content)} characters)")
                return content
            except Exception as e:
                logger.error(f"Failed to read text file: {e}")
                raise
        
        # For other files, use Claude to process them
        logger.info(f"Using Claude Code to process non-text file: {file_path}")
        
        # Use --print flag and ask Claude to read the file
        cmd = [self.claude_cmd, "--print"]
        prompt = f"Please read and extract the text content from the file: {file_path}"
        
        # Increase timeout for larger files
        adjusted_timeout = max(120, file_size // 10000)  # At least 120s, add 1s per 10KB
        if adjusted_timeout > self.timeout:
            logger.info(f"Adjusting timeout from {self.timeout}s to {adjusted_timeout}s for large file")
            original_timeout = self.timeout
            self.timeout = adjusted_timeout
        else:
            original_timeout = None
        
        try:
            result = self._run_command(cmd, input_text=prompt)
            
            if result.success:
                elapsed = time.time() - start_time
                logger.info(f"Successfully read document via Claude in {elapsed:.2f}s: {file_path}")
                logger.debug(f"Extracted {len(result.output)} characters from {file_path}")
                return result.output
            else:
                error_msg = f"Failed to read document: {result.error or 'Unknown error'}"
                logger.error(f"{error_msg} (file: {file_path})")
                raise Exception(error_msg)
        finally:
            # Restore original timeout if it was adjusted
            if original_timeout is not None:
                self.timeout = original_timeout
    
    def analyze_text(self, text: str, prompt: str, schema: Optional[Dict] = None) -> Dict:
        """
        Analyze text using Claude and return structured output
        
        Args:
            text: Text to analyze
            prompt: Analysis prompt/instructions
            schema: Optional JSON schema for structured output
            
        Returns:
            Analysis result as dictionary
            
        Raises:
            Exception: If analysis fails
        """
        # Prepare the full prompt
        full_prompt = f"{prompt}\n\n"
        
        if schema:
            full_prompt += f"Please respond with valid JSON matching this schema:\n"
            full_prompt += f"```json\n{json.dumps(schema, indent=2)}\n```\n\n"
            full_prompt += "Important: Return ONLY the JSON object, no additional text.\n\n"
        
        full_prompt += f"Text to analyze:\n---\n{text[:3000]}\n---\n"  # Limit text for safety
        
        # Use claude with --print flag for non-interactive output
        # Pass the prompt via stdin
        cmd = [self.claude_cmd, "--print"]
        
        result = self._run_command(cmd, input_text=full_prompt)
        
        if result.success:
            if schema:
                try:
                    # Parse JSON response
                    return json.loads(result.output)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON response: {e}")
                    logger.debug(f"Raw output that failed to parse: {result.output[:200]}")
                    # Attempt to extract JSON from response
                    import re
                    # First try to find a JSON array
                    array_match = re.search(r'\[.*\]', result.output, re.DOTALL)
                    if array_match:
                        try:
                            extracted = json.loads(array_match.group())
                            logger.info(f"Successfully extracted JSON array from response")
                            return extracted
                        except json.JSONDecodeError:
                            logger.warning("Found array pattern but it's not valid JSON")
                    
                    # Then try to find a JSON object
                    json_match = re.search(r'\{.*\}', result.output, re.DOTALL)
                    if json_match:
                        try:
                            extracted = json.loads(json_match.group())
                            logger.info(f"Successfully extracted JSON object from response")
                            return extracted
                        except json.JSONDecodeError:
                            logger.warning("Found object pattern but it's not valid JSON")
                    
                    # No JSON found, return the plain text with error indicator
                    logger.warning(f"No valid JSON found in response. Returning plain text.")
                    return {"result": result.output, "error": "JSON parsing failed"}
            else:
                return {"result": result.output}
        else:
            error_msg = f"Analysis failed: {result.error or 'Unknown error'}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def execute_task(self, agent: str, action: str, params: Optional[Dict] = None) -> Dict:
        """
        Execute a task using Claude Code's Task agent
        
        Args:
            agent: Agent name (e.g., 'finance-agent', 'general-purpose')
            action: Action to perform
            params: Optional parameters for the action
            
        Returns:
            Task execution result as dictionary
        """
        # Build base command with --print for non-interactive output
        cmd = [self.claude_cmd, "--print"]
        
        # Create prompt with action and parameters, including agent delegation
        if params:
            prompt = f"Use the Task tool to delegate to the {agent} agent: {action}\n\nParameters:\n{json.dumps(params, indent=2)}"
        else:
            prompt = f"Use the Task tool to delegate to the {agent} agent: {action}"
        
        result = self._run_command(cmd, input_text=prompt)
        
        if result.success:
            # Try to parse as JSON
            try:
                return json.loads(result.output)
            except json.JSONDecodeError:
                # Return as structured result
                return {
                    "status": "success",
                    "agent": agent,
                    "action": action,
                    "result": result.output
                }
        else:
            return {
                "status": "failed",
                "agent": agent,
                "action": action,
                "error": result.error or "Task execution failed"
            }
    
    def chat(self, message: str, context: Optional[str] = None) -> str:
        """
        Simple chat interaction with Claude
        
        Args:
            message: User message
            context: Optional context to include
            
        Returns:
            Claude's response
        """
        if context:
            full_message = f"Context:\n{context}\n\nMessage:\n{message}"
        else:
            full_message = message
        
        cmd = [self.claude_cmd, "--print"]
        result = self._run_command(cmd, input_text=full_message)
        
        if result.success:
            return result.output
        else:
            error_msg = f"Chat failed: {result.error or 'Unknown error'}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def validate_installation(self) -> bool:
        """
        Check if Claude Code is installed and accessible
        
        Returns:
            True if Claude Code is available, False otherwise
        """
        cmd = [self.claude_cmd, "--version"]
        result = self._run_command(cmd)
        
        if result.success:
            logger.info(f"Claude Code found: {result.output}")
            return True
        else:
            logger.warning(f"Claude Code not found or not accessible: {result.error}")
            return False

# Async wrapper for better integration
class AsyncClaudeCLI(ClaudeCLI):
    """Async version of ClaudeCLI for better integration with async code"""
    
    async def read_document_async(self, file_path: str) -> str:
        """Async version of read_document"""
        return await asyncio.to_thread(self.read_document, file_path)
    
    async def analyze_text_async(self, text: str, prompt: str, schema: Optional[Dict] = None) -> Dict:
        """Async version of analyze_text"""
        return await asyncio.to_thread(self.analyze_text, text, prompt, schema)
    
    async def execute_task_async(self, agent: str, action: str, params: Optional[Dict] = None) -> Dict:
        """Async version of execute_task"""
        return await asyncio.to_thread(self.execute_task, agent, action, params)
    
    async def chat_async(self, message: str, context: Optional[str] = None) -> str:
        """Async version of chat"""
        return await asyncio.to_thread(self.chat, message, context)

# Example usage and testing
if __name__ == "__main__":
    # Initialize CLI wrapper
    cli = ClaudeCLI()
    
    # Validate installation
    if cli.validate_installation():
        print("✅ Claude Code is installed and accessible")
    else:
        print("❌ Claude Code is not available. Please install Claude Code first.")
        print("   Visit: https://claude.ai/code for installation instructions")
    
    # Example: Read a document
    # try:
    #     text = cli.read_document("samples/invoice.pdf")
    #     print(f"📄 Document text (first 200 chars): {text[:200]}...")
    # except Exception as e:
    #     print(f"❌ Document reading failed: {e}")
    
    # Example: Analyze text
    # try:
    #     analysis = cli.analyze_text(
    #         text="Invoice #INV-2024-001 for $5,000 due on March 15, 2024",
    #         prompt="Extract invoice details including number, amount, and due date",
    #         schema={
    #             "invoice_number": {"type": "string"},
    #             "amount": {"type": "number"},
    #             "due_date": {"type": "string"}
    #         }
    #     )
    #     print(f"📊 Analysis result: {json.dumps(analysis, indent=2)}")
    # except Exception as e:
    #     print(f"❌ Analysis failed: {e}")
    
    # Example: Execute task
    # try:
    #     result = cli.execute_task(
    #         agent="general-purpose",
    #         action="summarize this text",
    #         params={"text": "Long document content here..."}
    #     )
    #     print(f"✅ Task result: {json.dumps(result, indent=2)}")
    # except Exception as e:
    #     print(f"❌ Task execution failed: {e}")
    
    print("\n💡 Claude CLI wrapper is ready for integration with DocAutomate")
    print("   Next step: Update ingester.py, extractor.py, and workflow.py to use this wrapper")