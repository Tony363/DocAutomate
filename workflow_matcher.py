#!/usr/bin/env python3
"""
Intelligent Workflow Matcher using Claude
Maps semantically similar workflow names to available workflows
"""

import json
import logging
import asyncio
from typing import Dict, Tuple, Optional, Set, List, Any
from dataclasses import dataclass
from functools import lru_cache
import re

# Try to import Claude CLI, fall back to basic matching if not available
try:
    from claude_cli import AsyncClaudeCLI
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    logging.warning("Claude CLI not available - using fallback matching")

logger = logging.getLogger(__name__)

@dataclass
class MatchResult:
    """Result of workflow matching attempt"""
    matched_workflow: str
    confidence: float
    reason: str
    reasoning: Optional[str] = None

class WorkflowMatcher:
    """
    Intelligent workflow matching using Claude and fallback strategies
    """
    
    # Static aliases for common variations
    STATIC_ALIASES = {
        # Complete variations
        'complete_recipient_info': 'complete_missing_info',
        'complete_agreement_date': 'complete_missing_info',
        'complete_sender_info': 'complete_missing_info',
        'complete_party_info': 'complete_missing_info',
        'complete_missing_information': 'complete_missing_info',
        'complete_info': 'complete_missing_info',
        
        # Signature variations
        'nda_signature': 'document_signature',
        'contract_signature': 'document_signature',
        'agreement_signature': 'document_signature',
        'sign_document': 'document_signature',
        'signature_required': 'document_signature',
        'signature_request': 'document_signature',
        
        # Document management variations
        'confidential_info_return': 'document_management',
        'return_confidential_info': 'document_management',
        'manage_document': 'document_management',
        'document_lifecycle': 'document_management',
        
        # Legal/compliance variations
        'nda_review': 'document_review',
        'contract_review': 'document_review',
        'legal_review': 'legal_compliance',
        'compliance_check': 'legal_compliance',
        
        # Invoice variations
        'invoice_processing': 'process_invoice',
        'process_invoice': 'invoice',
        'invoice_workflow': 'invoice',
    }
    
    # Synonyms for token-based matching
    SYNONYMS = {
        'information': 'info',
        'recipient': 'party',
        'sender': 'party',
        'nda': 'document',
        'confidentiality': 'confidential',
        'confidential': 'document',
        'sign': 'signature',
        'signing': 'signature',
        'agreement': 'document',
        'contract': 'document',
        'return': 'management',
        'manage': 'management',
        'process': 'processing',
        'complete': 'missing',
        'fill': 'missing',
    }
    
    # Generic fallback workflows in order of preference
    GENERIC_FALLBACKS = [
        'document_review',
        'complete_missing_info',
        'document_management',
        'document_signature',
        'legal_compliance'
    ]
    
    def __init__(self, workflow_engine=None):
        """
        Initialize the matcher
        
        Args:
            workflow_engine: WorkflowEngine instance to get available workflows
        """
        self.workflow_engine = workflow_engine
        self.available_workflows = {}
        self._match_cache = {}  # Cache matches to avoid repeated Claude calls
        
        if workflow_engine:
            self.available_workflows = workflow_engine.workflows
            
        # Initialize Claude CLI if available
        self.claude_cli = None
        if CLAUDE_AVAILABLE:
            try:
                self.claude_cli = AsyncClaudeCLI()
                logger.info("Claude CLI initialized for intelligent matching")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude CLI: {e}")
                
    def _normalize_name(self, name: str) -> str:
        """Normalize workflow name for comparison"""
        # Convert to lowercase and replace non-alphanumeric with underscore
        normalized = re.sub(r'[^a-z0-9]+', '_', name.lower())
        # Remove duplicate underscores and trim
        normalized = re.sub(r'_+', '_', normalized).strip('_')
        return normalized
    
    def _tokenize(self, name: str) -> Set[str]:
        """Split name into tokens and apply synonyms"""
        tokens = set()
        normalized = self._normalize_name(name)
        
        for token in normalized.split('_'):
            if token:
                # Add original token
                tokens.add(token)
                # Add synonym if exists
                if token in self.SYNONYMS:
                    tokens.add(self.SYNONYMS[token])
                    
        return tokens
    
    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate Jaccard similarity between two workflow names"""
        tokens1 = self._tokenize(name1)
        tokens2 = self._tokenize(name2)
        
        if not tokens1 or not tokens2:
            return 0.0
            
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        
        return intersection / union if union > 0 else 0.0
    
    async def _match_with_claude(self, requested_name: str, context: Dict[str, Any]) -> Optional[MatchResult]:
        """
        Use Claude to semantically match workflow names
        
        Args:
            requested_name: The workflow name to match
            context: Additional context about the action
            
        Returns:
            MatchResult if Claude provides a match, None otherwise
        """
        if not self.claude_cli or not self.available_workflows:
            return None
            
        try:
            # Build workflow descriptions
            workflow_descriptions = []
            for wf_name, wf_def in self.available_workflows.items():
                desc = wf_def.get('description', 'No description available')
                workflow_descriptions.append(f"- {wf_name}: {desc}")
            
            # Prepare the matching prompt
            prompt = f"""You are a workflow matching expert. Match the requested workflow to the best available workflow.

