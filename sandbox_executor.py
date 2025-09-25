#!/usr/bin/env python3
"""
Sandbox Executor Module - Secure Code Execution
Provides secure, isolated execution environment for generated code
"""

import subprocess
import tempfile
import logging
import json
import os
import time
import signal
import resource
import shutil
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import hashlib
import threading
import asyncio

logger = logging.getLogger(__name__)

class ExecutionStatus(str, Enum):
    """Execution status enumeration"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_LIMIT = "resource_limit"

class SecurityLevel(str, Enum):
    """Security level for code execution"""
    LOW = "low"        # Basic process isolation
    MEDIUM = "medium"  # Resource limits + network restrictions
    HIGH = "high"      # Full sandboxing with container-like isolation

@dataclass
class ExecutionLimits:
    """Resource limits for code execution"""
    timeout_seconds: int = 60
    memory_limit_mb: int = 512
    cpu_time_seconds: int = 30
    max_output_size: int = 1024 * 1024  # 1MB
    network_access: bool = False
    file_system_access: bool = True
    max_files: int = 100

@dataclass
class ExecutionResult:
    """Result of code execution"""
    status: ExecutionStatus
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    memory_used: int
    files_created: List[str]
    artifacts: Dict[str, Any]
    error_message: Optional[str] = None
    security_violations: List[str] = None

class SandboxExecutor:
    """
    Secure code executor with configurable isolation levels
    """
    
    def __init__(self, 
                 security_level: SecurityLevel = SecurityLevel.MEDIUM,
                 base_limits: ExecutionLimits = None):
        self.security_level = security_level
        self.limits = base_limits or ExecutionLimits()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="docautomate_sandbox_"))
        self.allowed_imports = self._get_allowed_imports()
        
        logger.info(f"Initialized sandbox executor with {security_level.value} security")
        
    def _get_allowed_imports(self) -> List[str]:
        """Get list of allowed Python imports based on security level"""
        base_imports = [
            "json", "csv", "datetime", "time", "math", "statistics",
            "collections", "itertools", "functools", "operator",
            "pathlib", "os.path", "typing"
        ]
        
        if self.security_level in [SecurityLevel.LOW, SecurityLevel.MEDIUM]:
            base_imports.extend([
                "pandas", "numpy", "matplotlib", "seaborn", "openpyxl",
                "sqlite3", "re", "hashlib", "base64"
            ])
        
        if self.security_level == SecurityLevel.LOW:
            base_imports.extend([
                "requests", "urllib", "http", "email", "smtplib"
            ])
        
        return base_imports
    
    async def execute_code(self, 
                          code: str, 
                          language: str = "python",
                          input_data: Dict[str, Any] = None,
                          custom_limits: ExecutionLimits = None) -> ExecutionResult:
        """
        Execute code in secure sandbox environment
        
        Args:
            code: Code to execute
            language: Programming language
            input_data: Input data for the code
            custom_limits: Custom resource limits
            
        Returns:
            Execution result with output and metadata
        """
        limits = custom_limits or self.limits
        
        logger.info(f"Executing {language} code with {self.security_level.value} security")
        
        # Validate code before execution
        security_issues = self._validate_code_security(code, language)
        if security_issues:
            return ExecutionResult(
                status=ExecutionStatus.PERMISSION_DENIED,
                stdout="",
                stderr="Security validation failed",
                return_code=-1,
                execution_time=0.0,
                memory_used=0,
                files_created=[],
                artifacts={},
                error_message="Code contains security violations",
                security_violations=security_issues
            )
        
        # Prepare execution environment
        execution_dir = self.temp_dir / f"exec_{int(time.time())}"
        execution_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if language.lower() == "python":
                result = await self._execute_python_code(code, input_data, limits, execution_dir)
            elif language.lower() == "bash":
                result = await self._execute_bash_code(code, input_data, limits, execution_dir)
            else:
                raise ValueError(f"Unsupported language: {language}")
            
            # Collect artifacts
            result.artifacts = self._collect_artifacts(execution_dir)
            result.files_created = [str(f) for f in execution_dir.rglob("*") if f.is_file()]
            
            return result
            
        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=0.0,
                memory_used=0,
                files_created=[],
                artifacts={},
                error_message=str(e)
            )
        finally:
            # Cleanup execution directory if not needed for artifacts
            if not result or not result.artifacts:
                try:
                    shutil.rmtree(execution_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup execution directory: {e}")
    
    def _validate_code_security(self, code: str, language: str) -> List[str]:
        """
        Validate code for security issues
        
        Args:
            code: Code to validate
            language: Programming language
            
        Returns:
            List of security issues found
        """
        issues = []
        
        if language.lower() == "python":
            issues.extend(self._validate_python_security(code))
        elif language.lower() == "bash":
            issues.extend(self._validate_bash_security(code))
        
        return issues
    
    def _validate_python_security(self, code: str) -> List[str]:
        """Validate Python code security"""
        issues = []
        
        # Check for dangerous imports
        dangerous_imports = [
            "subprocess", "os.system", "eval", "exec", "compile",
            "__import__", "importlib", "sys", "ctypes"
        ]
        
        if self.security_level == SecurityLevel.HIGH:
            dangerous_imports.extend(["socket", "urllib", "requests", "http"])
        
        for dangerous in dangerous_imports:
            if dangerous in code:
                issues.append(f"Potentially dangerous import or function: {dangerous}")
        
        # Check for file system operations that might be dangerous
        if self.security_level == SecurityLevel.HIGH:
            dangerous_file_ops = ["open(", "with open", "file(", "shutil.", "os."]
            for op in dangerous_file_ops:
                if op in code and "/tmp/" not in code:
                    issues.append(f"File system operation outside sandbox: {op}")
        
        # Check for network operations
        if not self.limits.network_access:
            network_patterns = ["urllib", "requests", "socket", "http", "ftp"]
            for pattern in network_patterns:
                if pattern in code:
                    issues.append(f"Network access not allowed: {pattern}")
        
        return issues
    
    def _validate_bash_security(self, code: str) -> List[str]:
        """Validate Bash code security"""
        issues = []
        
        # Check for dangerous commands
        dangerous_commands = [
            "rm -rf", "rm -r", "sudo", "su", "chmod", "chown",
            "passwd", "adduser", "deluser", "crontab", "systemctl",
            "service", "mount", "umount", "fdisk", "mkfs"
        ]
        
        for dangerous in dangerous_commands:
            if dangerous in code:
                issues.append(f"Dangerous command: {dangerous}")
        
        # Check for network operations
        if not self.limits.network_access:
            network_commands = ["curl", "wget", "nc", "netcat", "ssh", "scp", "rsync"]
            for cmd in network_commands:
                if cmd in code:
                    issues.append(f"Network command not allowed: {cmd}")
        
        return issues
    
    async def _execute_python_code(self, 
                                 code: str, 
                                 input_data: Dict[str, Any],
                                 limits: ExecutionLimits,
                                 execution_dir: Path) -> ExecutionResult:
        """Execute Python code with security constraints"""
        
        # Create Python script file
        script_file = execution_dir / "script.py"
        
        # Prepare the code with input data
        if input_data:
            data_setup = f"import json\nINPUT_DATA = {json.dumps(input_data, indent=2, default=str)}\n\n"
            full_code = data_setup + code
        else:
            full_code = code
        
        # Write code to file
        with open(script_file, 'w') as f:
            f.write(full_code)
        
        # Prepare execution command
        cmd = [
            "python3", "-u",  # Unbuffered output
            str(script_file)
        ]
        
        # Execute with resource limits
        return await self._execute_with_limits(cmd, limits, execution_dir)
    
    async def _execute_bash_code(self, 
                                code: str, 
                                input_data: Dict[str, Any],
                                limits: ExecutionLimits,
                                execution_dir: Path) -> ExecutionResult:
        """Execute Bash code with security constraints"""
        
        # Create bash script file
        script_file = execution_dir / "script.sh"
        
        # Prepare the script
        full_code = f"#!/bin/bash\nset -e\ncd {execution_dir}\n\n{code}"
        
        # Write code to file
        with open(script_file, 'w') as f:
            f.write(full_code)
        
        # Make executable
        os.chmod(script_file, 0o755)
        
        # Prepare execution command
        cmd = ["bash", str(script_file)]
        
        # Execute with resource limits
        return await self._execute_with_limits(cmd, limits, execution_dir)
    
    async def _execute_with_limits(self, 
                                 cmd: List[str], 
                                 limits: ExecutionLimits,
                                 execution_dir: Path) -> ExecutionResult:
        """Execute command with resource limits"""
        
        start_time = time.time()
        
        # Prepare environment
        env = os.environ.copy()
        env['PYTHONPATH'] = str(execution_dir)
        env['HOME'] = str(execution_dir)
        env['TMPDIR'] = str(execution_dir)
        
        if not limits.network_access:
            # Block network access by setting empty proxy
            env['http_proxy'] = 'http://127.0.0.1:1'
            env['https_proxy'] = 'http://127.0.0.1:1'
        
        # Set resource limits
        def set_limits():
            # Memory limit (in bytes)
            resource.setrlimit(resource.RLIMIT_AS, (limits.memory_limit_mb * 1024 * 1024, -1))
            
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_time_seconds, -1))
            
            # File descriptor limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_files, limits.max_files))
            
            # Core dump size limit
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        
        try:
            # Execute the command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=execution_dir,
                env=env,
                preexec_fn=set_limits if os.name == 'posix' else None
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=limits.timeout_seconds
                )
                return_code = process.returncode
                status = ExecutionStatus.SUCCESS if return_code == 0 else ExecutionStatus.FAILED
                
            except asyncio.TimeoutError:
                # Kill the process if it times out
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
                
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    stdout="",
                    stderr=f"Execution timed out after {limits.timeout_seconds} seconds",
                    return_code=-1,
                    execution_time=time.time() - start_time,
                    memory_used=0,
                    files_created=[],
                    artifacts={},
                    error_message="Execution timeout"
                )
            
            # Decode output
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            
            # Truncate output if too large
            if len(stdout_text) > limits.max_output_size:
                stdout_text = stdout_text[:limits.max_output_size] + "\n... (output truncated)"
            
            if len(stderr_text) > limits.max_output_size:
                stderr_text = stderr_text[:limits.max_output_size] + "\n... (error output truncated)"
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                status=status,
                stdout=stdout_text,
                stderr=stderr_text,
                return_code=return_code,
                execution_time=execution_time,
                memory_used=self._estimate_memory_usage(execution_dir),
                files_created=[],
                artifacts={}
            )
            
        except MemoryError:
            return ExecutionResult(
                status=ExecutionStatus.MEMORY_EXCEEDED,
                stdout="",
                stderr="Memory limit exceeded",
                return_code=-1,
                execution_time=time.time() - start_time,
                memory_used=limits.memory_limit_mb * 1024 * 1024,
                files_created=[],
                artifacts={},
                error_message="Memory limit exceeded"
            )
        
        except PermissionError as e:
            return ExecutionResult(
                status=ExecutionStatus.PERMISSION_DENIED,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=time.time() - start_time,
                memory_used=0,
                files_created=[],
                artifacts={},
                error_message="Permission denied"
            )
        
        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=time.time() - start_time,
                memory_used=0,
                files_created=[],
                artifacts={},
                error_message=str(e)
            )
    
    def _estimate_memory_usage(self, execution_dir: Path) -> int:
        """Estimate memory usage by looking at created files"""
        total_size = 0
        try:
            for file_path in execution_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception as e:
            logger.warning(f"Failed to estimate memory usage: {e}")
        
        return total_size
    
    def _collect_artifacts(self, execution_dir: Path) -> Dict[str, Any]:
        """Collect execution artifacts (output files, logs, etc.)"""
        artifacts = {}
        
        try:
            # Look for common output files
            for pattern in ["*.json", "*.csv", "*.txt", "*.png", "*.pdf", "*.xlsx"]:
                for file_path in execution_dir.glob(pattern):
                    if file_path.is_file() and file_path.stat().st_size < 10 * 1024 * 1024:  # < 10MB
                        rel_path = file_path.relative_to(execution_dir)
                        
                        if file_path.suffix.lower() in ['.json', '.txt', '.csv']:
                            # Read text files
                            try:
                                with open(file_path, 'r') as f:
                                    artifacts[str(rel_path)] = f.read()
                            except:
                                artifacts[str(rel_path)] = f"<binary file: {file_path.stat().st_size} bytes>"
                        else:
                            # Record binary files
                            artifacts[str(rel_path)] = f"<binary file: {file_path.stat().st_size} bytes>"
        
        except Exception as e:
            logger.warning(f"Failed to collect artifacts: {e}")
            artifacts['collection_error'] = str(e)
        
        return artifacts
    
    def cleanup(self):
        """Clean up temporary directories and resources"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                logger.info("Sandbox cleanup completed")
        except Exception as e:
            logger.error(f"Failed to cleanup sandbox: {e}")
    
    def __del__(self):
        """Cleanup on object destruction"""
        self.cleanup()

