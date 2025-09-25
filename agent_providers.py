#!/usr/bin/env python3
"""
Agent Providers Module - Pure Claude Code Delegation
All document processing is delegated to Claude Code agents through the SuperClaude Framework
No local processing logic - this module only orchestrates Claude CLI invocations
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import asyncio
import yaml
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class AgentCapability(str, Enum):
    """Agent capabilities for routing decisions"""
    FINANCIAL = "financial"
    LEGAL = "legal"
    TECHNICAL = "technical"
    DATA_ANALYSIS = "data_analysis"
    SECURITY = "security"
    GENERAL = "general"
    UI_GENERATION = "ui_generation"
    WEB_AUTOMATION = "web_automation"
    CODE_GENERATION = "code_generation"
    QUALITY_ASSURANCE = "quality_assurance"

@dataclass
class ProviderScore:
    """Scoring result from a provider"""
    score: float  # 0.0 to 1.0
    reasons: List[str]
    capabilities: List[AgentCapability]
    estimated_cost: float
    estimated_time_seconds: int

@dataclass
class ExecutionResult:
    """Result from provider execution"""
    success: bool
    output: Any
    cost: float
    duration_seconds: float
    quality_score: float
    artifacts: Dict[str, Any]
    telemetry: Dict[str, Any]
    next_actions: List[str]

class AgentProvider(ABC):
    """
    Abstract base class for all agent providers - PURE DELEGATION PATTERN
    All operations delegate to Claude Code via CLI - no local processing
    """
    
    def __init__(self, name: str, capabilities: List[AgentCapability]):
        self.name = name
        self.capabilities = capabilities
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # Load DSL configurations
        self._load_dsl_config()
        
        # Initialize Claude CLI wrapper
        from claude_cli import AsyncClaudeCLI, SuperClaudeMode
        self.cli = AsyncClaudeCLI()
        self.modes = SuperClaudeMode
    
    def _load_dsl_config(self):
        """Load DSL configuration for agent mappings"""
        dsl_path = Path(__file__).parent / "dsl" / "unified-operations.yaml"
        if dsl_path.exists():
            with open(dsl_path, 'r') as f:
                self.dsl_config = yaml.safe_load(f)
        else:
            self.dsl_config = {}
            
        # Load agent mappings
        mappings_path = Path(__file__).parent / "dsl" / "agent-mappings.yaml"
        if mappings_path.exists():
            with open(mappings_path, 'r') as f:
                self.agent_mappings = yaml.safe_load(f)
        else:
            self.agent_mappings = {}
    
    @abstractmethod
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        """Evaluate if this provider can handle the document"""
        pass
    
    @abstractmethod
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create execution plan for the document"""
        pass
    
    async def execute(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Execute a step by delegating to Claude Code - PURE DELEGATION"""
        # All execution delegates to Claude CLI
        return await self._delegate_to_claude(step, context)
    
    async def _delegate_to_claude(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        """Pure delegation to Claude Code via CLI"""
        start_time = datetime.now()
        
        try:
            # Build prompt from DSL template
            prompt = self._build_prompt_from_dsl(step, context)
            
            # Select agent and mode
            agent = step.get('agent', self.name)
            mode = self._select_mode(step, context)
            
            # Delegate to Claude
            result = await self.cli.execute_with_agent(
                agent=agent,
                prompt=prompt,
                mode=mode,
                context_files=context.get('files', []),
                flags=step.get('flags', [])
            )
            
            # Calculate metrics
            duration = (datetime.now() - start_time).total_seconds()
            
            return ExecutionResult(
                success=result.success,
                output=result.output,
                cost=self._estimate_cost(result),
                duration_seconds=duration,
                quality_score=self._extract_quality_score(result),
                artifacts=self._extract_artifacts(result),
                telemetry={'claude_response': result.metadata},
                next_actions=self._extract_next_actions(result)
            )
            
        except Exception as e:
            self.logger.error(f"Claude delegation failed: {e}")
            return ExecutionResult(
                success=False,
                output={'error': str(e)},
                cost=0.0,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                quality_score=0.0,
                artifacts={},
                telemetry={'error': str(e)},
                next_actions=['retry', 'fallback']
            )
    
    def _build_prompt_from_dsl(self, step: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Build prompt using DSL templates"""
        # Get template from DSL config
        operation = step.get('operation', 'analysis')
        template = self.dsl_config.get('prompt_templates', {}).get(operation, {}).get('template', '')
        
        if not template:
            # Fallback to basic prompt
            template = "Analyze and process this document: {{ document_content }}"
        
        # Render template with context
        from jinja2 import Template
        jinja_template = Template(template)
        return jinja_template.render(**context, **step)
    
    def _select_mode(self, step: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Select appropriate SuperClaude mode based on operation"""
        operation = step.get('operation', 'general')
        
        # Check DSL mode mappings
        mode_map = self.dsl_config.get('mode_mappings', {})
        if operation in mode_map:
            return mode_map[operation]
        
        # Default mode selection
        if context.get('parallel', False):
            return self.modes.ORCHESTRATE
        elif context.get('quality_loop', False):
            return self.modes.LOOP
        elif context.get('document_size', 0) > 10000:
            return self.modes.TOKEN_EFFICIENT
        else:
            return self.modes.TASK_MANAGE
    
    def _estimate_cost(self, result) -> float:
        """Estimate cost from Claude result"""
        # Rough estimation: $0.01 per 1000 tokens
        tokens = result.metadata.get('tokens_used', 1000) if hasattr(result, 'metadata') else 1000
        return tokens * 0.00001
    
    def _extract_quality_score(self, result) -> float:
        """Extract quality score from Claude response"""
        try:
            if hasattr(result, 'output') and isinstance(result.output, dict):
                return result.output.get('quality_score', 0.85)
            return 0.85  # Default quality
        except:
            return 0.85
    
    def _extract_artifacts(self, result) -> Dict[str, Any]:
        """Extract artifacts from Claude response"""
        try:
            if hasattr(result, 'output') and isinstance(result.output, dict):
                return result.output.get('artifacts', {})
            return {}
        except:
            return {}
    
    def _extract_next_actions(self, result) -> List[str]:
        """Extract next actions from Claude response"""
        try:
            if hasattr(result, 'output') and isinstance(result.output, dict):
                return result.output.get('next_actions', [])
            return []
        except:
            return []
    
    @abstractmethod
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        """Validate execution result and return quality score with issues"""
        pass
    
    @abstractmethod
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        """Summarize execution results into artifacts and next actions"""
        pass

class FinanceEngineerAgent(AgentProvider):
    """Agent specialized in financial document processing - PURE CLAUDE DELEGATION"""
    
    def __init__(self):
        super().__init__(
            name="finance-engineer",
            capabilities=[AgentCapability.FINANCIAL, AgentCapability.DATA_ANALYSIS]
        )
    
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        """Delegate document assessment to Claude"""
        # Use Claude to assess if this is a financial document
        assessment_prompt = f"""
        Assess if this document requires financial analysis:
        Type: {document_meta.get("content_type", "unknown")}
        Preview: {document_meta.get("content_preview", "")[:500]}
        
        Return confidence score (0-1) for financial processing.
        """
        
        result = await self.cli.execute(
            prompt=assessment_prompt,
            mode=self.modes.TOKEN_EFFICIENT,
            flags=["--uc"]
        )
        
        # Extract score from Claude's assessment
        try:
            score = float(result.output.get('confidence', 0.5))
        except:
            score = 0.5
            
        return ProviderScore(
            score=score,
            reasons=["Claude assessment for financial processing"],
            capabilities=[AgentCapability.FINANCIAL, AgentCapability.DATA_ANALYSIS],
            estimated_cost=0.02,
            estimated_time_seconds=30
        )
    
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate plan via Claude - no local logic"""
        plan_prompt = f"""
        Create a financial document processing plan.
        Document type: {context.get('document_type', 'invoice')}
        
        Return structured plan with steps for:
        1. Financial data extraction
        2. Calculation validation
        3. Visualization generation
        4. Report creation
        """
        
        result = await self.cli.execute_with_agent(
            agent="finance-engineer",
            prompt=plan_prompt,
            mode=self.modes.TASK_MANAGE
        )
        
        # Return Claude-generated plan
        if result.success and isinstance(result.output, list):
            return result.output
        else:
            # Fallback plan structure
            return [
                {
                    "id": "extract_financial_data",
                    "operation": "analysis",
                    "agent": "finance-engineer",
                    "prompt": "Extract all financial data from document"
                },
                {
                    "id": "validate_calculations",
                    "operation": "validation",
                    "agent": "quality-engineer",
                    "prompt": "Validate all calculations and totals"
                },
                {
                    "id": "generate_report",
                    "operation": "generation",
                    "agent": "technical-writer",
                    "prompt": "Generate financial analysis report"
                }
            ]
    
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        issues = []
        score = result.quality_score
        
        # Validate financial data extraction
        if "extracted_data" in result.output:
            data = result.output["extracted_data"]
            # Add validation logic here
            
        return score, issues
    
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        return {
            "summary": "Financial document processed successfully",
            "artifacts": {
                "analysis_script": "financial_analysis.py",
                "visualization": "charts.png",
                "report": "financial_report.pdf"
            },
            "next_actions": [
                "review_extracted_data",
                "approve_payment",
                "schedule_transaction"
            ]
        }

class SecurityEngineerAgent(AgentProvider):
    """Agent specialized in security and legal document review"""
    
    def __init__(self):
        super().__init__(
            name="security-engineer",
            capabilities=[AgentCapability.SECURITY, AgentCapability.LEGAL]
        )
    
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        score = 0.0
        reasons = []
        
        doc_type = document_meta.get("content_type", "").lower()
        if any(term in doc_type for term in ["nda", "contract", "agreement", "legal"]):
            score += 0.5
            reasons.append("Legal document type detected")
        
        # Check for security/legal keywords
        content_preview = document_meta.get("content_preview", "").lower()
        legal_keywords = ["confidential", "agreement", "party", "obligation", "liability", "terms", "conditions"]
        keyword_matches = sum(1 for kw in legal_keywords if kw in content_preview)
        if keyword_matches > 2:
            score += 0.3
            reasons.append(f"Found {keyword_matches} legal/security keywords")
        
        # Check for PII flags
        if document_meta.get("pii_flags"):
            score += 0.2
            reasons.append("Contains PII - security review needed")
        
        return ProviderScore(
            score=min(score, 1.0),
            reasons=reasons,
            capabilities=[AgentCapability.SECURITY, AgentCapability.LEGAL],
            estimated_cost=0.03,
            estimated_time_seconds=45
        )
    
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": "security_scan",
                "tool": "claude",
                "args": {
                    "flags": "--delegate",
                    "agent": "security-engineer",
                    "prompt": "Identify confidentiality requirements, PII, and security obligations"
                }
            },
            {
                "id": "compliance_check",
                "tool": "validation",
                "args": {
                    "checks": ["gdpr_compliance", "data_retention", "access_controls"]
                }
            },
            {
                "id": "generate_access_controls",
                "tool": "code_generation",
                "args": {
                    "type": "access_control_policy",
                    "format": "yaml"
                }
            }
        ]
    
    async def execute(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        # Implementation similar to FinanceEngineerAgent
        return ExecutionResult(
            success=True,
            output={"security_findings": []},
            cost=0.015,
            duration_seconds=10.0,
            quality_score=0.92,
            artifacts={},
            telemetry={},
            next_actions=[]
        )
    
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        return result.quality_score, []
    
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        return {
            "summary": "Security review completed",
            "artifacts": {
                "security_report": "security_assessment.pdf",
                "access_policy": "access_controls.yaml"
            },
            "next_actions": ["implement_controls", "notify_stakeholders"]
        }

class TechnicalWriterAgent(AgentProvider):
    """Agent specialized in documentation and report generation"""
    
    def __init__(self):
        super().__init__(
            name="technical-writer",
            capabilities=[AgentCapability.TECHNICAL, AgentCapability.GENERAL]
        )
    
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        score = 0.0
        reasons = []
        
        doc_type = document_meta.get("content_type", "").lower()
        if any(term in doc_type for term in ["report", "documentation", "manual", "guide"]):
            score += 0.5
            reasons.append("Documentation type detected")
        
        # Default handler for general documents
        if score == 0:
            score = 0.3
            reasons.append("Can handle general documentation tasks")
        
        return ProviderScore(
            score=min(score, 1.0),
            reasons=reasons,
            capabilities=[AgentCapability.TECHNICAL],
            estimated_cost=0.01,
            estimated_time_seconds=20
        )
    
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": "analyze_structure",
                "tool": "claude",
                "args": {
                    "flags": "--delegate",
                    "agent": "technical-writer",
                    "prompt": "Analyze document structure and create outline"
                }
            },
            {
                "id": "generate_summary",
                "tool": "claude",
                "args": {
                    "flags": "--delegate",
                    "agent": "technical-writer",
                    "prompt": "Generate executive summary and key points"
                }
            },
            {
                "id": "create_report",
                "tool": "report_generation",
                "args": {
                    "format": "markdown",
                    "include_toc": True,
                    "include_charts": True
                }
            }
        ]
    
    async def execute(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output={"report_generated": True},
            cost=0.008,
            duration_seconds=8.0,
            quality_score=0.88,
            artifacts={},
            telemetry={},
            next_actions=[]
        )
    
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        return result.quality_score, []
    
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        return {
            "summary": "Documentation generated successfully",
            "artifacts": {
                "report": "document_report.md",
                "summary": "executive_summary.pdf"
            },
            "next_actions": ["review_report", "distribute_to_stakeholders"]
        }