Available workflows:
{chr(10).join(workflow_descriptions)}

Requested workflow: "{requested_name}"
Context: {json.dumps(context, indent=2) if context else "No additional context"}

Analyze the semantic meaning and intent, then provide the best match.
Return ONLY a JSON object with this structure:
{{
    "matched_workflow": "exact_workflow_name_from_list",
    "confidence": 0.95,
    "reasoning": "Brief explanation of why this matches"
}}

If no good match exists (confidence < 0.5), use "no_match" as the matched_workflow.
"""
            
            # Call Claude for matching
            result = await self.claude_cli.analyze_text_async(
                text="",
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "matched_workflow": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reasoning": {"type": "string"}
                    },
                    "required": ["matched_workflow", "confidence", "reasoning"]
                }
            )
            
            if result and isinstance(result, dict):
                matched = result.get('matched_workflow')
                confidence = float(result.get('confidence', 0))
                reasoning = result.get('reasoning', '')
                
                if matched and matched != 'no_match' and matched in self.available_workflows:
                    return MatchResult(
                        matched_workflow=matched,
                        confidence=confidence,
                        reason='claude_semantic_match',
                        reasoning=reasoning
                    )
                    
        except Exception as e:
            logger.debug(f"Claude matching failed: {e}")
            
        return None
    
    def _fuzzy_match(self, requested_name: str) -> Optional[MatchResult]:
        """
        Fuzzy match using token similarity
        
        Args:
            requested_name: The workflow name to match
            
        Returns:
            MatchResult if a good fuzzy match is found, None otherwise
        """
        if not self.available_workflows:
            return None
            
        best_match = None
        best_score = 0.0
        
        for workflow_name in self.available_workflows.keys():
            score = self._calculate_similarity(requested_name, workflow_name)
            if score > best_score:
                best_score = score
                best_match = workflow_name
                
        # Require at least 0.5 similarity for fuzzy match
        if best_match and best_score >= 0.5:
            # Adjust confidence based on similarity score
            confidence = min(0.7, best_score * 0.9)
            
            return MatchResult(
                matched_workflow=best_match,
                confidence=confidence,
                reason='fuzzy_token_match',
                reasoning=f"Token similarity score: {best_score:.2f}"
            )
            
        return None
    
    async def match(self, requested_name: str, context: Optional[Dict[str, Any]] = None) -> MatchResult:
        """
        Match a requested workflow name to an available workflow
        
        Args:
            requested_name: The workflow name to match
            context: Optional context about the action/document
            
        Returns:
            MatchResult with the best match and confidence
        """
        # Check cache first
        cache_key = f"{requested_name}:{json.dumps(context, sort_keys=True) if context else ''}"
        if cache_key in self._match_cache:
            logger.debug(f"Using cached match for '{requested_name}'")
            return self._match_cache[cache_key]
        
        # 1. Try direct match
        if requested_name in self.available_workflows:
            result = MatchResult(
                matched_workflow=requested_name,
                confidence=1.0,
                reason='direct_match',
                reasoning="Exact workflow name exists"
            )
            self._match_cache[cache_key] = result
            return result
        
        # 2. Try static aliases
        normalized = self._normalize_name(requested_name)
        if normalized in self.STATIC_ALIASES:
            aliased = self.STATIC_ALIASES[normalized]
            if aliased in self.available_workflows:
                result = MatchResult(
                    matched_workflow=aliased,
                    confidence=0.9,
                    reason='static_alias',
                    reasoning=f"Known alias mapping: {requested_name} -> {aliased}"
                )
                self._match_cache[cache_key] = result
                return result
        
        # 3. Try Claude semantic matching (if available)
        if CLAUDE_AVAILABLE and self.claude_cli:
            claude_result = await self._match_with_claude(requested_name, context or {})
            if claude_result and claude_result.confidence >= 0.7:
                self._match_cache[cache_key] = claude_result
                return claude_result
        
        # 4. Try fuzzy token matching
        fuzzy_result = self._fuzzy_match(requested_name)
        if fuzzy_result:
            self._match_cache[cache_key] = fuzzy_result
            return fuzzy_result
        
        # 5. Try generic fallback
        for fallback in self.GENERIC_FALLBACKS:
            if fallback in self.available_workflows:
                result = MatchResult(
                    matched_workflow=fallback,
                    confidence=0.4,
                    reason='generic_fallback',
                    reasoning=f"No specific match found, using generic workflow: {fallback}"
                )
                self._match_cache[cache_key] = result
                return result
        
        # 6. No match found
        result = MatchResult(
            matched_workflow=requested_name,
            confidence=0.0,
            reason='no_match',
            reasoning="No suitable workflow match found"
        )
        self._match_cache[cache_key] = result
        return result
    
    def clear_cache(self):
        """Clear the match cache"""
        self._match_cache.clear()
        logger.info("Workflow match cache cleared")

# Convenience function for backwards compatibility
async def match_workflow(requested_name: str, available_workflows: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Tuple[str, float, str]:
    """
    Match a workflow name to available workflows
    
    Args:
        requested_name: The workflow name to match
        available_workflows: Dictionary of available workflows
        context: Optional context about the action
        
    Returns:
        Tuple of (matched_name, confidence, reason)
    """
    # Create a temporary matcher
    class TempEngine:
        def __init__(self, workflows):
            self.workflows = workflows
    
    temp_engine = TempEngine(available_workflows)
    matcher = WorkflowMatcher(temp_engine)
    
    result = await matcher.match(requested_name, context)
    return result.matched_workflow, result.confidence, result.reason

# Example usage
if __name__ == "__main__":
    async def test_matcher():
        """Test the workflow matcher"""
        
        # Mock available workflows
        available = {
            'document_signature': {'description': 'Handle signature requirements'},
            'complete_missing_info': {'description': 'Fill in missing information'},
            'document_management': {'description': 'Manage document lifecycle'},
            'document_review': {'description': 'Review documents'},
            'legal_compliance': {'description': 'Legal compliance checks'},
            'invoice': {'description': 'Process invoices'}
        }
        
        # Test cases
        test_cases = [
            ('document_signature', {}),  # Direct match
            ('nda_signature', {}),  # Static alias
            ('complete_missing_information', {}),  # Static alias variant
            ('confidential_info_return', {}),  # Should map to document_management
            ('signature_request', {'action_type': 'signature'}),  # With context
            ('random_unknown_workflow', {})  # No match
        ]
        
        class MockEngine:
            def __init__(self):
                self.workflows = available
        
        matcher = WorkflowMatcher(MockEngine())
        
        print("Testing Workflow Matcher\n" + "="*50)
        
        for requested, context in test_cases:
            result = await matcher.match(requested, context)
            print(f"\nRequested: {requested}")
            print(f"  Matched: {result.matched_workflow}")
            print(f"  Confidence: {result.confidence:.2f}")
            print(f"  Reason: {result.reason}")
            if result.reasoning:
                print(f"  Reasoning: {result.reasoning}")
    
    asyncio.run(test_matcher())