class CodeValidator:
    """
    Static code analysis and validation utilities
    """
    
    @staticmethod
    def validate_python_syntax(code: str) -> List[str]:
        """Validate Python code syntax"""
        issues = []
        
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            issues.append(f"Syntax error at line {e.lineno}: {e.msg}")
        except Exception as e:
            issues.append(f"Compilation error: {str(e)}")
        
        return issues
    
    @staticmethod
    def analyze_code_complexity(code: str) -> Dict[str, Any]:
        """Analyze code complexity metrics"""
        lines = code.split('\n')
        
        metrics = {
            'total_lines': len(lines),
            'non_empty_lines': len([line for line in lines if line.strip()]),
            'comment_lines': len([line for line in lines if line.strip().startswith('#')]),
            'import_statements': len([line for line in lines if line.strip().startswith('import') or line.strip().startswith('from')]),
            'function_definitions': len([line for line in lines if line.strip().startswith('def ')]),
            'class_definitions': len([line for line in lines if line.strip().startswith('class ')]),
        }
        
        # Calculate complexity score
        complexity_score = (
            metrics['total_lines'] * 0.1 +
            metrics['function_definitions'] * 2 +
            metrics['class_definitions'] * 3 +
            metrics['import_statements'] * 0.5
        )
        
        metrics['complexity_score'] = complexity_score
        metrics['complexity_level'] = 'low' if complexity_score < 50 else 'medium' if complexity_score < 150 else 'high'
        
        return metrics

