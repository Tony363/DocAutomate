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
from typing import Dict, Any, List, Optional, Union
import asyncio
from dataclasses import dataclass
from enum import Enum
import hashlib
from datetime import datetime
import pty
import select
import fcntl
import PyPDF2

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

class SuperClaudeMode(str, Enum):
    """SuperClaude Framework behavioral modes"""
    BRAINSTORM = "brainstorm"
    TASK_MANAGE = "task-manage"
    ORCHESTRATE = "orchestrate"
    TOKEN_EFFICIENT = "uc"
    INTROSPECT = "introspect"
    LOOP = "loop"

class SuperClaudeAgent(str, Enum):
    """SuperClaude Framework specialized agents"""
    GENERAL_PURPOSE = "general-purpose"
    ROOT_CAUSE_ANALYST = "root-cause-analyst"
    REFACTORING_EXPERT = "refactoring-expert"
    TECHNICAL_WRITER = "technical-writer"
    PERFORMANCE_ENGINEER = "performance-engineer"
    SECURITY_ENGINEER = "security-engineer"
    FRONTEND_ARCHITECT = "frontend-architect"
    BACKEND_ARCHITECT = "backend-architect"
    FINANCE_ENGINEER = "finance-engineer"
    QUALITY_ENGINEER = "quality-engineer"

class SuperClaudeMCP(str, Enum):
    """SuperClaude Framework MCP servers"""
    SEQUENTIAL = "sequential"
    MAGIC = "magic"
    PLAYWRIGHT = "playwright"
    MORPHLLM = "morphllm"
    CONTEXT7 = "context7"
    SERENA = "serena"
    ZEN = "zen"

