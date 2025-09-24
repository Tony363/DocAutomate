#!/usr/bin/env python3
"""
Action Extractor Module
Uses Claude's NLP capabilities to extract actionable items from documents
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ActionType(str, Enum):
    """Supported action types"""
    INVOICE_PROCESSING = "invoice_processing"
    APPROVAL_REQUEST = "approval_request"
    DATA_ENTRY = "data_entry"
    NOTIFICATION = "notification"
    SCHEDULING = "scheduling"
    PAYMENT = "payment"
    REPORT_GENERATION = "report_generation"
    CUSTOM = "custom"

class ConfidenceLevel(str, Enum):
    """Confidence levels for extracted actions"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ExtractedEntity(BaseModel):
    """Represents an extracted entity from the document"""
    name: str = Field(description="Entity name (e.g., 'invoice_number', 'vendor_name')")
    value: Any = Field(description="Extracted value")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)")
    location: Optional[str] = Field(default=None, description="Location in document where found")

class ExtractedAction(BaseModel):
    """Represents an actionable item extracted from a document"""
    action_type: ActionType = Field(description="Type of action to be taken")
    workflow_name: str = Field(description="Name of the workflow to trigger")
    description: str = Field(description="Human-readable description of the action")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters to pass to the workflow")
    entities: List[ExtractedEntity] = Field(default_factory=list, description="Extracted entities")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Overall confidence (0.0 to 1.0)")
    confidence_level: ConfidenceLevel = Field(description="Qualitative confidence level")
    priority: int = Field(ge=1, le=5, default=3, description="Priority level (1=highest, 5=lowest)")
    deadline: Optional[str] = Field(default=None, description="Deadline if mentioned in document")
    
    @validator('confidence_level', pre=False, always=True)
    def set_confidence_level(cls, v, values):
        """Auto-set confidence level based on score"""
        score = values.get('confidence_score', 0)
        if score >= 0.85:
            return ConfidenceLevel.HIGH
        elif score >= 0.65:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

