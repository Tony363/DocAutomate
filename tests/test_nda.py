#!/usr/bin/env python3
"""Test NDA document processing with the improved extractor"""

import asyncio
import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from extractor import ActionExtractor

async def test_nda_extraction():
    """Test NDA document extraction with file_access_request action"""
    
    # Simulated NDA document content
    nda_content = """
    NON-DISCLOSURE AGREEMENT
    
    This Non-Disclosure Agreement ("Agreement") is entered into as of January 15, 2024,
    between Tony (the "Disclosing Party") and Yoobroo Inc. (the "Receiving Party").
    
    WHEREAS, the Disclosing Party possesses certain confidential and proprietary information
    relating to software development and business operations;
    
    NOW, THEREFORE, the parties agree as follows:
    
    1. CONFIDENTIAL INFORMATION
    The Receiving Party acknowledges that it will have access to confidential information
    including but not limited to source code, business plans, and customer data.
    
    2. OBLIGATIONS
    The Receiving Party agrees to:
    - Maintain strict confidentiality of all disclosed information
    - Not disclose any confidential information to third parties
    - Request file access permission before accessing any confidential documents
    - Return all confidential materials upon termination of this agreement
    
    3. TERM
    This Agreement shall remain in effect for a period of two (2) years from the date
    first written above.
    
    4. SIGNATURES REQUIRED
    Both parties must sign this agreement for it to be legally binding.
    
    By signing below, the parties acknowledge and agree to the terms set forth above.
    
    _______________________        _______________________
    Tony (Disclosing Party)         Yoobroo Inc. (Receiving Party)
    Date: _____________            Date: _____________
    """
    
    # Initialize extractor
    extractor = ActionExtractor(confidence_threshold=0.0)  # Low threshold for testing
    
    print("=" * 60)
    print("Testing NDA Document Processing")
    print("=" * 60)
    
    # Extract actions - should auto-detect as NDA
    actions = await extractor.extract_actions(nda_content)
    
    print(f"\n✅ Extracted {len(actions)} actions from NDA document")
    
    for i, action in enumerate(actions, 1):
        print(f"\n📋 Action {i}:")
        print(f"   Type: {action.action_type}")
        print(f"   Workflow: {action.workflow_name}")
        print(f"   Description: {action.description}")
        print(f"   Confidence: {action.confidence_score:.2f} ({action.confidence_level})")
        
        # Check if original_action_type was preserved
        if 'original_action_type' in action.parameters:
            print(f"   ✨ Original Action Type (preserved): {action.parameters['original_action_type']}")
        
        # Show parameters
        if action.parameters:
            print(f"   Parameters:")
            for key, value in action.parameters.items():
                print(f"      - {key}: {value}")
    
    # Test the smart fallback directly
    print("\n" + "=" * 60)
    print("Testing Smart Fallback Mechanism")
    print("=" * 60)
    
    # Simulate Claude's response with file_access_request
    simulated_claude_response = json.dumps([
        {
            "action_type": "file_access_request",  # This would normally fail validation
            "workflow_name": "nda_review",
            "description": "Request file access permission for confidential documents",
            "parameters": {
                "document_type": "nda",
                "parties": ["Tony", "Yoobroo Inc."],
                "confidential_scope": "source code, business plans, customer data"
            },
            "confidence_score": 0.95,
            "confidence_level": "high",
            "priority": 1,
            "deadline": "2024-01-20"
        },
        {
            "action_type": "signature_request",  # This should work now
            "workflow_name": "signature_workflow",
            "description": "Obtain signatures from both parties",
            "parameters": {
                "signers": ["Tony", "Yoobroo Inc."],
                "document_type": "nda"
            },
            "confidence_score": 0.90,
            "confidence_level": "high",
            "priority": 1,
            "deadline": "2024-01-20"
        }
    ])
    
    # Test parsing with smart fallback
    parsed_actions = extractor._parse_claude_response(simulated_claude_response)
    
    print(f"\n✅ Smart fallback processed {len(parsed_actions)} actions")
    
    for i, action in enumerate(parsed_actions, 1):
        print(f"\n📋 Parsed Action {i}:")
        print(f"   Type: {action.action_type}")
        print(f"   Workflow: {action.workflow_name}")
        
        if action.action_type == 'custom' and 'original_action_type' in action.parameters:
            print(f"   ✨ Smart Fallback Applied!")
            print(f"   Original Type: {action.parameters['original_action_type']}")
            print(f"   Converted to: CUSTOM")
            print(f"   Preserved in parameters: ✅")
    
    print("\n" + "=" * 60)
    print("✅ NDA Document Processing Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_nda_extraction())