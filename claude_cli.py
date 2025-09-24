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
from pathlib import Path
from typing import Dict, Any, List, Optional
import shlex
import asyncio
from dataclasses import dataclass

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
            timeout: Command timeout in seconds (default from CLAUDE_TIMEOUT env or 30)
            claude_cmd: Path to claude executable (default from CLAUDE_CLI_PATH env or 'claude')
        """
        self.timeout = timeout if timeout is not None else int(os.getenv("CLAUDE_TIMEOUT", "30"))
        self.claude_cmd = claude_cmd if claude_cmd is not None else os.getenv("CLAUDE_CLI_PATH", "claude")
        
    def _run_command(self, cmd: List[str], input_text: Optional[str] = None) -> CLIResult:
        """
        Execute Claude Code command and return result
        
        Args:
            cmd: Command and arguments as list
            input_text: Optional text to pipe to stdin
            
        Returns:
            CLIResult with output, error, and status
        """
        try:
            # Log the command for debugging (without sensitive data)
            safe_cmd = ' '.join(cmd[:3]) + ' ...' if len(cmd) > 3 else ' '.join(cmd)
            logger.info(f"Running: {safe_cmd}")
            
            # Execute command
            result = subprocess.run(
                cmd,
                input=input_text if input_text else None,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False  # Don't raise on non-zero exit
            )
            
            return CLIResult(
                success=(result.returncode == 0),
                output=result.stdout.strip(),
                error=result.stderr.strip() if result.stderr else None,
                exit_code=result.returncode
            )
            
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {self.timeout}s: {safe_cmd}")
            return CLIResult(
                success=False,
                output="",
                error=f"Command timed out after {self.timeout} seconds",
                exit_code=-1
            )
        except FileNotFoundError:
            logger.error(f"Claude command not found: {self.claude_cmd}")
            return CLIResult(
                success=False,
                output="",
                error=f"Claude command not found. Please ensure Claude Code is installed and '{self.claude_cmd}' is in PATH",
                exit_code=-1
            )
        except Exception as e:
            logger.error(f"Command failed: {e}")
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
        # Verify file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # For text files, read directly
        if file_path.endswith(('.txt', '.md', '.json', '.yaml', '.yml')):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"Successfully read text file: {file_path}")
                return content
        
        # For other files, use Claude to process them
        # Use --print flag and ask Claude to read the file
        cmd = [self.claude_cmd, "--print"]
        prompt = f"Please read and extract the text content from the file: {file_path}"
        
        result = self._run_command(cmd, input_text=prompt)
        
        if result.success:
            logger.info(f"Successfully read document via Claude: {file_path}")
            return result.output
        else:
            error_msg = f"Failed to read document: {result.error or 'Unknown error'}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
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
                    # Attempt to extract JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', result.output, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    else:
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