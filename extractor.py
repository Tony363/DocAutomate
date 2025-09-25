#!/usr/bin/env python3
"""
Action Extractor Module
Uses Claude's NLP capabilities to extract actionable items from documents
"""

import json
import logging
import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum

# Set up logging with more detail
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

class ActionType(str, Enum):
    """Supported action types"""
    # Original invoice-related types
    INVOICE_PROCESSING = "invoice_processing"
    APPROVAL_REQUEST = "approval_request"
    DATA_ENTRY = "data_entry"
    NOTIFICATION = "notification"
    SCHEDULING = "scheduling"
    PAYMENT = "payment"
    REPORT_GENERATION = "report_generation"
    
    # Document and legal types
    LEGAL_REVIEW = "legal_review"
    DOCUMENT_REVIEW = "document_review"
    ACCESS_REQUEST = "access_request"
    FILE_ACCESS_REQUEST = "file_access_request"
    SIGNATURE_REQUEST = "signature_request"
    CONTRACT_REVIEW = "contract_review"
    NDA_PROCESSING = "nda_processing"
    
    # Fallback
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
            'nda': self._get_nda_prompt(),
            'contract': self._get_contract_prompt(),
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
    
    def _get_nda_prompt(self) -> str:
        return """Analyze this NDA/confidentiality agreement and extract actionable items.
        Focus on: access permissions required, signatures needed, review deadlines, compliance requirements,
        confidential information handling, and any approval workflows needed.
        """
    
    def _get_contract_prompt(self) -> str:
        return """Analyze this contract/agreement and extract actionable items.
        Focus on: signature requirements, review deadlines, approval processes, obligations,
        deliverables, and compliance requirements.
        """
    
    def _detect_document_type(self, text: str) -> str:
        """Detect document type from content"""
        text_lower = text.lower()
        
        # Check for NDA/confidentiality documents
        if any(term in text_lower for term in ['nda', 'non-disclosure', 'confidential agreement', 
                                                'confidentiality agreement']):
            return 'nda'
        # Check for contracts
        elif any(term in text_lower for term in ['contract', 'agreement', 'terms and conditions',
                                                  'whereas', 'hereinafter']):
            return 'contract'
        # Check for invoices
        elif any(term in text_lower for term in ['invoice', 'bill', 'payment due', 'invoice number',
                                                  'amount due', 'tax invoice']):
            return 'invoice'
        # Check for emails
        elif '@' in text and any(term in text_lower for term in ['subject:', 'from:', 'to:', 'date:']):
            return 'email'
        # Check for reports
        elif any(term in text_lower for term in ['executive summary', 'findings', 'recommendations',
                                                  'conclusion', 'analysis']):
            return 'report'
        else:
            return 'general'
    
    async def extract_actions(self, text: str, document_type: str = None) -> List[ExtractedAction]:
        """
        Extract actionable items from document text
        Returns list of structured actions with confidence scores
        """
        start_time = time.time()
        text_size = len(text) if text else 0
        logger.info(f"Starting action extraction: text_size={text_size} chars, document_type={document_type}")
        
        # Auto-detect document type if not provided
        if document_type is None:
            detect_start = time.time()
            document_type = self._detect_document_type(text)
            detect_time = time.time() - detect_start
            logger.info(f"Auto-detected document type '{document_type}' in {detect_time:.3f}s")
        else:
            logger.info(f"Using provided document type: {document_type}")
        
        # Get appropriate prompt
        prompt_template = self.extraction_prompts.get(document_type, self.extraction_prompts['general'])
        logger.debug(f"Using prompt template for type '{document_type}'")
        
        # Build the extraction prompt
        logger.debug("Building extraction prompt")
        prompt = self._build_extraction_prompt(text, prompt_template)
        prompt_size = len(prompt)
        logger.debug(f"Prompt built: size={prompt_size} chars")
        
        try:
            # Call Claude API
            logger.info("Calling Claude API for action extraction")
            api_start = time.time()
            raw_response = await self._call_claude_api(prompt)
            api_time = time.time() - api_start
            logger.info(f"Claude API responded in {api_time:.2f}s, response_size={len(raw_response) if raw_response else 0} chars")
            
            # Parse and validate response
            logger.debug("Parsing Claude response")
            parse_start = time.time()
            actions = self._parse_claude_response(raw_response)
            parse_time = time.time() - parse_start
            logger.info(f"Parsed {len(actions)} actions in {parse_time:.3f}s")
            
            # Log action details
            for i, action in enumerate(actions):
                logger.debug(f"Action {i+1}/{len(actions)}: type={action.action_type}, workflow={action.workflow_name}, "
                           f"confidence={action.confidence_score:.2f}, priority={action.priority}")
            
            # Filter by confidence threshold
            initial_count = len(actions)
            filtered_actions = [
                action for action in actions 
                if action.confidence_score >= self.confidence_threshold
            ]
            filtered_count = initial_count - len(filtered_actions)
            
            if filtered_count > 0:
                logger.info(f"Filtered {filtered_count} low-confidence actions (threshold={self.confidence_threshold})")
            
            # Log low-confidence actions for review
            for action in actions:
                if action.confidence_score < self.confidence_threshold:
                    logger.warning(f"Low confidence action filtered: '{action.description}' "
                                 f"(type={action.action_type}, score={action.confidence_score:.2f})")
            
            total_time = time.time() - start_time
            logger.info(f"Action extraction completed in {total_time:.2f}s: extracted={len(filtered_actions)}, "
                       f"filtered={filtered_count}, document_type={document_type}")
            
            return filtered_actions
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"Failed to extract actions after {total_time:.2f}s: {str(e)}")
            logger.debug(f"Stack trace:", exc_info=True)
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
        Call Claude via CLI for extraction with extensive logging
        """
        start_time = time.time()
        
        try:
            # Use Claude Code CLI for real extraction
            logger.info("Importing Claude CLI module")
            from claude_cli import AsyncClaudeCLI
            
            # Initialize CLI with increased timeout for complex extractions
            cli = AsyncClaudeCLI()
            logger.info(f"Claude CLI initialized with timeout={cli.timeout}s")
            
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
                logger.debug(f"Extracted document text from prompt: {len(document_text)} chars")
            else:
                document_text = prompt
                logger.debug(f"Using full prompt as document text: {len(document_text)} chars")
            
            # Call Claude with structured extraction request
            logger.info("Calling Claude Code CLI for action extraction")
            extraction_prompt = """Extract all actionable items from this document and return ONLY a JSON array.

