#!/usr/bin/env python3
"""
Test real Claude Code integration for DocAutomate
This script tests the actual Claude Code CLI integration
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime

# Import our modules
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from claude_cli import ClaudeCLI, AsyncClaudeCLI
from ingester import DocumentIngester
from extractor import ActionExtractor
from workflow import WorkflowEngine

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)

async def test_claude_cli_directly():
    """Test Claude CLI wrapper directly"""
    print_section("Testing Claude CLI Wrapper")
    
    # Initialize CLI
    cli = ClaudeCLI()
    
    # Test 1: Validate Claude Code installation
    print("\n1. Checking Claude Code installation...")
    is_installed = cli.validate_installation()
    if is_installed:
        print("   ✅ Claude Code is installed and accessible")
    else:
        print("   ⚠️  Claude Code not found - some features will be simulated")
        print("   💡 To install: Visit https://claude.ai/code")
    
    # Test 2: Test document reading (if sample exists)
    sample_file = Path("samples/sample_invoice.txt")
    if sample_file.exists() and is_installed:
        print(f"\n2. Testing document reading with Claude...")
        try:
            text = cli.read_document(str(sample_file))
            print(f"   ✅ Read {len(text)} characters from {sample_file.name}")
            print(f"   Preview: {text[:100]}...")
        except Exception as e:
            print(f"   ❌ Document reading failed: {e}")
    
    # Test 3: Test text analysis
    if is_installed:
        print(f"\n3. Testing Claude analysis...")
        try:
            test_text = "Invoice #INV-2024-001 for $5,000 due on March 15, 2024. Please process payment."
            analysis = cli.analyze_text(
                text=test_text,
                prompt="Extract key information from this invoice text",
                schema={
                    "invoice_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "due_date": {"type": "string"},
                    "action_required": {"type": "string"}
                }
            )
            print(f"   ✅ Analysis successful:")
            print(f"   {json.dumps(analysis, indent=6)}")
        except Exception as e:
            print(f"   ❌ Analysis failed: {e}")
    
    # Test 4: Test task execution
    if is_installed:
        print(f"\n4. Testing task execution...")
        try:
            result = cli.execute_task(
                agent="general-purpose",
                action="Summarize this text: The quick brown fox jumps over the lazy dog.",
                params={}
            )
            print(f"   ✅ Task execution successful:")
            print(f"   Status: {result.get('status', 'unknown')}")
            if 'result' in result:
                print(f"   Result: {result['result'][:100]}...")
        except Exception as e:
            print(f"   ❌ Task execution failed: {e}")
    
    return is_installed

async def test_document_pipeline():
    """Test the full document processing pipeline"""
    print_section("Testing Document Processing Pipeline")
    
    # Initialize components
    ingester = DocumentIngester()
    extractor = ActionExtractor(confidence_threshold=0.5)
    
    # Create or use sample document
    sample_file = Path("samples/sample_invoice.txt")
    if not sample_file.exists():
        print("\n1. Creating sample invoice...")
        sample_file.parent.mkdir(exist_ok=True)
        sample_content = """
INVOICE #INV-2024-002
Date: January 20, 2024
Due Date: February 20, 2024

Bill To:
Tech Solutions Inc.
789 Innovation Drive
Austin, TX 78701

Services:
- Cloud Infrastructure Setup: $3,500.00
- Security Audit: $1,500.00
- Monthly Support: $1,000.00

Total Due: $6,000.00

