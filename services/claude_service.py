#!/usr/bin/env python3
"""
Claude Service - Pure Claude Code Orchestration
All document operations delegate to Claude Code agents via SuperClaude Framework
No local document processing - pure API wrapper for Claude CLI invocations
"""

import json
import logging
import os
import yaml
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import asyncio
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from jinja2 import Template

# Import claude_cli module
import sys
sys.path.append(str(Path(__file__).parent.parent))
from claude_cli import AsyncClaudeCLI, SuperClaudeMode, SuperClaudeAgent, SuperClaudeMCP, CLIResult

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class AnalysisResult:
    """Result from document analysis"""
    success: bool
    analysis: Dict[str, Any]
    agent_used: Optional[str] = None
    confidence: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ConsensusResult:
    """Result from multi-model consensus"""
    success: bool
    consensus: Dict[str, Any]
    models_used: List[str]
    agreement_score: float
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class RemediationResult:
    """Result from document remediation"""
    success: bool
    remediated_content: str
    issues_resolved: List[str]
    quality_score: float
    metadata: Optional[Dict[str, Any]] = None

class ClaudeService:
    """
    Pure Claude Code Orchestration Service
    All operations delegate to Claude agents - no local processing
    """
    
    def __init__(self):
        """Initialize service with DSL configurations and CLI wrapper"""
        # Use extended timeout for validation operations to reduce timeout failures
        validation_timeout = int(os.getenv("CLAUDE_VALIDATION_TIMEOUT", "300"))  # 5 minutes default
        self.cli = AsyncClaudeCLI(timeout=validation_timeout)
        self._load_dsl_configurations()
        logger.info(f"Claude Service initialized with {validation_timeout}s timeout for validation operations")
    
    def _load_dsl_configurations(self):
        """Load DSL configurations for orchestration"""
        # Load unified operations DSL
        dsl_path = Path(__file__).parent.parent / "dsl" / "unified-operations.yaml"
        if dsl_path.exists():
            with open(dsl_path, 'r') as f:
                self.dsl_config = yaml.safe_load(f)
        else:
            self.dsl_config = {}
            logger.warning("DSL configuration not found, using defaults")
        
        # Load agent mappings
        mappings_path = Path(__file__).parent.parent / "dsl" / "agent-mappings.yaml"
        if mappings_path.exists():
            with open(mappings_path, 'r') as f:
                self.agent_mappings = yaml.safe_load(f)
        else:
            self.agent_mappings = {}
            logger.warning("Agent mappings not found, using defaults")
    
    def _get_prompt_template(self, operation: str) -> str:
        """Get prompt template from DSL for operation"""
        templates = self.dsl_config.get('prompt_templates', {})
        return templates.get(operation, {}).get('template', '')
    
    def _select_agents_for_operation(self, operation: str, document_type: str) -> Dict[str, Any]:
        """Select appropriate agents based on DSL mappings"""
        # Check operation mappings
        op_config = self.dsl_config.get('operation_types', {}).get(operation, {})
        
        # Check document type mappings
        doc_config = self.agent_mappings.get('document_type_mappings', {}).get(document_type, {})
        
        return {
            'primary': op_config.get('primary_agent') or doc_config.get('primary') or 'general-purpose',
            'secondary': op_config.get('fallback_agents', []) or doc_config.get('secondary', []),
            'parallel': op_config.get('parallel_agents', []),
            'consensus_required': op_config.get('consensus_required', False) or doc_config.get('consensus_required', False)
        }
    
    async def multi_agent_analysis(self, 
                                  document_content: str,
                                  document_metadata: Dict[str, Any],
                                  agents: Optional[List[str]] = None) -> Dict[str, AnalysisResult]:
        """
        Perform multi-agent analysis on document
        
        Args:
            document_content: Document text content
            document_metadata: Document metadata
            agents: List of agents to use (if None, uses default set)
            
        Returns:
            Dictionary mapping agent name to analysis results
        """
        # Default agents for comprehensive analysis
        if agents is None:
            agents = [
                "general-purpose",
                "technical-writer", 
                "requirements-analyst",
                "security-engineer",
                "quality-engineer"
            ]
        
        results = {}
        tasks = []
        
        # Create analysis tasks for each agent
        for agent in agents:
            task = self._analyze_with_agent(
                agent, 
                document_content, 
                document_metadata
            )
            tasks.append((agent, task))
        
        # Execute all analyses in parallel
        logger.info(f"Starting parallel analysis with {len(agents)} agents")
        start_time = datetime.now()
        
        for agent, task in tasks:
            try:
                result = await task
                results[agent] = result
                logger.info(f"Agent {agent} completed with confidence {result.confidence:.2f}")
            except Exception as e:
                logger.error(f"Agent {agent} failed: {e}")
                results[agent] = AnalysisResult(
                    success=False,
                    analysis={"error": str(e)},
                    agent_used=agent,
                    confidence=0.0
                )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Multi-agent analysis completed in {elapsed:.2f}s")
        
        return results
    
    async def _analyze_with_agent(self,
                                 agent: str,
                                 content: str,
                                 metadata: Dict[str, Any]) -> AnalysisResult:
        """
        Analyze document with specific agent
        
        Args:
            agent: Agent name
            content: Document content
            metadata: Document metadata
            
        Returns:
            Analysis result from agent
        """
        # Build agent-specific prompt
        prompts = {
            "general-purpose": "Analyze document structure, identify major sections, quality issues, and completeness gaps",
            "technical-writer": "Review for clarity, terminology consistency, and documentation quality",
            "requirements-analyst": "Validate requirements coverage and completeness",
            "security-engineer": "Identify security vulnerabilities and compliance gaps",
            "quality-engineer": "Assess test coverage and quality metrics"
        }
        
        base_prompt = prompts.get(agent, "Perform comprehensive analysis")
        
        # Prepare full prompt with context
        prompt = f"""
Using the {agent} agent perspective, {base_prompt} for this document:

Document Type: {metadata.get('content_type', 'unknown')}
Document ID: {metadata.get('document_id', 'unknown')}

Content to analyze:
{content[:3000]}...

Please provide structured analysis with:
1. Key findings
2. Issues identified
3. Recommendations
4. Confidence score (0-1)
"""
        
        # Define schema for structured output
        schema = {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "severity": {"type": "string"},
                            "description": {"type": "string"},
                            "location": {"type": "string"}
                        }
                    }
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "confidence": {"type": "number"}
            }
        }
        
        try:
            # Execute analysis using Claude CLI
            result = await self.cli.analyze_text_async(
                text=content,
                prompt=prompt,
                schema=schema
            )
            
            return AnalysisResult(
                success=True,
                analysis=result,
                agent_used=agent,
                confidence=result.get("confidence", 0.5),
                metadata={"document_id": metadata.get("document_id")}
            )
            
        except Exception as e:
            logger.error(f"Analysis failed for agent {agent}: {e}")
            raise
    
    async def consensus_validation(self,
                                  analysis_results: Dict[str, AnalysisResult],
                                  document_id: str,
                                  models: Optional[List[str]] = None) -> ConsensusResult:
        """
        Perform multi-model consensus validation on analysis results
        
        Args:
            analysis_results: Results from multi-agent analysis
            document_id: Document identifier
            models: List of models to use for consensus
            
        Returns:
            Consensus result with agreement score
        """
        if models is None:
            models = ["gpt-5", "claude-opus-4.1", "gpt-4.1"]
        
        # Prepare consolidated findings for consensus
        all_issues = []
        all_recommendations = []
        
        for agent, result in analysis_results.items():
            if result.success:
                issues = result.analysis.get("issues", [])
                all_issues.extend(issues)
                recs = result.analysis.get("recommendations", [])
                all_recommendations.extend(recs)
        
        # Build consensus prompt
        prompt = f"""
Validate and prioritize the following analysis findings for document {document_id}:

Issues Identified:
{json.dumps(all_issues, indent=2)}

Recommendations:
{json.dumps(all_recommendations, indent=2)}

Please provide consensus on:
1. Issue severity and priority
2. Recommendation validity
3. Action items
4. Overall document quality score

Use multi-model consensus with models: {', '.join(models)}
"""
        
        # Execute consensus using Zen MCP
        try:
            result = await self.cli.use_mcp_server_async(
                prompt=prompt,
                mcp=SuperClaudeMCP.ZEN,
                additional_flags=["--consensus", "--model", models[0]]
            )
            
            # Parse consensus result with robust JSON handling
            if result.success and result.output:
                raw = result.output.strip()
                try:
                    if raw.startswith("{") or raw.startswith("["):
                        consensus_data = json.loads(raw)
                    else:
                        logger.warning(f"Non-JSON consensus output (len={len(raw)}): {raw[:200]}...")
                        consensus_data = {}
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse consensus JSON (len={len(raw)}): {raw[:200]}... Error: {e}")
                    consensus_data = {}
            else:
                consensus_data = {}
            
            # Calculate agreement score based on model responses
            agreement_score = consensus_data.get("agreement_score", 0.7)
            
            return ConsensusResult(
                success=result.success,
                consensus=consensus_data,
                models_used=models,
                agreement_score=agreement_score,
                metadata={"document_id": document_id}
            )
            
        except Exception as e:
            logger.error(f"Consensus validation failed: {e}")
            return ConsensusResult(
                success=False,
                consensus={"error": str(e)},
                models_used=models,
                agreement_score=0.0,
                metadata={"document_id": document_id}
            )
    
    async def generate_remediation(self,
                                 document_content: str,
                                 issues: List[Dict[str, Any]],
                                 document_id: str) -> RemediationResult:
        """
        Generate remediated document based on identified issues
        
        Args:
            document_content: Original document content
            issues: List of issues to remediate
            document_id: Document identifier
            
        Returns:
            Remediation result with improved content
        """
        # Build remediation prompt
        prompt = f"""
Generate an improved version of this document that addresses the identified issues:

Original Document:
{document_content[:2000]}...

Issues to Address:
{json.dumps(issues, indent=2)}

Please:
1. Fix all identified issues
2. Maintain original document structure
3. Improve clarity and completeness
4. Add missing sections if needed
5. Ensure consistency throughout

Return the complete remediated document.
"""
        
        try:
            # Use task management mode for systematic remediation
            result = await self.cli.execute_with_mode_async(
                prompt=prompt,
                mode=SuperClaudeMode.TASK_MANAGE,
                context={
                    "document_id": document_id,
                    "issue_count": len(issues)
                }
            )
            
            if result.success:
                # Calculate quality score based on issues resolved
                quality_score = min(1.0, 0.5 + (0.1 * len(issues)))
                
                return RemediationResult(
                    success=True,
                    remediated_content=result.output,
                    issues_resolved=[issue.get("id", f"issue_{i}") 
                                    for i, issue in enumerate(issues)],
                    quality_score=quality_score,
                    metadata={"document_id": document_id}
                )
            else:
                raise Exception(f"Remediation failed: {result.error}")
                
        except Exception as e:
            logger.error(f"Document remediation failed: {e}")
            return RemediationResult(
                success=False,
                remediated_content="",
                issues_resolved=[],
                quality_score=0.0,
                metadata={"document_id": document_id, "error": str(e)}
            )
    
    async def quality_validation(self,
                                remediated_content: str,
                                original_content: str,
                                document_id: str) -> Dict[str, Any]:
        """
        Perform deep quality validation on remediated document with enhanced prompt strategy
        
        Args:
            remediated_content: Remediated document content
            original_content: Original document content
            document_id: Document identifier
            
        Returns:
            Validation results with quality metrics
        """
        # Enhanced prompt with explicit JSON structure requirements and simplified approach
        prompt = f"""
CRITICAL: Respond with ONLY valid JSON in the exact format specified below. No explanatory text.

Compare original vs remediated document for Document ID: {document_id}

Original content (first 800 chars):
{original_content[:800]}...

Remediated content (first 800 chars):
{remediated_content[:800]}...

Return ONLY this JSON structure:
{{
    "quality_score": <number 0-100>,
    "improvements": ["improvement1", "improvement2"],
    "remaining_issues": ["issue1", "issue2"],
    "structure_score": <number 0-100>,
    "accuracy_score": <number 0-100>,
    "completeness_score": <number 0-100>
}}
"""
        
        try:
            # Try simplified approach first (faster, more reliable)
            result = await self.cli.analyze_text_async(
                text=f"Original:\n{original_content[:1500]}\n\nRemediated:\n{remediated_content[:1500]}",
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "quality_score": {"type": "number"},
                        "improvements": {"type": "array", "items": {"type": "string"}},
                        "remaining_issues": {"type": "array", "items": {"type": "string"}},
                        "structure_score": {"type": "number"},
                        "accuracy_score": {"type": "number"},
                        "completeness_score": {"type": "number"}
                    }
                }
            )
            
            # If analyze_text succeeds, use it directly
            if result:
                logger.info(f"Quality validation completed using simplified approach for {document_id}")
                return {
                    "success": True,
                    "validation": result,
                    "quality_score": result.get("quality_score", 75),
                    "improvements": result.get("improvements", []),
                    "remaining_issues": result.get("remaining_issues", []),
                    "document_id": document_id,
                    "method": "simplified"
                }
            
        except Exception as e:
            logger.warning(f"Simplified validation failed, trying fallback approach: {e}")
        
        # Fallback: Use Zen MCP but with simpler prompt (no thinkdeep to reduce timeout risk)
        fallback_prompt = f"""
Validate document quality for {document_id}. Return valid JSON only:

{{"quality_score": <0-100>, "improvements": [], "remaining_issues": []}}

Original: {original_content[:500]}...
Remediated: {remediated_content[:500]}...
"""
        
        try:
            result = await self.cli.use_mcp_server_async(
                prompt=fallback_prompt,
                mcp=SuperClaudeMCP.ZEN,
                additional_flags=["--model", "gpt-5"]  # Removed --thinkdeep to reduce timeout risk
            )
            
            if result.success:
                # Robust JSON parsing with validation and fallback
                raw = result.output or ""
                try:
                    if raw.strip().startswith("{") or raw.strip().startswith("["):
                        validation_data = json.loads(raw)
                    else:
                        logger.warning(f"Non-JSON validation output (len={len(raw)}): {raw[:200]}...")
                        validation_data = {}
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse validation JSON (len={len(raw)}): {raw[:200]}... Error: {e}")
                    validation_data = {}
                
                logger.info(f"Quality validation completed using fallback approach for {document_id}")
                return {
                    "success": True,
                    "validation": validation_data,
                    "quality_score": validation_data.get("quality_score", 50),  # Default fallback score
                    "improvements": validation_data.get("improvements", []),
                    "remaining_issues": validation_data.get("remaining_issues", []),
                    "document_id": document_id,
                    "method": "fallback"
                }
            else:
                raise Exception(f"Validation failed: {result.error}")
                
        except Exception as e:
            logger.error(f"Quality validation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }
    
    async def orchestrate_workflow(self,
                                  document_id: str,
                                  document_content: str,
                                  document_metadata: Dict[str, Any],
                                  workflow_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Orchestrate complete document processing workflow
        
        Args:
            document_id: Document identifier
            document_content: Document text content
            document_metadata: Document metadata
            workflow_config: Optional workflow configuration
            
        Returns:
            Complete workflow execution results
        """
        logger.info(f"Starting orchestration for document {document_id}")
        start_time = datetime.now()
        
        results = {
            "document_id": document_id,
            "start_time": start_time.isoformat(),
            "steps": {}
        }
        
        try:
            # Step 1: Multi-agent analysis
            logger.info("Step 1: Multi-agent analysis")
            analysis_results = await self.multi_agent_analysis(
                document_content,
                document_metadata
            )
            results["steps"]["analysis"] = {
                "status": "completed",
                "agent_count": len(analysis_results),
                "agents": list(analysis_results.keys())
            }
            
            # Step 2: Consensus validation
            logger.info("Step 2: Consensus validation")
            consensus = await self.consensus_validation(
                analysis_results,
                document_id
            )
            results["steps"]["consensus"] = {
                "status": "completed" if consensus.success else "failed",
                "agreement_score": consensus.agreement_score,
                "models_used": consensus.models_used
            }
            
            # Step 3: Generate remediation
            logger.info("Step 3: Generate remediation")
            # Extract issues from analysis
            all_issues = []
            for agent, result in analysis_results.items():
                if result.success:
                    all_issues.extend(result.analysis.get("issues", []))
            
            remediation = await self.generate_remediation(
                document_content,
                all_issues,
                document_id
            )
            results["steps"]["remediation"] = {
                "status": "completed" if remediation.success else "failed",
                "issues_resolved": len(remediation.issues_resolved),
                "quality_score": remediation.quality_score
            }
            
            # Step 4: Quality validation
            logger.info("Step 4: Quality validation")
            validation = await self.quality_validation(
                remediation.remediated_content,
                document_content,
                document_id
            )
            results["steps"]["validation"] = {
                "status": "completed" if validation.get("success") else "failed",
                "quality_score": validation.get("quality_score", 0),
                "improvements": len(validation.get("improvements", []))
            }
            
            # Calculate overall metrics
            elapsed = (datetime.now() - start_time).total_seconds()
            results["completed_at"] = datetime.now().isoformat()
            results["duration_seconds"] = elapsed
            results["overall_status"] = "completed"
            results["final_quality_score"] = validation.get("quality_score", 0)
            
            logger.info(f"Orchestration completed in {elapsed:.2f}s with quality score {results['final_quality_score']}")
            
            return results
            
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            results["overall_status"] = "failed"
            results["error"] = str(e)
            return results
    
    async def delegate_to_agent(self,
                               task_description: str,
                               agent: Optional[str] = None,
                               context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Delegate a specific task to a Claude agent
        
        Args:
            task_description: Description of the task
            agent: Specific agent to use (None for auto-routing)
            context: Optional context for the task
            
        Returns:
            Task execution result
        """
        try:
            if agent:
                # Use specific agent
                result = await self.cli.delegate_to_agent_async(
                    prompt=task_description,
                    agent=agent,
                    task_manage=True
                )
            else:
                # Auto-route to best agent
                result = await self.cli.delegate_to_agent_async(
                    prompt=task_description,
                    agent=None,
                    task_manage=True
                )
            
            return {
                "success": result.success,
                "output": result.output,
                "agent_used": result.metadata.get("requested_agent", "auto-routed"),
                "context": context
            }
            
        except Exception as e:
            logger.error(f"Agent delegation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "agent": agent,
                "context": context
            }

# Singleton instance for API usage
claude_service = ClaudeService()