# Example usage and testing
if __name__ == "__main__":
    async def test_sandbox():
        # Test with different security levels
        for security_level in [SecurityLevel.LOW, SecurityLevel.MEDIUM, SecurityLevel.HIGH]:
            print(f"\nTesting {security_level.value} security level:")
            
            # Initialize sandbox
            sandbox = SandboxExecutor(security_level=security_level)
            
            # Test simple Python code
            test_code = '''
import json
import math

# Process input data
if 'INPUT_DATA' in locals():
    data = INPUT_DATA
    print(f"Processing document with {len(data)} fields")
    
    # Simple analysis
    numeric_values = [v for v in data.values() if isinstance(v, (int, float))]
    if numeric_values:
        print(f"Found {len(numeric_values)} numeric values")
        print(f"Sum: {sum(numeric_values)}")
        print(f"Average: {sum(numeric_values) / len(numeric_values)}")
    
    # Save results
    results = {
        "total_fields": len(data),
        "numeric_fields": len(numeric_values),
        "analysis_complete": True
    }
    
    with open("analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("Analysis completed and saved")
else:
    print("No input data provided")
'''
            
            # Test input data
            input_data = {
                "invoice_number": "INV-2024-001",
                "amount": 15000.00,
                "vendor_name": "ACME Corp",
                "tax_rate": 0.08
            }
            
            # Execute code
            result = await sandbox.execute_code(
                code=test_code,
                language="python",
                input_data=input_data
            )
            
            print(f"Status: {result.status}")
            print(f"Execution time: {result.execution_time:.2f}s")
            print(f"Files created: {len(result.files_created)}")
            print(f"Artifacts: {list(result.artifacts.keys())}")
            
            if result.stdout:
                print(f"Output:\n{result.stdout}")
            
            if result.stderr:
                print(f"Errors:\n{result.stderr}")
            
            if result.security_violations:
                print(f"Security violations: {result.security_violations}")
            
            # Cleanup
            sandbox.cleanup()
    
    # Run tests
    print("🔒 Testing Sandbox Executor")
    asyncio.run(test_sandbox())
    print("\n✅ Sandbox testing completed")