@dataclass
class CLIResult:
    """Result from CLI command execution"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    metadata: Optional[Dict[str, Any]] = None

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
        
        # Permission management configuration
        self.auto_grant_permissions = os.getenv("CLAUDE_AUTO_GRANT_FILE_ACCESS", "true").lower() == "true"
        allowed_dirs = os.getenv("CLAUDE_ALLOWED_DIRECTORIES", "")
        self.allowed_directories = [d.strip() for d in allowed_dirs.split(",") if d.strip()] if allowed_dirs else []
        
        logger.info(f"Initialized ClaudeCLI with timeout={self.timeout}s, command='{self.claude_cmd}'")
        logger.info(f"Permission settings: auto_grant={self.auto_grant_permissions}, allowed_dirs={len(self.allowed_directories)}")
        
        # Initialize audit logging
        self.audit_log_enabled = os.getenv("CLAUDE_AUDIT_LOG", "true").lower() == "true"
        self.audit_log_file = os.getenv("CLAUDE_AUDIT_LOG_FILE", "logs/claude_audit.log")
        if self.audit_log_enabled:
            self._ensure_audit_log_dir()
    
    def _ensure_audit_log_dir(self):
        """Ensure audit log directory exists"""
        audit_dir = Path(self.audit_log_file).parent
        audit_dir.mkdir(parents=True, exist_ok=True)
    
    def _log_file_access(self, file_path: str, operation: str, status: str, details: Dict[str, Any] = None):
        """Log file access for audit trail"""
        if not self.audit_log_enabled:
            return
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "file_path": file_path,
            "file_hash": hashlib.sha256(str(file_path).encode()).hexdigest()[:16],
            "status": status,
            "pid": os.getpid(),
            "details": details or {}
        }
        
        try:
            with open(self.audit_log_file, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")
        
    def _run_command_pty(self, cmd: List[str], input_text: Optional[str] = None) -> CLIResult:
        """
        Execute Claude Code command using PTY for interactive permission handling
        
        Args:
            cmd: Command and arguments as list
            input_text: Optional text to pipe to stdin
            
        Returns:
            CLIResult with output, error, and status
        """
        try:
            # Create a pseudo-terminal
            master_fd, slave_fd = pty.openpty()
            
            # Start the process
            process = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid
            )
            
            os.close(slave_fd)
            
            # Make the master fd non-blocking
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            output = []
            start_time = time.time()
            permission_prompted = False
            
            # Send initial input if provided
            if input_text:
                os.write(master_fd, (input_text + "\n").encode())
            
            while True:
                # Check for timeout
                if time.time() - start_time > self.timeout:
                    process.kill()
                    os.close(master_fd)
                    return CLIResult(
                        success=False,
                        output="",
                        error="Command timed out",
                        exit_code=-1
                    )
                
                # Check if process is still running
                if process.poll() is not None:
                    break
                
                # Try to read output
                readable, _, _ = select.select([master_fd], [], [], 0.1)
                if readable:
                    try:
                        data = os.read(master_fd, 1024).decode('utf-8', errors='ignore')
                        output.append(data)
                        
                        # Check for permission prompt and auto-respond
                        if not permission_prompted and any(phrase in data.lower() for phrase in 
                            ['permission', 'allow', 'grant', 'access', 'yes/no', 'y/n']):
                            logger.info("Permission prompt detected, auto-responding 'yes'")
                            os.write(master_fd, b"yes\n")
                            permission_prompted = True
                            
                    except OSError:
                        break
            
            # Get final output
            try:
                remaining = os.read(master_fd, 10240).decode('utf-8', errors='ignore')
                output.append(remaining)
            except:
                pass
            
            os.close(master_fd)
            exit_code = process.returncode
            
            full_output = ''.join(output).strip()
            
            return CLIResult(
                success=(exit_code == 0),
                output=full_output,
                error=None if exit_code == 0 else f"Exit code: {exit_code}",
                exit_code=exit_code
            )
            
        except Exception as e:
            logger.error(f"PTY execution failed: {e}")
            return CLIResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    def _run_command(self, cmd: List[str], input_text: Optional[str] = None, 
                    retries: int = 2, retry_delay: int = 5, use_pty: bool = False) -> CLIResult:
        """
        Execute Claude Code command with retry logic and extensive logging
        
        Args:
            cmd: Command and arguments as list
            input_text: Optional text to pipe to stdin
            retries: Number of retry attempts for timeout errors
            retry_delay: Delay between retries in seconds
            use_pty: Use PTY for interactive commands
            
        Returns:
            CLIResult with output, error, and status
        """
        # Use PTY for interactive commands if requested
        if use_pty:
            return self._run_command_pty(cmd, input_text)
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
    
    def _extract_pdf_fallback(self, file_path: str) -> str:
        """
        Fallback PDF extraction using PyPDF2
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text from PDF
        """
        try:
            logger.info(f"Using PyPDF2 fallback for PDF extraction: {file_path}")
            
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text_parts = []
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text_parts.append(page.extract_text())
                
                full_text = '\n'.join(text_parts)
                logger.info(f"PyPDF2 extracted {len(full_text)} characters from {file_path}")
                return full_text
                
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {e}")
            raise
    
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
        
        # For PDF files, try Claude first with PTY, then fallback to PyPDF2
        if file_ext == '.pdf':
            logger.info(f"Processing PDF file: {file_path}")
            
            # Try Claude with PTY for interactive permission handling
            cmd = [self.claude_cmd, "--print"]
            prompt = f"Please read and extract the text content from the file: {file_path}"
            
            logger.info(f"Attempting Claude Code extraction with PTY for: {file_path}")
            result = self._run_command(cmd, input_text=prompt, use_pty=True)
            
            if result.success:
                # Validate the extracted content
                if (len(result.output) > 100 and 
                    not any(phrase in result.output.lower() for phrase in 
                           ['permission', 'grant', 'access', 'allow', 'i need your permission'])):
                    logger.info(f"Claude successfully extracted {len(result.output)} characters")
                    
                    # Audit log successful extraction
                    self._log_file_access(file_path, "file_read", "success", {
                        "method": "claude_pty",
                        "output_length": len(result.output),
                        "file_size": file_size
                    })
                    
                    return result.output
                else:
                    logger.warning(f"Claude extraction appears to have failed (permission issue or short output)")
            
            # If Claude fails, use PyPDF2 fallback
            logger.info(f"Claude extraction failed, using PyPDF2 fallback for: {file_path}")
            try:
                pdf_text = self._extract_pdf_fallback(file_path)
                
                # Audit log fallback extraction
                self._log_file_access(file_path, "file_read", "success", {
                    "method": "pypdf2_fallback",
                    "output_length": len(pdf_text),
                    "file_size": file_size
                })
                
                return pdf_text
            except Exception as e:
                logger.error(f"Both Claude and PyPDF2 extraction failed for {file_path}: {e}")
                
                # Audit log failure
                self._log_file_access(file_path, "file_read", "failed", {
                    "error": str(e),
                    "methods_tried": ["claude_pty", "pypdf2"]
                })
                
                raise Exception(f"PDF extraction failed for {file_path}: {e}")
        
        # For other non-text files, use Claude to process them
        logger.info(f"Using Claude Code to process non-text file: {file_path}")
        
        cmd = [self.claude_cmd, "--print"]
        prompt = f"Please read and extract the text content from the file: {file_path}"
        
        # Use PTY for better interactive handling
        logger.info(f"Using Claude Code with PTY for: {file_path}")
        result = self._run_command(cmd, input_text=prompt, use_pty=True)
        
        # Increase timeout for larger files if needed
        adjusted_timeout = max(120, file_size // 10000)  # At least 120s, add 1s per 10KB
        if adjusted_timeout > self.timeout:
            logger.info(f"Adjusting timeout from {self.timeout}s to {adjusted_timeout}s for large file")
            original_timeout = self.timeout
            self.timeout = adjusted_timeout
        else:
            original_timeout = None
        
        try:
            if not result.success:
                # Try again with standard subprocess as fallback
                logger.info(f"PTY failed, trying standard subprocess for: {file_path}")
                result = self._run_command(cmd, input_text=prompt, use_pty=False)
            
            if result.success:
                elapsed = time.time() - start_time
                logger.info(f"Successfully read document via Claude in {elapsed:.2f}s: {file_path}")
                logger.debug(f"Extracted {len(result.output)} characters from {file_path}")
                
                # Log successful file access for audit trail
                logger.info(f"File access granted and processed: {file_path} ({len(result.output)} chars)")
                
                # Audit log successful file processing
                self._log_file_access(file_path, "file_read", "success", {
                    "processing_time": elapsed,
                    "output_length": len(result.output),
                    "file_size": file_size
                })
                
                return result.output
            else:
                # Enhanced error handling for permission-related issues
                error_msg = result.error or 'Unknown error'
                
                # Detect common permission-related error patterns
                if any(keyword in error_msg.lower() for keyword in ['permission', 'access', 'denied', 'unauthorized']):
                    logger.error(f"Permission-related error for {file_path}: {error_msg}")
                    logger.info("Try setting CLAUDE_AUTO_GRANT_FILE_ACCESS=true or run Claude interactively first")
                    
                    # Audit log permission failure
                    self._log_file_access(file_path, "file_read", "permission_denied", {
                        "error": error_msg,
                        "auto_grant_enabled": self.auto_grant_permissions
                    })
                    
                    raise PermissionError(f"File access permission required: {error_msg}")
                elif 'timeout' in error_msg.lower():
                    logger.error(f"Timeout during file processing - may indicate permission prompt waiting: {file_path}")
                    
                    # Audit log timeout failure
                    self._log_file_access(file_path, "file_read", "timeout", {
                        "error": error_msg,
                        "timeout_seconds": self.timeout
                    })
                    
                    raise TimeoutError(f"File processing timeout (possible permission issue): {error_msg}")
                else:
                    logger.error(f"Failed to read document: {error_msg} (file: {file_path})")
                    
                    # Audit log general failure
                    self._log_file_access(file_path, "file_read", "error", {
                        "error": error_msg
                    })
                    
                    raise Exception(f"Document processing failed: {error_msg}")
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
        # Prepare the full prompt with stronger JSON enforcement
        if schema:
            # Much stronger JSON enforcement for schema-based requests
            full_prompt = f"""{prompt}