IMPORTANT: 
- Return ONLY valid JSON, no other text
- If no actions found, return empty array: []
- Each action must have: action_type, workflow_name, description, parameters, confidence_score, priority
- Example format:
[
  {
    "action_type": "invoice_processing",
    "workflow_name": "process_invoice",
    "description": "Process invoice",
    "parameters": {},
    "entities": [],
    "confidence_score": 0.9,
    "confidence_level": "high",
    "priority": 2,
    "deadline": null
  }
]

Look for: invoice processing, approval requests, payments, scheduling, legal review, signatures, and any other actions.
Return ONLY the JSON array, nothing else:"""
            
            api_call_start = time.time()
            result = await cli.analyze_text_async(
                text=document_text,
                prompt=extraction_prompt,
                schema=extraction_schema
            )
            api_call_time = time.time() - api_call_start
            logger.info(f"Claude Code API call completed in {api_call_time:.2f}s")
            
            # Convert result to JSON string if it's a dict
            if isinstance(result, dict):
                # Check for JSON parsing error from claude_cli
                if 'error' in result and result.get('error') == 'JSON parsing failed':
                    logger.warning(f"Claude returned non-JSON response: {result.get('result', 'unknown')[:100]}")
                    logger.info("Using empty array as no actions were found")
                    json_result = "[]"  # Return empty JSON array
                elif 'result' in result:
                    # Validate it's actually JSON-like content
                    result_str = result['result']
                    if isinstance(result_str, str):
                        # Check if it looks like JSON (starts with [ or {)
                        trimmed = result_str.strip()
                        if trimmed and not (trimmed.startswith('[') or trimmed.startswith('{')):
                            logger.warning(f"Claude returned plain text instead of JSON: '{result_str[:100]}'")
                            logger.info("Using empty array as response was not JSON")
                            json_result = "[]"
                        else:
                            # It looks like it might be JSON, but let's validate
                            try:
                                # Try to parse it to validate it's proper JSON
                                test_parse = json.loads(result_str)
                                if not isinstance(test_parse, (list, dict)):
                                    logger.warning(f"Claude returned JSON but not array/object: {type(test_parse).__name__}")
                                    json_result = "[]"
                                else:
                                    json_result = result_str  # Use the original string
                                    logger.debug(f"Valid JSON from 'result' key: {len(json_result)} chars")
                            except json.JSONDecodeError:
                                logger.warning(f"Claude returned invalid JSON: {result_str[:100]}")
                                json_result = "[]"
                    else:
                        # result['result'] is not a string, try to convert it
                        json_result = json.dumps(result['result'])
                        logger.debug(f"Converted 'result' value to JSON: {len(json_result)} chars")
                else:
                    # No 'result' key, wrap the dict in an array
                    json_result = json.dumps([result])
                    logger.debug(f"Wrapped dict result in array: {len(json_result)} chars")
            elif isinstance(result, list):
                json_result = json.dumps(result)
                logger.debug(f"Response is already a list: {len(json_result)} chars")
            else:
                # Plain string or other type
                result_str = str(result)
                logger.warning(f"Unexpected result type {type(result).__name__}: {result_str[:100]}")
                json_result = "[]"
            
            total_time = time.time() - start_time
            logger.info(f"Claude API call successful in {total_time:.2f}s, returning {len(json_result)} chars")
            return json_result
                
        except ImportError as e:
            logger.warning(f"Claude CLI module not found: {e}")
            logger.info("Using fallback simulated response")
            
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
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"Claude Code extraction failed after {total_time:.2f}s: {e}")
            logger.debug(f"Stack trace:", exc_info=True)
            
            logger.info("Using fallback simulated response due to error")
            
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
        """Parse and validate Claude's response with smart fallback for unsupported action types"""
        try:
            # Log the raw response for debugging
            logger.debug(f"Parsing Claude response: {raw_response[:200]}...")
            
            # Parse JSON
            data = json.loads(raw_response)
            
            # Validate it's actually a list
            if not isinstance(data, list):
                logger.error(f"Expected JSON array but got {type(data).__name__}. Response: {raw_response[:100]}")
                if isinstance(data, str):
                    logger.error("Response was parsed as a string, not an array. This indicates a double-encoding issue.")
                return []
            
            # If it's an empty list, return it
            if len(data) == 0:
                logger.info("Claude returned empty array - no actions found")
                return []
            
            # Validate each action
            actions = []
            for i, item in enumerate(data):
                # Make sure item is a dict, not a string
                if not isinstance(item, dict):
                    logger.error(f"Item {i} is {type(item).__name__}, not dict. Value: {str(item)[:100]}")
                    continue  # Skip this item
                try:
                    action = ExtractedAction(**item)
                    actions.append(action)
                except Exception as e:
                    # Smart fallback for unsupported action types
                    error_str = str(e)
                    if 'action_type' in error_str and 'Input should be' in error_str:
                        logger.info(f"Converting unsupported action type '{item.get('action_type')}' to CUSTOM")
                        
                        # Store original action type in parameters
                        if 'parameters' not in item:
                            item['parameters'] = {}
                        item['parameters']['original_action_type'] = item.get('action_type')
                        
                        # Set to CUSTOM type
                        item['action_type'] = 'custom'
                        
                        # Auto-assign workflow based on original type
                        original_type = str(item['parameters']['original_action_type']).lower()
                        if 'nda' in original_type or 'access' in original_type:
                            item['workflow_name'] = item.get('workflow_name', 'document_review')
                        elif 'signature' in original_type:
                            item['workflow_name'] = item.get('workflow_name', 'signature_workflow')
                        elif 'legal' in original_type or 'contract' in original_type:
                            item['workflow_name'] = item.get('workflow_name', 'legal_review')
                        
                        # Retry validation with CUSTOM type
                        try:
                            action = ExtractedAction(**item)
                            actions.append(action)
                            logger.info(f"Successfully converted to CUSTOM action with workflow: {item['workflow_name']}")
                        except Exception as e2:
                            logger.error(f"Failed to validate even with CUSTOM type: {e2}")
                            logger.debug(f"Invalid action data: {item}")
                    else:
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