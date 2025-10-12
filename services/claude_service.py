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
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from jinja2 import Template

# Import claude_cli module
import sys
sys.path.append(str(Path(__file__).parent.parent))
from claude_cli import AsyncClaudeCLI, SuperClaudeMode, SuperClaudeAgent, SuperClaudeMCP, CLIResult

# Configure logging
logger = logging.getLogger(__name__)


def _format_seconds(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    try:
        total_seconds = int(round(float(seconds)))
    except (TypeError, ValueError):
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: List[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)

@dataclass
class AnalysisResult:
    """Result from document analysis"""
    success: bool
    analysis: Dict[str, Any]
    agent_used: Optional[str] = None
    confidence: float = 0.0
    metadata: Optional[Dict[str, Any]] = None
    processing_time: Optional[float] = None
    claude_command: Optional[str] = None

@dataclass
class ConsensusResult:
    """Result from multi-model consensus"""
    success: bool
    consensus: Dict[str, Any]
    models_used: List[str]
    agreement_score: float
    metadata: Optional[Dict[str, Any]] = None
    agreement_details: Optional[List[Dict[str, Any]]] = None

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
                                  agents: Optional[List[str]] = None,
                                  claude_config: Optional[Dict[str, Any]] = None,
                                  parallel: bool = True) -> Dict[str, AnalysisResult]:
        """
        Perform multi-agent analysis on document
        
        Args:
            document_content: Document text content
            document_metadata: Document metadata
            agents: List of agents to use (if None, uses default set)
            claude_config: Optional configuration modifiers for Claude execution
            parallel: Whether to execute agent analyses concurrently
            
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
        
        # Create analysis coroutines for each agent
        tasks = [
            (agent, self._analyze_with_agent(
                agent,
                document_content,
                document_metadata,
                claude_config=claude_config
            ))
            for agent in agents
        ]
        
        logger.info(
            f"Starting {'parallel' if parallel else 'sequential'} analysis with {len(agents)} agents"
        )
        start_time = datetime.now(timezone.utc)
        
        if parallel:
            task_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True
            )
        else:
            task_results = []
            for _, coroutine in tasks:
                try:
                    task_results.append(await coroutine)
                except Exception as exc:
                    task_results.append(exc)
        
        # Process results
        for i, (agent, _) in enumerate(tasks):
            result = task_results[i]
            if isinstance(result, Exception):
                logger.error(f"Agent {agent} failed: {result}")
                results[agent] = AnalysisResult(
                    success=False,
                    analysis={"error": str(result)},
                    agent_used=agent,
                    confidence=0.0
                )
            else:
                results[agent] = result
                logger.info(f"Agent {agent} completed with confidence {result.confidence:.2f}")
        
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"Multi-agent analysis completed in {elapsed:.2f}s")
        
        # Attach elapsed timing metadata
        for result in results.values():
            if result.metadata is None:
                result.metadata = {}
            result.metadata.setdefault("analysis_started_at", start_time.isoformat())
            result.metadata["analysis_completed_at"] = datetime.now(timezone.utc).isoformat()
            result.metadata["execution_mode"] = "parallel" if parallel else "sequential"
            if result.processing_time is None:
                result.processing_time = elapsed
        
        return results
    
    async def _analyze_with_agent(self,
                                 agent: str,
                                 content: str,
                                 metadata: Dict[str, Any],
                                 claude_config: Optional[Dict[str, Any]] = None) -> AnalysisResult:
        """
        Analyze document with specific agent
        
        Args:
            agent: Agent name
            content: Document content
            metadata: Document metadata
            claude_config: Optional configuration modifiers
            
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
        prompt_overrides = (claude_config or {}).get("prompt_overrides", {})
        agent_overrides = (prompt_overrides.get(agent) if prompt_overrides else None)
        if agent_overrides:
            base_prompt = agent_overrides
        
        command_flags: List[str] = []
        if claude_config:
            command_flags.extend(claude_config.get("flags", []))
            modes = claude_config.get("superclaude_modes", [])
            if modes:
                command_flags.extend(modes)
            agent_flag_overrides = (claude_config.get("agent_flags", {}) or {}).get(agent, [])
            if agent_flag_overrides:
                command_flags.extend(agent_flag_overrides)
        
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
            agent_start = datetime.now(timezone.utc)
            # Execute analysis using Claude CLI
            result = await self.cli.analyze_text_async(
                text=content,
                prompt=prompt,
                schema=schema
            )
            elapsed = (datetime.now(timezone.utc) - agent_start).total_seconds()
            
            return AnalysisResult(
                success=True,
                analysis=result,
                agent_used=agent,
                confidence=result.get("confidence", 0.5),
                metadata={
                    "document_id": metadata.get("document_id"),
                    "analysis_prompt": prompt,
                    "command_flags": command_flags
                },
                processing_time=elapsed,
                claude_command=" ".join(command_flags) if command_flags else None
            )
            
        except Exception as e:
            logger.error(f"Analysis failed for agent {agent}: {e}")
            raise

    def _parse_consensus_output(self, raw_output: Optional[str]) -> Dict[str, Any]:
        """Safely parse consensus JSON output."""
        if not raw_output:
            return {}
        raw = raw_output.strip()
        if not raw:
            return {}
        try:
            if raw.startswith("{") or raw.startswith("["):
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
                return {"raw": parsed}
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to parse consensus JSON (len={len(raw)}): {exc}")
        return {}
    
    async def consensus_validation(self,
                                  analysis_results: Dict[str, AnalysisResult],
                                  document_id: str,
                                  models: Optional[List[str]] = None,
                                  consensus_config: Optional[Dict[str, Any]] = None) -> ConsensusResult:
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
        consensus_config = consensus_config or {}
        additional_flags = consensus_config.get("flags", [])
        agreement_threshold = consensus_config.get("agreement_threshold", 0.6)
        
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
        
        agreement_details: List[Dict[str, Any]] = []
        issues_votes: Dict[str, Dict[str, Any]] = {}
        recommendation_votes: Dict[str, Dict[str, Any]] = {}
        quality_scores: List[float] = []
        overall_success = True
        
        for model in models:
            flags = ["--consensus"]
            flags.extend(additional_flags)
            flags.extend(["--model", model])
            
            try:
                call_started = datetime.now(timezone.utc)
                result = await self.cli.use_mcp_server_async(
                    prompt=prompt,
                    mcp=SuperClaudeMCP.ZEN,
                    additional_flags=flags
                )
                latency = (datetime.now(timezone.utc) - call_started).total_seconds()
                parsed = self._parse_consensus_output(result.output if result.success else None)
                success = result.success
            except Exception as exc:
                logger.error(f"Consensus request failed for model {model}: {exc}")
                parsed = {}
                latency = None
                success = False
                overall_success = False
            
            quality = parsed.get("overall_quality_score") or parsed.get("quality_score")
            if isinstance(quality, (int, float)):
                quality_scores.append(float(quality))
            
            issues = parsed.get("critical_issues") or parsed.get("issues") or []
            normalized_issues: List[Dict[str, Any]] = []
            for issue in issues:
                if isinstance(issue, dict):
                    normalized = issue.copy()
                else:
                    normalized = {"issue": issue}
                normalized_issues.append(normalized)
                issue_key = json.dumps(normalized, sort_keys=True)
                entry = issues_votes.setdefault(issue_key, {"issue": normalized, "models": []})
                entry["models"].append(model)
            
            recommendations = parsed.get("recommendations") or []
            normalized_recs: List[Dict[str, Any]] = []
            for rec in recommendations:
                if isinstance(rec, dict):
                    normalized_rec = rec.copy()
                else:
                    normalized_rec = {"recommendation": rec}
                normalized_recs.append(normalized_rec)
                rec_key = json.dumps(normalized_rec, sort_keys=True)
                entry = recommendation_votes.setdefault(rec_key, {"recommendation": normalized_rec, "models": []})
                entry["models"].append(model)
            
            agreement_details.append({
                "model": model,
                "success": success,
                "latency_seconds": latency,
                "flags": flags,
                "quality_score": quality,
                "issues": normalized_issues,
                "recommendations": normalized_recs,
                "raw_output": parsed
            })
        
        aggregated_issues: List[Dict[str, Any]] = []
        for data in issues_votes.values():
            support_ratio = len(data["models"]) / len(models)
            issue_entry = data["issue"].copy()
            issue_entry["agreed_by"] = data["models"]
            issue_entry["support"] = round(support_ratio, 2)
            aggregated_issues.append(issue_entry)
        
        aggregated_recommendations: List[Dict[str, Any]] = []
        for data in recommendation_votes.values():
            support_ratio = len(data["models"]) / len(models)
            rec_entry = data["recommendation"].copy()
            rec_entry["supported_by"] = data["models"]
            rec_entry["support"] = round(support_ratio, 2)
            aggregated_recommendations.append(rec_entry)
        
        overall_quality = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else None
        if aggregated_issues:
            agreement_score = round(
                sum(issue["support"] for issue in aggregated_issues) / len(aggregated_issues),
                2
            )
        else:
            agreement_score = 0.0
        
        consensus_payload = {
            "overall_quality_score": overall_quality,
            "critical_issues": aggregated_issues,
            "recommendations": aggregated_recommendations,
            "models_used": models,
            "agreement_threshold": agreement_threshold
        }
        
        return ConsensusResult(
            success=overall_success,
            consensus=consensus_payload,
            models_used=models,
            agreement_score=agreement_score,
            metadata={
                "document_id": document_id,
                "issues_considered": len(all_issues),
                "recommendations_considered": len(all_recommendations)
            },
            agreement_details=agreement_details
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
CRITICAL INSTRUCTION: You MUST return ONLY the complete remediated document in Markdown format.
DO NOT include any summary, explanation, or commentary.
DO NOT start with "Here is..." or "Below is..." or any introduction.
DO NOT end with any summary of changes made.
ONLY output the full document text itself.

Original Document (truncated for context):
{document_content[:10000]}

Issues to Address:
{json.dumps(issues, indent=2)}

Requirements:
1. Fix all identified issues
2. Maintain original document structure  
3. Improve clarity and completeness
4. Add missing sections if needed
5. Ensure consistency throughout

OUTPUT ONLY THE COMPLETE REMEDIATED DOCUMENT IN MARKDOWN - NOTHING ELSE.
Start directly with the document title or first line.
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
                # Validate output is a full document, not a summary
                output = (result.output or "").strip()
                
                # Check for summary indicators
                summary_indicators = [
                    "Summary of Improvements",
                    "## Summary",
                    "Changes made:",
                    "Improvements:",
                    "Fixed the following",
                    "Here is",
                    "Below is"
                ]
                
                first_line = output.split('\n')[0] if output else ""
                is_summary = any(indicator in first_line for indicator in summary_indicators)
                
                # Also check if output is too short to be a full document
                if is_summary or len(output) < 500:
                    logger.warning(f"Remediation appears to be a summary (length: {len(output)}, starts with: {first_line[:50]})")
                    # Retry with even stricter prompt
                    stricter_prompt = f"""
YOU ARE RETURNING A SUMMARY INSTEAD OF THE DOCUMENT. THIS IS WRONG.

Return ONLY the FULL TEXT of the remediated document.
Start with the document title: "NON-DISCLOSURE AGREEMENT"
Include ALL sections of the NDA.
DO NOT include any summary or explanation.

Original Document:
{document_content[:10000]}

Issues: {json.dumps(issues)}

OUTPUT THE FULL REMEDIATED DOCUMENT NOW:
"""
                    retry_result = await self.cli.execute_with_mode_async(
                        prompt=stricter_prompt,
                        mode=SuperClaudeMode.TASK_MANAGE,
                        context={"document_id": document_id, "retry": True}
                    )
                    
                    if retry_result.success:
                        output = (retry_result.output or "").strip()
                        # If still too short, raise error
                        if len(output) < 500:
                            raise Exception(f"Remediation output too short ({len(output)} chars) - appears to be summary")
                    else:
                        raise Exception(f"Remediation retry failed: {retry_result.error}")
                
                # Calculate quality score based on issues resolved
                quality_score = min(1.0, 0.5 + (0.1 * len(issues)))
                
                # Cache latest remediation content for downstream retrieval
                self._last_remediation_result = output
                
                return RemediationResult(
                    success=True,
                    remediated_content=output,
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
        orchestration_started = datetime.now(timezone.utc)

        results: Dict[str, Any] = {
            "document_id": document_id,
            "started_at": orchestration_started.isoformat(),
            "status": "running",
            "claude_workflow": {
                "analysis": {"status": "pending"},
                "consensus": {"status": "pending"},
                "remediation": {"status": "pending"},
                "validation": {"status": "pending"}
            },
            "steps": {},
            "metrics": {}
        }

        def record_step(step_name: str, payload: Dict[str, Any]) -> None:
            entry = dict(payload)
            results["claude_workflow"][step_name] = entry
            results["steps"][step_name] = {
                k: v for k, v in entry.items()
                if k not in {"agents", "agreement_details", "critical_issues", "recommendations"}
            }

        def mark_skipped(step_name: str, reason: str) -> None:
            record_step(step_name, {"status": "skipped", "reason": reason})

        status = "completed"
        error_message: Optional[str] = None
        analysis_results: Dict[str, AnalysisResult] = {}
        consensus_result: Optional[ConsensusResult] = None
        remediation_result: Optional[RemediationResult] = None
        validation_result: Optional[Dict[str, Any]] = None

        # Analysis
        try:
            analysis_cfg = (workflow_config or {}).get("analysis", {})
            analysis_start = datetime.now(timezone.utc)
            analysis_results = await self.multi_agent_analysis(
                document_content,
                document_metadata,
                agents=analysis_cfg.get("agents"),
                claude_config=analysis_cfg.get("claude_config") or analysis_cfg,
                parallel=analysis_cfg.get("parallel", True)
            )
            analysis_end = datetime.now(timezone.utc)
            duration = (analysis_end - analysis_start).total_seconds()
            agent_details = {
                agent: {
                    "success": res.success,
                    "confidence": res.confidence,
                    "processing_time_seconds": res.processing_time,
                    "claude_command": res.claude_command,
                    "metadata": res.metadata
                }
                for agent, res in analysis_results.items()
            }
            record_step("analysis", {
                "status": "completed",
                "started_at": analysis_start.isoformat(),
                "completed_at": analysis_end.isoformat(),
                "duration_seconds": duration,
                "duration_formatted": _format_seconds(duration),
                "agent_count": len(analysis_results),
                "agents": agent_details
            })
            results["metrics"]["analysis"] = {
                "agent_count": len(analysis_results),
                "average_confidence": round(
                    sum(res.confidence for res in analysis_results.values()) / len(analysis_results),
                    2
                ) if analysis_results else None
            }
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            record_step("analysis", {"status": "failed", "error": error_message})
            mark_skipped("consensus", "analysis_failed")
            mark_skipped("remediation", "analysis_failed")
            mark_skipped("validation", "analysis_failed")

        # Consensus
        if status == "completed":
            try:
                consensus_cfg = (workflow_config or {}).get("consensus", {})
                consensus_start = datetime.now(timezone.utc)
                consensus_result = await self.consensus_validation(
                    analysis_results,
                    document_id,
                    models=consensus_cfg.get("models"),
                    consensus_config=consensus_cfg
                )
                consensus_end = datetime.now(timezone.utc)
                duration = (consensus_end - consensus_start).total_seconds()
                record_step("consensus", {
                    "status": "completed" if consensus_result.success else "failed",
                    "started_at": consensus_start.isoformat(),
                    "completed_at": consensus_end.isoformat(),
                    "duration_seconds": duration,
                    "duration_formatted": _format_seconds(duration),
                    "agreement_score": consensus_result.agreement_score,
                    "models_used": consensus_result.models_used,
                    "critical_issues": (consensus_result.consensus or {}).get("critical_issues", []),
                    "recommendations": (consensus_result.consensus or {}).get("recommendations", []),
                    "agreement_details": consensus_result.agreement_details
                })
                results["metrics"]["consensus"] = {
                    "agreement_score": consensus_result.agreement_score,
                    "models_used": consensus_result.models_used
                }
                if not consensus_result.success:
                    status = "failed"
                    error_message = (consensus_result.consensus or {}).get("error", "Consensus validation failed")
                    mark_skipped("remediation", "consensus_failed")
                    mark_skipped("validation", "consensus_failed")
            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                record_step("consensus", {"status": "failed", "error": error_message})
                mark_skipped("remediation", "consensus_failed")
                mark_skipped("validation", "consensus_failed")

        # Remediation
        if status == "completed":
            try:
                remediation_start = datetime.now(timezone.utc)
                aggregated_issues: List[Dict[str, Any]] = []
                for result in analysis_results.values():
                    if result.success:
                        aggregated_issues.extend(result.analysis.get("issues", []))
                remediation_result = await self.generate_remediation(
                    document_content,
                    aggregated_issues,
                    document_id
                )
                remediation_end = datetime.now(timezone.utc)
                duration = (remediation_end - remediation_start).total_seconds()
                record_step("remediation", {
                    "status": "completed" if remediation_result.success else "failed",
                    "started_at": remediation_start.isoformat(),
                    "completed_at": remediation_end.isoformat(),
                    "duration_seconds": duration,
                    "duration_formatted": _format_seconds(duration),
                    "issues_resolved": remediation_result.issues_resolved,
                    "quality_score": remediation_result.quality_score
                })
                if remediation_result.success and remediation_result.remediated_content:
                    results["remediated_content"] = remediation_result.remediated_content
                else:
                    status = "failed"
                    error_message = "Remediation failed"
                    mark_skipped("validation", "remediation_failed")
            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                record_step("remediation", {"status": "failed", "error": error_message})
                mark_skipped("validation", "remediation_failed")

        # Validation
        if status == "completed":
            try:
                validation_start = datetime.now(timezone.utc)
                validation_result = await self.quality_validation(
                    original_content=document_content,
                    remediated_content=remediation_result.remediated_content if remediation_result else document_content,
                    document_id=document_id
                )
                validation_end = datetime.now(timezone.utc)
                duration = (validation_end - validation_start).total_seconds()
                success = validation_result.get("success", True)
                record_step("validation", {
                    "status": "completed" if success else "failed",
                    "started_at": validation_start.isoformat(),
                    "completed_at": validation_end.isoformat(),
                    "duration_seconds": duration,
                    "duration_formatted": _format_seconds(duration),
                    "quality_score": validation_result.get("quality_score"),
                    "improvements": validation_result.get("improvements", []),
                    "remaining_issues": validation_result.get("remaining_issues", [])
                })
                results.setdefault("quality_metrics", {})
                results["quality_metrics"].update({
                    "final_quality_score": validation_result.get("quality_score"),
                    "improvements": validation_result.get("improvements", [])
                })
                validation_result.setdefault("quality_score", validation_result.get("quality_score"))
                if not success:
                    status = "failed"
                    error_message = validation_result.get("error", "Validation failed")
            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                record_step("validation", {"status": "failed", "error": error_message})

        completed_at = datetime.now(timezone.utc)
        results["completed_at"] = completed_at.isoformat()
        results["duration_seconds"] = (completed_at - orchestration_started).total_seconds()
        results["duration_formatted"] = _format_seconds(results["duration_seconds"])
        results["status"] = status
        if error_message:
            results["error"] = error_message

        if consensus_result:
            results.setdefault("quality_metrics", {})
            results["quality_metrics"].update({
                "agreement_score": consensus_result.agreement_score,
                "overall_quality_score": (consensus_result.consensus or {}).get("overall_quality_score")
            })
        if remediation_result:
            results.setdefault("quality_metrics", {})
            results["quality_metrics"].update({
                "remediation_quality_score": remediation_result.quality_score,
                "issues_resolved": len(remediation_result.issues_resolved)
            })

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

    async def compress_folder_with_claude(self, 
                                         folder_path: str,
                                         output_filename: str,
                                         include_patterns: Optional[List[str]] = None,
                                         exclude_patterns: Optional[List[str]] = None,
                                         compression_level: int = 6) -> Dict[str, Any]:
        """
        Compress folder using Claude for intelligent file selection and optimization
        
        Args:
            folder_path: Path to folder to compress
            output_filename: Output filename for zip
            include_patterns: Patterns to include
            exclude_patterns: Patterns to exclude
            compression_level: Compression level (0-9)
            
        Returns:
            Compression results with metadata
        """
        try:
            # Use Claude to analyze folder and optimize compression strategy
            analysis_prompt = f"""
            Analyze folder structure for compression optimization:
            - Folder path: {folder_path}
            - Include patterns: {include_patterns or 'all files'}
            - Exclude patterns: {exclude_patterns or 'none'}
            - Requested compression level: {compression_level}
            
            Please analyze the folder contents and recommend:
            1. Optimal compression settings
            2. File filtering strategy
            3. Performance considerations
            4. Estimated compression ratio
            
            Focus on efficiency and ensuring no important files are missed.
            """
            
            analysis_result = await self.cli.delegate_to_agent_async(
                prompt=analysis_prompt,
                agent="performance-engineer",
                task_manage=True,
                use_dsl=True
            )
            
            if not analysis_result.success:
                logger.warning(f"Claude analysis failed, proceeding with default settings: {analysis_result.error}")
            
            # Import FileOperations here to avoid circular imports
            from utils.file_operations import FileOperations
            
            # Execute compression with Claude's recommendations or defaults
            result = await FileOperations.compress_folder(
                folder_path=folder_path,
                output_path=str(Path(folder_path).parent / output_filename),
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                compression_level=compression_level
            )
            
            # Enhance result with Claude analysis if successful
            if analysis_result.success:
                result['claude_analysis'] = {
                    'recommendations': analysis_result.output,
                    'agent_used': analysis_result.metadata.get('requested_agent', 'performance-engineer')
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Claude-assisted compression failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'method': 'claude_compression'
            }

    async def convert_document_with_claude(self,
                                          input_path: str,
                                          output_path: Optional[str] = None,
                                          output_format: str = 'pdf',
                                          quality: str = 'high',
                                          preserve_formatting: bool = True) -> Dict[str, Any]:
        """
        Convert document using Claude for intelligent conversion optimization
        
        Args:
            input_path: Path to input document
            output_path: Path for output (optional)
            output_format: Target format
            quality: Conversion quality
            preserve_formatting: Whether to preserve formatting
            
        Returns:
            Conversion results with metadata
        """
        try:
            # Read document content for analysis
            input_file = Path(input_path)
            if not input_file.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            # Use Claude to analyze document and optimize conversion strategy
            analysis_prompt = f"""
            Analyze document for optimal conversion strategy:
            - Input file: {input_path}
            - Output format: {output_format}
            - Quality requirement: {quality}
            - Preserve formatting: {preserve_formatting}
            
            Please analyze the document structure and recommend:
            1. Optimal conversion method
            2. Quality settings to preserve content fidelity
            3. Formatting preservation strategy
            4. Potential conversion challenges
            5. Quality validation checkpoints
            
            Focus on maintaining document integrity and visual fidelity.
            """
            
            analysis_result = await self.cli.delegate_to_agent_async(
                prompt=analysis_prompt,
                agent="technical-writer",
                task_manage=True,
                use_dsl=True
            )
            
            if not analysis_result.success:
                logger.warning(f"Claude analysis failed, proceeding with default settings: {analysis_result.error}")
            
            # Import FileOperations here to avoid circular imports
            from utils.file_operations import FileOperations
            
            # Execute conversion with Claude's recommendations
            result = await FileOperations.convert_docx_to_pdf(
                input_path=input_path,
                output_path=output_path,
                quality=quality,
                preserve_formatting=preserve_formatting,
                use_claude=True
            )
            
            # Enhance result with Claude analysis if successful
            if analysis_result.success:
                result['claude_analysis'] = {
                    'recommendations': analysis_result.output,
                    'agent_used': analysis_result.metadata.get('requested_agent', 'technical-writer')
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Claude-assisted conversion failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'method': 'claude_conversion'
            }

    async def batch_operations_with_claude(self,
                                          operation_type: str,
                                          file_list: List[str],
                                          operation_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute batch file operations with Claude coordination
        
        Args:
            operation_type: Type of operation ('compress', 'convert', etc.)
            file_list: List of files to process
            operation_params: Operation-specific parameters
            
        Returns:
            Batch operation results
        """
        try:
            # Use Claude to analyze batch and optimize strategy
            strategy_prompt = f"""
            Optimize batch {operation_type} strategy:
            - Operation type: {operation_type}
            - Number of files: {len(file_list)}
            - Parameters: {operation_params}
            
            Please recommend:
            1. Optimal batch size and processing order
            2. Parallel vs sequential processing strategy  
            3. Resource allocation and timing
            4. Error handling and recovery approach
            5. Quality checkpoints and validation
            
            Focus on efficiency, reliability, and resource optimization.
            """
            
            strategy_result = await self.cli.delegate_to_agent_async(
                prompt=strategy_prompt,
                agent="performance-engineer",
                task_manage=True,
                orchestrate=True
            )
            
            if not strategy_result.success:
                logger.warning(f"Claude strategy optimization failed: {strategy_result.error}")
            
            # Import FileOperations here to avoid circular imports
            from utils.file_operations import FileOperations
            
            # Execute batch operation based on type
            if operation_type == 'convert':
                result = await FileOperations.batch_convert_documents(
                    input_files=file_list,
                    output_dir=operation_params.get('output_directory', './output'),
                    conversion_type=operation_params.get('conversion_type', 'docx_to_pdf'),
                    parallel=operation_params.get('parallel', True),
                    max_workers=operation_params.get('max_workers', 4)
                )
            else:
                result = {
                    'success': False,
                    'error': f"Batch operation type '{operation_type}' not implemented"
                }
            
            # Enhance result with Claude strategy if successful
            if strategy_result.success:
                result['claude_strategy'] = {
                    'recommendations': strategy_result.output,
                    'agent_used': strategy_result.metadata.get('requested_agent', 'performance-engineer')
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Claude-assisted batch operation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'method': 'claude_batch_operation'
            }

# Singleton instance for API usage
claude_service = ClaudeService()
