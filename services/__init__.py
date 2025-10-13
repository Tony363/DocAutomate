"""Services package for DocAutomate."""

from . import claude_service as claude_service_module

claude_service = claude_service_module
claude_service_instance = claude_service_module.claude_service
ClaudeService = claude_service_module.ClaudeService

__all__ = [
    "claude_service",
    "claude_service_instance",
    "ClaudeService",
]