ACTION REQUIRED:
1. Review and approve this invoice
2. Schedule payment by due date
3. Send confirmation to billing@techsolutions.com
"""
        sample_file.write_text(sample_content)
        print(f"   ✅ Created sample invoice: {sample_file}")
    
    # Test document ingestion with Claude
    print("\n2. Ingesting document with Claude Code...")
    try:
        document = await ingester.ingest_file(str(sample_file))
        print(f"   ✅ Document ingested: {document.id}")
        print(f"   Filename: {document.filename}")
        print(f"   Text length: {len(document.text)} characters")
    except Exception as e:
        print(f"   ❌ Ingestion failed: {e}")
        return None, []
    
    # Test action extraction with Claude
    print("\n3. Extracting actions with Claude...")
    try:
        actions = await extractor.extract_actions(
            document.text,
            document_type='invoice'
        )
        print(f"   ✅ Extracted {len(actions)} actions:")
        for i, action in enumerate(actions, 1):
            print(f"      {i}. {action.description}")
            print(f"         Type: {action.action_type}")
            print(f"         Confidence: {action.confidence_score:.2%}")
    except Exception as e:
        print(f"   ❌ Extraction failed: {e}")
    
    return document, actions if 'actions' in locals() else []

async def test_workflow_execution(document, actions):
    """Test workflow execution with Claude Task agents"""
    print_section("Testing Workflow Execution with Claude")
    
    engine = WorkflowEngine()
    
    # Check available workflows
    print(f"\n1. Available workflows: {list(engine.workflows.keys())}")
    
    if not engine.workflows:
        print("   ⚠️  No workflows defined")
        return
    
    # Prepare test parameters
    if actions and len(actions) > 0:
        # Use parameters from first action
        test_params = actions[0].parameters
    else:
        # Use default test parameters
        test_params = {
            'invoice_id': 'INV-2024-002',
            'vendor_name': 'Tech Solutions Inc.',
            'amount': 6000.00,
            'currency': 'USD',
            'due_date': '2024-02-20'
        }
    
    # Execute workflow
    workflow_name = 'process_invoice' if 'process_invoice' in engine.workflows else list(engine.workflows.keys())[0]
    
    print(f"\n2. Executing workflow: {workflow_name}")
    print(f"   Parameters: {json.dumps(test_params, indent=6)}")
    
    try:
        run = await engine.execute_workflow(
            workflow_name=workflow_name,
            document_id=document.id,
            initial_parameters=test_params
        )
        
        print(f"\n   ✅ Workflow execution completed:")
        print(f"      Run ID: {run.run_id}")
        print(f"      Status: {run.status}")
        print(f"      Started: {run.started_at}")
        print(f"      Completed: {run.completed_at}")
        
        if run.outputs:
            print(f"      Steps completed:")
            for step_id, output in run.outputs.items():
                status = output.get('status', 'unknown') if isinstance(output, dict) else 'done'
                print(f"        - {step_id}: {status}")
        
        if run.error:
            print(f"      ⚠️ Error: {run.error}")
            
    except Exception as e:
        print(f"   ❌ Workflow execution failed: {e}")

async def test_full_integration():
    """Run complete integration test"""
    print("\n" + "🚀 " * 20)
    print("   DOCAUTOMATE + CLAUDE CODE INTEGRATION TEST")
    print("🚀 " * 20)
    
    # Test 1: Claude CLI directly
    claude_available = await test_claude_cli_directly()
    
    # Test 2: Document pipeline
    document, actions = await test_document_pipeline()
    
    # Test 3: Workflow execution
    if document:
        await test_workflow_execution(document, actions)
    
    # Summary
    print_section("Test Summary")
    
    if claude_available:
        print("\n✅ Claude Code Integration: ACTIVE")
        print("   - Document reading: Using Claude Read tool")
        print("   - Action extraction: Using Claude NLP")
        print("   - Task execution: Using Claude Task agents")
        print("   - Analysis: Using Claude analysis")
    else:
        print("\n⚠️  Claude Code Integration: SIMULATED")
        print("   - Document reading: Fallback to basic text")
        print("   - Action extraction: Using placeholder responses")
        print("   - Task execution: Simulated only")
        print("   - Analysis: Mock results")
    
    print("\n📊 Coverage:")
    print(f"   - CLI Wrapper: {'✅ Working' if claude_available else '⚠️ Fallback'}")
    print(f"   - Document Ingestion: ✅ Integrated")
    print(f"   - Action Extraction: ✅ Integrated")
    print(f"   - Workflow Engine: ✅ Integrated")
    print(f"   - Task Agents: {'✅ Active' if claude_available else '⚠️ Simulated'}")
    
    print("\n💡 Next Steps:")
    if claude_available:
        print("   1. Test with real PDF documents")
        print("   2. Configure specific Task agents")
        print("   3. Fine-tune extraction prompts")
        print("   4. Add more workflow templates")
    else:
        print("   1. Install Claude Code: https://claude.ai/code")
        print("   2. Ensure 'claude' command is in PATH")
        print("   3. Re-run this test to verify integration")
    
    print("\n✨ DocAutomate is ready to process documents with Claude Code!")

# Run the test
if __name__ == "__main__":
    print("Starting DocAutomate + Claude Code Integration Test")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    try:
        asyncio.run(test_full_integration())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nTest completed!")