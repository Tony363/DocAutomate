#!/usr/bin/env python3
"""
Smoke tests for agent routing to ensure specialized providers are selected.
"""

import pytest

from agent_providers import agent_registry


@pytest.mark.asyncio
async def test_route_backend_architect():
    provider, score = await agent_registry.route({
        "document_type": "api_documentation",
        "content_preview": "This API endpoint handles microservice traffic."
    })
    assert provider.name == "backend-architect"
    assert score.score >= 0.8


@pytest.mark.asyncio
async def test_route_frontend_architect():
    provider, score = await agent_registry.route({
        "document_type": "ui_spec",
        "content_preview": "Component design tokens and responsive layout requirements."
    })
    assert provider.name == "frontend-architect"
    assert score.score >= 0.8


@pytest.mark.asyncio
async def test_route_system_architect():
    provider, score = await agent_registry.route({
        "document_type": "architecture_design",
        "content_preview": "System context, scalability, availability considerations."
    })
    assert provider.name == "system-architect"
    assert score.score >= 0.8


@pytest.mark.asyncio
async def test_route_requirements_analyst():
    provider, score = await agent_registry.route({
        "document_type": "requirements_spec",
        "content_preview": "The system shall provide user stories and acceptance criteria."
    })
    assert provider.name == "requirements-analyst"
    assert score.score >= 0.8


@pytest.mark.asyncio
async def test_route_refactoring_expert():
    provider, score = await agent_registry.route({
        "document_type": "code_review",
        "content_preview": "Detected code smell and technical debt remediation plan."
    })
    assert provider.name == "refactoring-expert"
    assert score.score >= 0.8


@pytest.mark.asyncio
async def test_route_performance_engineer():
    provider, score = await agent_registry.route({
        "document_type": "performance_report",
        "content_preview": "Latency and throughput benchmarks with optimization notes."
    })
    assert provider.name == "performance-engineer"
    assert score.score >= 0.8


@pytest.mark.asyncio
async def test_route_legal_review():
    provider, score = await agent_registry.route({
        "document_type": "legal_contract",
        "content_preview": "This agreement defines liability clauses and jurisdiction."
    })
    assert provider.name == "legal-review"
    assert score.score >= 0.8