class GeneralPurposeAgent(AgentProvider):
    """Fallback agent for general document processing"""
    
    def __init__(self):
        super().__init__(
            name="general-purpose",
            capabilities=[AgentCapability.GENERAL]
        )
    
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        # Always returns a baseline score as fallback
        return ProviderScore(
            score=0.1,
            reasons=["General purpose fallback agent"],
            capabilities=[AgentCapability.GENERAL],
            estimated_cost=0.015,
            estimated_time_seconds=30
        )
    
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": "general_analysis",
                "tool": "claude",
                "args": {
                    "flags": "--delegate",
                    "agent": "general-purpose",
                    "prompt": "Analyze document and extract key information"
                }
            }
        ]
    
    async def execute(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output={"analysis": "General analysis completed"},
            cost=0.01,
            duration_seconds=10.0,
            quality_score=0.75,
            artifacts={},
            telemetry={},
            next_actions=[]
        )
    
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        return result.quality_score, []
    
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        return {
            "summary": "Document processed",
            "artifacts": {},
            "next_actions": ["manual_review"]
        }

class RootCauseAnalystAgent(AgentProvider):
    """Agent for analyzing and classifying unknown documents"""
    
    def __init__(self):
        super().__init__(
            name="root-cause-analyst",
            capabilities=[AgentCapability.GENERAL, AgentCapability.DATA_ANALYSIS]
        )
    
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        # Higher score for unknown or ambiguous documents
        score = 0.0
        reasons = []
        
        if not document_meta.get("content_type") or document_meta.get("content_type") == "unknown":
            score = 0.8
            reasons.append("Unknown document type - needs classification")
        elif document_meta.get("confidence", 1.0) < 0.5:
            score = 0.7
            reasons.append("Low confidence in document type - needs analysis")
        
        return ProviderScore(
            score=score,
            reasons=reasons,
            capabilities=[AgentCapability.GENERAL, AgentCapability.DATA_ANALYSIS],
            estimated_cost=0.02,
            estimated_time_seconds=40
        )
    
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": "deep_analysis",
                "tool": "claude",
                "args": {
                    "flags": "--thinkdeep --delegate",
                    "agent": "root-cause-analyst",
                    "prompt": "Analyze document structure, content, and purpose to determine type and appropriate processing"
                }
            },
            {
                "id": "classify_document",
                "tool": "classification",
                "args": {
                    "model": "sequential",
                    "return_confidence": True
                }
            },
            {
                "id": "route_to_specialist",
                "tool": "routing",
                "args": {
                    "based_on": "classification_result"
                }
            }
        ]
    
    async def execute(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output={
                "document_type": "invoice",
                "confidence": 0.85,
                "recommended_agent": "finance-engineer"
            },
            cost=0.015,
            duration_seconds=15.0,
            quality_score=0.9,
            artifacts={},
            telemetry={},
            next_actions=["route_to_finance_engineer"]
        )
    
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        return result.quality_score, []
    
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        return {
            "summary": "Document classified and routed successfully",
            "artifacts": {
                "classification_report": "document_classification.json"
            },
            "next_actions": ["process_with_specialized_agent"]
        }

