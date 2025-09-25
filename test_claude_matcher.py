#!/usr/bin/env python3
"""
Test the Claude-based workflow matching system
"""

import asyncio
import logging
from workflow import WorkflowEngine
from workflow_matcher import WorkflowMatcher, MatchResult

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_workflow_matching():
    """Test the workflow matching with various name variations"""
    
    print("\n" + "="*60)
    print("CLAUDE-BASED WORKFLOW MATCHING TEST")
    print("="*60 + "\n")
    
    # Initialize workflow engine to get available workflows
    engine = WorkflowEngine()
    
    # Initialize the matcher
    matcher = WorkflowMatcher(engine)
    
    print("Available workflows:")
    for wf_name in engine.workflows.keys():
        print(f"  - {wf_name}")
    print()
    
    # Test cases that were failing
    test_cases = [
        # Original failures from the error log
        ('nda_signature', {'action_type': 'signature', 'document_type': 'nda'}),
        ('complete_missing_information', {'action_type': 'complete', 'field': 'address'}),
        ('confidential_info_return', {'action_type': 'return', 'document_type': 'confidential'}),
        
        # Additional test cases
        ('document_signature', {}),  # Direct match
        ('complete_recipient_info', {}),  # Previous alias
        ('complete_agreement_date', {}),  # Previous alias
        ('contract_signature', {'document_type': 'contract'}),  # Semantic variation
        ('sign_document', {}),  # Action-based name
        ('invoice_processing', {'document_type': 'invoice'}),  # Invoice variation
        ('legal_review', {'document_type': 'legal'}),  # Legal document
        ('random_unknown_workflow_xyz', {}),  # Should use fallback
    ]
    
    print("Testing workflow matching:\n")
    print(f"{'Requested':<35} {'Matched':<25} {'Confidence':>10} {'Reason':<20}")
    print("-" * 90)
    
    success_count = 0
    total_count = len(test_cases)
    
    for requested_name, context in test_cases:
        try:
            result = await matcher.match(requested_name, context)
            
            # Format output
            status = "✅" if result.confidence >= 0.7 else "⚠️" if result.confidence >= 0.3 else "❌"
            
            print(f"{status} {requested_name:<32} {result.matched_workflow:<25} {result.confidence:>8.2f} {result.reason:<20}")
            
            if result.reasoning:
                print(f"   └─ {result.reasoning}")
            
            # Count as success if we found a match with reasonable confidence
            if result.confidence >= 0.3:
                success_count += 1
                
        except Exception as e:
            print(f"❌ {requested_name:<32} ERROR: {e}")
    
    print("-" * 90)
    print(f"\nResults: {success_count}/{total_count} workflows successfully matched")
    
    # Test the specific failures from the log
    print("\n" + "="*60)
    print("TESTING SPECIFIC ERROR CASES")
    print("="*60 + "\n")
    
    error_cases = [
        'nda_signature',
        'complete_missing_information', 
        'confidential_info_return'
    ]
    
    for workflow_name in error_cases:
        result = await matcher.match(workflow_name, {})
        
        print(f"Error case: '{workflow_name}'")
        print(f"  Resolution: '{result.matched_workflow}'")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Reason: {result.reason}")
        
        if result.matched_workflow in engine.workflows:
            print(f"  ✅ Resolved to existing workflow!")
        else:
            print(f"  ❌ Still unresolved")
        print()
    
    # Show cache effectiveness
    print("Cache statistics:")
    print(f"  Cached entries: {len(matcher._match_cache)}")
    
    # Test cache hit
    print("\nTesting cache hit (should be instant):")
    import time
    start = time.time()
    result = await matcher.match('nda_signature', {'action_type': 'signature', 'document_type': 'nda'})
    elapsed = time.time() - start
    print(f"  Cached lookup took: {elapsed:.4f}s")
    print(f"  Result: {result.matched_workflow} (confidence: {result.confidence:.2f})")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_workflow_matching())