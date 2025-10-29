#!/usr/bin/env python3
"""
Centralized environment-driven configuration for DocAutomate.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional


class Settings:
    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("DOC_AUTOMATE_API_KEY")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./state/docautomate.db")
        self.claude_api_base: Optional[str] = os.getenv("CLAUDE_API_BASE")
        self.claude_api_key: Optional[str] = os.getenv("CLAUDE_API_KEY")
        self.enable_local_fallbacks: bool = os.getenv("CLAUDE_ENABLE_LOCAL_FALLBACKS", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.log_json: bool = os.getenv("DOC_AUTOMATE_LOG_JSON", "false").lower() in ("1", "true", "yes", "on")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