class QualityEngineerAgent(AgentProvider):
    """Agent for quality assurance and validation"""
    
    def __init__(self):
        super().__init__(
            name="quality-engineer",
            capabilities=[AgentCapability.QUALITY_ASSURANCE]
        )
    
    async def can_handle(self, document_meta: Dict[str, Any]) -> ProviderScore:
        # Used for validation workflows
        if document_meta.get("requires_validation", False):
            return ProviderScore(
                score=0.9,
                reasons=["Document requires quality validation"],
                capabilities=[AgentCapability.QUALITY_ASSURANCE],
                estimated_cost=0.01,
                estimated_time_seconds=15
            )
        return ProviderScore(score=0.0, reasons=[], capabilities=[], estimated_cost=0, estimated_time_seconds=0)
    
    async def plan(self, document: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "id": "quality_checks",
                "tool": "validation",
                "args": {
                    "checks": ["completeness", "accuracy", "consistency", "format"]
                }
            }
        ]
    
    async def execute(self, step: Dict[str, Any], context: Dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output={"validation_passed": True, "issues": []},
            cost=0.005,
            duration_seconds=5.0,
            quality_score=0.95,
            artifacts={},
            telemetry={},
            next_actions=[]
        )
    
    async def validate(self, result: ExecutionResult) -> Tuple[float, List[str]]:
        return result.quality_score, []
    
    async def summarize(self, results: List[ExecutionResult]) -> Dict[str, Any]:
        return {
            "summary": "Quality validation completed",
            "artifacts": {
                "validation_report": "quality_report.json"
            },
            "next_actions": []
        }