CRITICAL JSON OUTPUT REQUIREMENTS:
1. You MUST respond with valid JSON only
2. Use this exact schema: {json.dumps(schema, indent=2)}
3. Do NOT include any explanatory text before or after the JSON
4. Start your response with {{ or [
5. End your response with }} or ]
6. No markdown code blocks, no comments, just pure JSON

Text to analyze:
---
{text[:3000]}
---

JSON OUTPUT (no other text):"""
        else:
            full_prompt = f"{prompt}\n\nText to analyze:\n---\n{text[:3000]}\n---\n"
        
        # Use claude with --print flag for non-interactive output
        cmd = [self.claude_cmd, "--print"]
        
        # Try with retries if JSON parsing fails
        max_attempts = 3 if schema else 1
        import re
        
        for attempt in range(max_attempts):
            if attempt > 0:
                # Strengthen JSON requirement on retries
                logger.info(f"Retry {attempt}/{max_attempts - 1} with stronger JSON enforcement")
                retry_prompt = f"IMPORTANT: Return ONLY valid JSON, no other text!\n\n{full_prompt}"
                result = self._run_command(cmd, input_text=retry_prompt)
            else:
                result = self._run_command(cmd, input_text=full_prompt)
            
            if result.success:
                if schema:
                    # Try to parse as JSON
                    output = result.output.strip()
                    
                    # Try direct parsing
                    try:
                        parsed = json.loads(output)
                        logger.info("Successfully parsed JSON response directly")
                        return parsed
                    except json.JSONDecodeError as e:
                        if attempt == 0:
                            logger.warning(f"Failed to parse JSON response: {e}")
                        
                        # Enhanced JSON extraction patterns
                        json_patterns = [
                            (r'^\s*(\{.*\})\s*$', 'object'),  # Object at start/end
                            (r'^\s*(\[.*\])\s*$', 'array'),   # Array at start/end
                            (r'(\{[^{}]*\{[^{}]*\}[^{}]*\})', 'nested_object'),  # Nested object
                            (r'(\[[^\[\]]*\])', 'simple_array'),  # Simple array
                            (r'(\{[^{}]*\})', 'simple_object'),   # Simple object
                        ]
                        
                        for pattern, pattern_type in json_patterns:
                            matches = re.findall(pattern, output, re.DOTALL | re.MULTILINE)
                            for match in matches:
                                try:
                                    parsed = json.loads(match)
                                    logger.info(f"Successfully extracted JSON {pattern_type} from response")
                                    return parsed
                                except json.JSONDecodeError:
                                    continue
                        
                        # On last attempt, return empty schema
                        if attempt == max_attempts - 1:
                            logger.warning("No valid JSON found after retries. Returning empty schema.")
                            return {} if isinstance(schema, dict) else []
                else:
                    return {"result": result.output}
            else:
                if attempt == max_attempts - 1:
                    error_msg = f"Analysis failed after {max_attempts} attempts: {result.error or 'Unknown error'}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
        
        # Should not reach here
        return {} if schema else {"result": ""}
    
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
    
    # SuperClaude Framework Integration Methods
    
    def execute_with_mode(self, 
                         prompt: str, 
                         mode: Union[SuperClaudeMode, str], 
                         context: Optional[Dict[str, Any]] = None) -> CLIResult:
        """
        Execute command with SuperClaude behavioral mode
        
        Args:
            prompt: Command or query to execute
            mode: SuperClaude behavioral mode (brainstorm, task-manage, etc.)
            context: Optional context data
            
        Returns:
            CLI execution result with metadata
        """
        mode_str = mode.value if isinstance(mode, SuperClaudeMode) else mode
        
        # Map SuperClaude modes to prompt instructions
        mode_prompts = {
            "task-manage": "--task-manage: Orchestrate this task with systematic organization and TodoWrite tracking.",
            "brainstorm": "--brainstorm: Use collaborative discovery mindset to explore this request.",
            "orchestrate": "--orchestrate: Optimize tool selection and parallel execution for this task.",
            "uc": "--uc: Use ultra-compressed token-efficient mode with symbols and abbreviations.",
            "introspect": "--introspect: Apply meta-cognitive analysis and self-reflection.",
            "loop": "--loop: Iterate until quality threshold ≥70% is achieved."
        }
        
        # Build command with ONLY valid CLI flags
        cmd = [self.claude_cmd, "--print"]
        
        # Embed mode instruction in prompt
        mode_instruction = mode_prompts.get(mode_str, f"--{mode_str}: Execute in {mode_str} mode.")
        full_prompt = f"{mode_instruction}\n\n{prompt}"
        
        if context:
            full_prompt = f"Context: {json.dumps(context, indent=2)}\n\n{full_prompt}"
        
        logger.info(f"Executing with {mode_str} mode: {prompt[:50]}...")
        
        result = self._run_command(cmd, input_text=full_prompt)
        
        # Add metadata about the mode used
        if result.metadata is None:
            result.metadata = {}
        result.metadata["mode"] = mode_str
        result.metadata["context_provided"] = bool(context)
        
        return result
    
    def delegate_to_agent(self, 
                         prompt: str, 
                         agent: Union[SuperClaudeAgent, str] = None,
                         task_manage: bool = False,
                         quality_loop: bool = False) -> CLIResult:
        """
        Delegate task to specialized SuperClaude agent
        
        Args:
            prompt: Task description
            agent: Specific agent to use (if None, auto-routes)
            task_manage: Enable task management mode
            quality_loop: Enable quality improvement loop
            
        Returns:
            CLI execution result with agent metadata
        """
        # Build command with ONLY valid flags
        cmd = [self.claude_cmd, "--print"]
        
        # Build agent instruction
        agent_instruction = "--delegate: Use intelligent agent routing for this task.\n"
        
        if agent:
            agent_str = agent.value if isinstance(agent, SuperClaudeAgent) else agent
            agent_instruction += f"Specifically use the {agent_str} agent.\n"
        else:
            agent_instruction += "Auto-select the best agent based on the task requirements.\n"
        
        if task_manage:
            agent_instruction += "--task-manage: Apply systematic task organization with TodoWrite tracking.\n"
        
        if quality_loop:
            agent_instruction += "--loop: Iterate until quality score ≥70% is achieved.\n"
        
        full_prompt = f"{agent_instruction}\n{prompt}"
        
        logger.info(f"Delegating to agent {agent or 'auto'}: {prompt[:50]}...")
        
        result = self._run_command(cmd, input_text=full_prompt)
        
        # Add metadata
        if result.metadata is None:
            result.metadata = {}
        result.metadata["delegation"] = True
        result.metadata["requested_agent"] = agent.value if isinstance(agent, SuperClaudeAgent) else agent
        result.metadata["task_manage"] = task_manage
        result.metadata["quality_loop"] = quality_loop
        
        return result
    
    def use_mcp_server(self, 
                      prompt: str, 
                      mcp: Union[SuperClaudeMCP, str],
                      additional_flags: List[str] = None) -> CLIResult:
        """
        Execute task using specific MCP server
        
        Args:
            prompt: Task description
            mcp: MCP server to use
            additional_flags: Additional command flags
            
        Returns:
            CLI execution result with MCP metadata
        """
        mcp_str = mcp.value if isinstance(mcp, SuperClaudeMCP) else mcp
        
        # Map MCP servers to instructions
        mcp_prompts = {
            "zen": "Use the Zen MCP server for multi-model consensus and deep thinking.",
            "sequential": "Use Sequential MCP for structured multi-step reasoning.",
            "magic": "Use Magic MCP for UI component generation.",
            "playwright": "Use Playwright MCP for browser automation.",
            "context7": "Use Context7 MCP for framework documentation.",
            "serena": "Use Serena MCP for semantic understanding.",
            "morphllm": "Use Morphllm MCP for bulk code transformations."
        }
        
        # Build command with ONLY valid CLI flags
        cmd = [self.claude_cmd, "--print"]
        
        # Build prompt with MCP instruction
        mcp_instruction = mcp_prompts.get(mcp_str, f"Use {mcp_str} MCP server for this task.")
        
        # Add additional SuperClaude directives if provided
        if additional_flags:
            for flag in additional_flags:
                if flag == "--thinkdeep":
                    mcp_instruction += "\n--thinkdeep: Apply deep multi-angle analysis and hypothesis testing."
                elif flag == "--consensus":
                    mcp_instruction += "\n--consensus: Build multi-model consensus validation."
                elif flag == "--model":
                    # Skip model flag, next item will be model name
                    continue
                elif flag in ["gpt-5", "claude-opus-4.1", "gpt-4.1"]:
                    # Model names - add as preference
                    mcp_instruction += f"\nPreferred model: {flag}"
                elif not flag.startswith("-"):
                    # Skip non-flag arguments
                    continue
                else:
                    mcp_instruction += f"\n{flag}"
        
        full_prompt = f"{mcp_instruction}\n\n{prompt}"
        
        logger.info(f"Using {mcp_str} MCP server: {prompt[:50]}...")
        
        result = self._run_command(cmd, input_text=full_prompt)
        
        # Add metadata
        if result.metadata is None:
            result.metadata = {}
        result.metadata["mcp_server"] = mcp_str
        result.metadata["additional_flags"] = additional_flags or []
        
        return result
    
    def brainstorm_document_processing(self, 
                                     document_content: str, 
                                     document_meta: Dict[str, Any]) -> CLIResult:
        """
        Use brainstorming mode to determine document processing approach
        
        Args:
            document_content: Document text content
            document_meta: Document metadata (type, source, etc.)
            
        Returns:
            Brainstorming result with processing recommendations
        """
        context = {
            "document_type": document_meta.get("content_type", "unknown"),
            "document_size": len(document_content),
            "source": document_meta.get("source", "unknown"),
            "metadata": document_meta
        }
        
        prompt = f"""Analyze this document and determine the best processing approach:
        