class ActionExtractor:
    """
    Extracts actionable items from document text using Claude's NLP
    """
    
    def __init__(self, confidence_threshold: float = 0.65):
        self.confidence_threshold = confidence_threshold
        self.extraction_prompts = self._load_extraction_prompts()
    
    def _load_extraction_prompts(self) -> Dict[str, str]:
        """Load specialized prompts for different document types"""
        return {
            'invoice': self._get_invoice_prompt(),
            'email': self._get_email_prompt(),
            'report': self._get_report_prompt(),
            'general': self._get_general_prompt()
        }
    
    def _get_invoice_prompt(self) -> str:
        return """Analyze this invoice document and extract actionable items.
        Focus on: payment details, vendor information, due dates, amounts, and approval requirements.
        """
    
    def _get_email_prompt(self) -> str:
        return """Analyze this email and identify required actions.
        Focus on: requests, deadlines, follow-ups, meetings to schedule, and decisions needed.
        """
    
    def _get_report_prompt(self) -> str:
        return """Analyze this report and extract action items.
        Focus on: recommendations, required follow-ups, issues to address, and metrics to track.
        """
    
    def _get_general_prompt(self) -> str:
        return """Analyze this document and identify all actionable items.
        Look for: tasks, deadlines, approvals needed, data to process, and follow-up requirements.
        """
    
    async def extract_actions(self, text: str, document_type: str = 'general') -> List[ExtractedAction]:
        """
        Extract actionable items from document text
        Returns list of structured actions with confidence scores
        """
        # Get appropriate prompt
        prompt_template = self.extraction_prompts.get(document_type, self.extraction_prompts['general'])
        
        # Build the extraction prompt
        prompt = self._build_extraction_prompt(text, prompt_template)
        
        try:
            # Call Claude API (simulated for demo)
            raw_response = await self._call_claude_api(prompt)
            
            # Parse and validate response
            actions = self._parse_claude_response(raw_response)
            
            # Filter by confidence threshold
            filtered_actions = [
                action for action in actions 
                if action.confidence_score >= self.confidence_threshold
            ]
            
            # Log low-confidence actions for review
            for action in actions:
                if action.confidence_score < self.confidence_threshold:
                    logger.warning(f"Low confidence action filtered: {action.description} (score: {action.confidence_score})")
            
            return filtered_actions
            
        except Exception as e:
            logger.error(f"Failed to extract actions: {str(e)}")
            return []
    
    def _build_extraction_prompt(self, text: str, template: str) -> str:
        """Build the complete prompt for Claude"""
        schema = json.dumps(ExtractedAction.model_json_schema(), indent=2)
        
        return f"""
{template}

Respond ONLY with a JSON array of action objects matching this schema:
{schema}

Important guidelines:
1. Extract only clearly actionable items
2. Provide accurate confidence scores
3. Include all relevant entities and parameters
4. Set appropriate priority levels
5. Extract deadlines when mentioned

Document text:
---
{text[:3000]}  # Limit to first 3000 chars for demo
---

Response (JSON array only):
"""
    
    async def _call_claude_api(self, prompt: str) -> str:
        """
        Call Claude via CLI for extraction
        """
        try:
            # Use Claude Code CLI for real extraction
            from claude_cli import AsyncClaudeCLI
            cli = AsyncClaudeCLI()
            
            # Define the expected schema for extraction
            extraction_schema = {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action_type": {"type": "string"},
                        "workflow_name": {"type": "string"},
                        "description": {"type": "string"},
                        "parameters": {"type": "object"},
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "value": {},
                                    "confidence": {"type": "number"},
                                    "location": {"type": "string"}
                                }
                            }
                        },
                        "confidence_score": {"type": "number"},
                        "confidence_level": {"type": "string"},
                        "priority": {"type": "integer"},
                        "deadline": {"type": "string"}
                    }
                }
            }
            
            # Extract the text portion from the prompt
            import re
            text_match = re.search(r'Document text:\n---\n(.+?)\n---', prompt, re.DOTALL)
            if text_match:
                document_text = text_match.group(1)
            else:
                document_text = prompt
            
            # Call Claude with structured extraction request
            logger.info("Calling Claude Code for action extraction")
            result = await cli.analyze_text_async(
                text=document_text,
                prompt="Extract all actionable items from this document. Include invoice processing, approval requests, payments, scheduling, and any other actions needed. Return as a JSON array.",
                schema=extraction_schema
            )
            
            # Convert result to JSON string if it's a dict
            if isinstance(result, dict):
                # If result has a 'result' key, use that
                if 'result' in result:
                    return json.dumps(result['result'])
                else:
                    return json.dumps([result])  # Wrap single result in array
            elif isinstance(result, list):
                return json.dumps(result)
            else:
                return str(result)
                
        except (ImportError, Exception) as e:
            # Fallback to simulated response if Claude Code is not available
            logger.warning(f"Claude Code extraction failed, using fallback: {e}")
            
            # Return a basic simulated response
            simulated_response = """[
  {
    "action_type": "invoice_processing",
    "workflow_name": "process_invoice",
    "description": "Process document (Claude Code required for full extraction)",
    "parameters": {
      "status": "pending_claude_extraction"
    },
    "entities": [],
    "confidence_score": 0.0,
    "confidence_level": "low",
    "priority": 5,
    "deadline": null
  }
]"""
            return simulated_response
    
    def _parse_claude_response(self, raw_response: str) -> List[ExtractedAction]:
        """Parse and validate Claude's response"""
        try:
            # Parse JSON
            data = json.loads(raw_response)
            
            # Validate each action
            actions = []
            for item in data:
                try:
                    action = ExtractedAction(**item)
                    actions.append(action)
                except Exception as e:
                    logger.error(f"Failed to validate action: {e}")
                    logger.debug(f"Invalid action data: {item}")
            
            return actions
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            return []
    
    def prioritize_actions(self, actions: List[ExtractedAction]) -> List[ExtractedAction]:
        """Sort actions by priority and confidence"""
        return sorted(
            actions,
            key=lambda x: (x.priority, -x.confidence_score)
        )
    
    def group_by_workflow(self, actions: List[ExtractedAction]) -> Dict[str, List[ExtractedAction]]:
        """Group actions by workflow name"""
        grouped = {}
        for action in actions:
            if action.workflow_name not in grouped:
                grouped[action.workflow_name] = []
            grouped[action.workflow_name].append(action)
        return grouped
    
    def validate_action_params(self, action: ExtractedAction, workflow_schema: Dict) -> bool:
        """
        Validate action parameters against workflow schema
        Returns True if valid, False otherwise
        """
        required_params = workflow_schema.get('required_parameters', [])
        
        for param in required_params:
            if param not in action.parameters:
                logger.warning(f"Missing required parameter '{param}' for workflow '{action.workflow_name}'")
                return False
        
        return True

# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def main():
        extractor = ActionExtractor(confidence_threshold=0.7)
        
        sample_text = """
        Invoice Number: INV-2024-001
        Vendor: ABC Corporation
        Amount: $5,000.00
        Due Date: February 15, 2024
        
        Please process this invoice for payment. Approval is required from the Finance Manager.
        The payment should be scheduled for the due date.
        """
        
        actions = await extractor.extract_actions(sample_text, document_type='invoice')
        
        print(f"Extracted {len(actions)} actions:")
        for action in actions:
            print(f"\\n- {action.description}")
            print(f"  Type: {action.action_type}")
            print(f"  Workflow: {action.workflow_name}")
            print(f"  Confidence: {action.confidence_score:.2f} ({action.confidence_level})")
            print(f"  Priority: {action.priority}")
            if action.deadline:
                print(f"  Deadline: {action.deadline}")
    
    asyncio.run(main())