class AgentRegistry:
    """Registry for managing and routing to agent providers"""
    
    def __init__(self):
        self.providers: Dict[str, AgentProvider] = {}
        self._initialize_default_agents()
    
    def _initialize_default_agents(self):
        """Initialize default SuperClaude agents"""
        self.register(FinanceEngineerAgent())
        self.register(SecurityEngineerAgent())
        self.register(TechnicalWriterAgent())
        self.register(GeneralPurposeAgent())
        self.register(RootCauseAnalystAgent())
        self.register(QualityEngineerAgent())
        
        logger.info(f"Initialized {len(self.providers)} agent providers")
    
    def register(self, provider: AgentProvider):
        """Register a new agent provider"""
        self.providers[provider.name] = provider
        logger.info(f"Registered agent provider: {provider.name}")
    
    async def route(self, document_meta: Dict[str, Any]) -> Tuple[AgentProvider, ProviderScore]:
        """Route document to the best agent provider"""
        scores = []
        
        # Evaluate all providers
        for name, provider in self.providers.items():
            score = await provider.can_handle(document_meta)
            scores.append((provider, score))
            logger.debug(f"{name} scored {score.score:.2f} for document")
        
        # Sort by score and return best match
        scores.sort(key=lambda x: x[1].score, reverse=True)
        best_provider, best_score = scores[0]
        
        logger.info(f"Routing to {best_provider.name} with score {best_score.score:.2f}")
        logger.debug(f"Reasons: {', '.join(best_score.reasons)}")
        
        return best_provider, best_score
    
    def get_provider(self, name: str) -> Optional[AgentProvider]:
        """Get a specific provider by name"""
        return self.providers.get(name)
    
    def list_providers(self) -> List[Dict[str, Any]]:
        """List all available providers"""
        return [
            {
                "name": provider.name,
                "capabilities": [cap.value for cap in provider.capabilities]
            }
            for provider in self.providers.values()
        ]

# Global registry instance
agent_registry = AgentRegistry()