Document Type: {context['document_type']}
Size: {context['document_size']} characters
Source: {context['source']}

Please recommend:
1. What type of document this is
2. What actions should be taken
3. Which agents would be most suitable
4. What workflow should be used

Document content preview (first 500 chars):
{document_content[:500]}..."""
        
        return self.execute_with_mode(prompt, SuperClaudeMode.BRAINSTORM, context)
    
    def generate_code_for_document(self, 
                                 document_data: Dict[str, Any],
                                 generation_type: str = "analysis",
                                 language: str = "python") -> CLIResult:
        """
        Generate code for document analysis/processing
        
        Args:
            document_data: Extracted document data
            generation_type: Type of code to generate (analysis, visualization, automation)
            language: Programming language for generated code
            
        Returns:
            Generated code result
        """
        prompt = f"""Generate {language} code for {generation_type} of this document data:

Data: {json.dumps(document_data, indent=2)}

Please generate:
1. Complete working {language} script
2. Include necessary imports and dependencies
3. Add comments explaining the logic
4. Include error handling
5. Make the code production-ready

Focus on: {generation_type}"""
        
        context = {
            "document_data": document_data,
            "generation_type": generation_type,
            "language": language
        }
        
        # Use task management for code generation
        return self.execute_with_mode(prompt, SuperClaudeMode.TASK_MANAGE, context)
    
    def orchestrate_parallel_processing(self, 
                                      documents: List[Dict[str, Any]],
                                      processing_hints: Dict[str, Any] = None) -> CLIResult:
        """
        Orchestrate parallel processing of multiple documents
        
        Args:
            documents: List of document metadata and content
            processing_hints: Hints for processing optimization
            
        Returns:
            Orchestration plan result
        """
        context = {
            "document_count": len(documents),
            "document_types": [doc.get("content_type") for doc in documents],
            "processing_hints": processing_hints or {}
        }
        
        prompt = f"""Plan parallel processing for {len(documents)} documents:

Document types: {', '.join(set(context['document_types']))}

Please create:
1. Optimal processing strategy
2. Resource allocation plan
3. Parallel execution approach
4. Quality assurance checkpoints
5. Error handling strategy

Processing hints: {json.dumps(processing_hints or {}, indent=2)}"""
        
        return self.execute_with_mode(prompt, SuperClaudeMode.ORCHESTRATE, context)
    
    def quality_improvement_loop(self, 
                                initial_result: Dict[str, Any],
                                quality_threshold: float = 0.85,
                                max_iterations: int = 3) -> CLIResult:
        """
        Run quality improvement loop on processing results
        
        Args:
            initial_result: Initial processing result to improve
            quality_threshold: Minimum quality score target
            max_iterations: Maximum improvement iterations
            
        Returns:
            Improved result with quality metadata
        """
        context = {
            "initial_quality": initial_result.get("quality_score", 0.0),
            "threshold": quality_threshold,
            "max_iterations": max_iterations
        }
        
        prompt = f"""Improve the quality of this processing result:

Initial Result: {json.dumps(initial_result, indent=2)}

Current Quality Score: {context['initial_quality']}
Target Quality Score: {quality_threshold}

Please:
1. Identify quality issues
2. Suggest specific improvements
3. Provide enhanced version
4. Validate the improvements
5. Calculate new quality score"""
        
        return self.execute_with_mode(prompt, SuperClaudeMode.LOOP, context)

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
    
    async def execute_with_mode_async(self, 
                                     prompt: str, 
                                     mode: Union[SuperClaudeMode, str], 
                                     context: Optional[Dict[str, Any]] = None) -> CLIResult:
        """Async wrapper for execute_with_mode"""
        return await asyncio.to_thread(self.execute_with_mode, prompt, mode, context)
    
    async def use_mcp_server_async(self, 
                                  prompt: str, 
                                  mcp: Union[SuperClaudeMCP, str],
                                  additional_flags: List[str] = None) -> CLIResult:
        """Async wrapper for use_mcp_server"""
        return await asyncio.to_thread(self.use_mcp_server, prompt, mcp, additional_flags)
    
    async def delegate_to_agent_async(self, 
                                     prompt: str, 
                                     agent: Union[SuperClaudeAgent, str] = None,
                                     task_manage: bool = False,
                                     quality_loop: bool = False) -> CLIResult:
        """Async wrapper for delegate_to_agent"""
        return await asyncio.to_thread(self.delegate_to_agent, prompt, agent, task_manage, quality_loop)

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
    
    # Example usage available in project documentation
    
    print("\n💡 Claude CLI wrapper is ready for integration with DocAutomate")
    print("   Next step: Update ingester.py, extractor.py, and workflow.py to use this wrapper")