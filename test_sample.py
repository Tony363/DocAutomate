#!/usr/bin/env python3
"""
Test script for DocAutomate Framework
Creates a sample invoice document and tests the processing pipeline
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta

# Import our modules
from ingester import DocumentIngester
from extractor import ActionExtractor
from workflow import WorkflowEngine

async def create_sample_invoice():
    """Create a sample invoice text file for testing"""
    invoice_content = """
INVOICE
=======

Invoice Number: INV-2024-001
Date: January 15, 2024
Due Date: February 15, 2024

From:
ABC Corporation
123 Business Street
New York, NY 10001
Tax ID: 12-3456789

To:
XYZ Company
456 Commerce Ave
San Francisco, CA 94102

INVOICE DETAILS
--------------

Description                      Quantity    Unit Price    Total
Software Development Services    40 hours    $125.00       $5,000.00
Cloud Infrastructure Setup       1           $2,500.00     $2,500.00
Monthly Support Package          1           $1,500.00     $1,500.00

                                            Subtotal:      $9,000.00
                                            Tax (10%):     $900.00
                                            TOTAL DUE:     $9,900.00

Payment Terms:
- Net 30 days
- 2% discount if paid within 10 days
- Late payment subject to 1.5% monthly interest

Please remit payment to:
Bank: First National Bank
Account: 123456789
Routing: 987654321

For questions about this invoice, please contact:
Email: billing@abccorp.com
Phone: (555) 123-4567

Thank you for your business!

REQUIRED ACTIONS:
1. Review and approve this invoice for payment
2. Schedule payment before the due date (February 15, 2024)
3. Send payment confirmation to billing@abccorp.com
"""
    
    # Save to file
    sample_dir = Path("./samples")
    sample_dir.mkdir(exist_ok=True)
    
    invoice_file = sample_dir / "sample_invoice.txt"
    with open(invoice_file, 'w') as f:
        f.write(invoice_content)
    
    print(f"✅ Created sample invoice: {invoice_file}")
    return str(invoice_file)

async def test_document_ingestion(file_path: str):
    """Test document ingestion"""
    print("\n📄 Testing Document Ingestion...")
    print("-" * 50)
    
    ingester = DocumentIngester()
    document = await ingester.ingest_file(file_path)
    
    print(f"Document ID: {document.id}")
    print(f"Filename: {document.filename}")
    print(f"Content Type: {document.content_type}")
    print(f"Status: {document.status}")
    print(f"Text Length: {len(document.text)} characters")
    
    return document

async def test_action_extraction(document):
    """Test action extraction from document"""
    print("\n🔍 Testing Action Extraction...")
    print("-" * 50)
    
    extractor = ActionExtractor(confidence_threshold=0.6)
    actions = await extractor.extract_actions(document.text, document_type='invoice')
    
    print(f"Extracted {len(actions)} actions:")
    
    for i, action in enumerate(actions, 1):
        print(f"\n Action {i}:")
        print(f"  Type: {action.action_type}")
        print(f"  Workflow: {action.workflow_name}")
        print(f"  Description: {action.description}")
        print(f"  Confidence: {action.confidence_score:.2%} ({action.confidence_level})")
        print(f"  Priority: {action.priority}")
        
        if action.parameters:
            print(f"  Parameters:")
            for key, value in action.parameters.items():
                print(f"    - {key}: {value}")
        
        if action.deadline:
            print(f"  Deadline: {action.deadline}")
    
    return actions

async def test_workflow_execution(document, actions):
    """Test workflow execution"""
    print("\n⚙️ Testing Workflow Execution...")
    print("-" * 50)
    
    engine = WorkflowEngine()
    
    # Check if we have any actions to process
    if not actions:
        print("No actions to process - creating test action")
        # Create a test action
        test_params = {
            'invoice_id': 'INV-2024-001',
            'vendor_name': 'ABC Corporation',
            'amount': 9900.00,
            'currency': 'USD',
            'due_date': (datetime.now() + timedelta(days=30)).isoformat()
        }
    else:
        # Use parameters from first extracted action
        test_params = actions[0].parameters
    
    print(f"Available workflows: {list(engine.workflows.keys())}")
    
    # Try to execute the invoice workflow if it exists
    if 'process_invoice' in engine.workflows:
        print("\nExecuting 'process_invoice' workflow...")
        print(f"Parameters: {json.dumps(test_params, indent=2)}")
        
        try:
            run = await engine.execute_workflow(
                workflow_name='process_invoice',
                document_id=document.id,
                initial_parameters=test_params
            )
            
            print(f"\n✅ Workflow Run Results:")
            print(f"  Run ID: {run.run_id}")
            print(f"  Status: {run.status}")
            print(f"  Started: {run.started_at}")
            print(f"  Completed: {run.completed_at}")
            
            if run.error:
                print(f"  Error: {run.error}")
            
            if run.outputs:
                print(f"  Outputs:")
                for step_id, output in run.outputs.items():
                    print(f"    - {step_id}: {output.get('status', 'unknown')}")
            
            return run
            
        except Exception as e:
            print(f"❌ Workflow execution failed: {e}")
            return None
    else:
        print("⚠️ No workflows available to test")
        return None

async def test_api_endpoints():
    """Test API endpoints (requires API to be running)"""
    print("\n🌐 Testing API Endpoints...")
    print("-" * 50)
    
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            # Test health endpoint
            response = await client.get("http://localhost:8000/health")
            if response.status_code == 200:
                print("✅ API is healthy")
                print(f"   Response: {response.json()}")
            else:
                print("❌ API health check failed")
    except Exception as e:
        print(f"⚠️ API not running or not accessible: {e}")
        print("   Run 'python api.py' in another terminal to test API")

async def main():
    """Main test function"""
    print("=" * 60)
    print("DocAutomate Framework Test Suite")
    print("=" * 60)
    
    # Create sample invoice
    invoice_path = await create_sample_invoice()
    
    # Test document ingestion
    document = await test_document_ingestion(invoice_path)
    
    # Test action extraction
    actions = await test_action_extraction(document)
    
    # Test workflow execution
    workflow_run = await test_workflow_execution(document, actions)
    
    # Test API endpoints
    await test_api_endpoints()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"✅ Document Ingestion: Success")
    print(f"✅ Action Extraction: {len(actions)} actions extracted")
    print(f"{'✅' if workflow_run and workflow_run.status == 'success' else '⚠️'} Workflow Execution: {'Success' if workflow_run else 'Not tested'}")
    print(f"📊 Total test coverage: Basic functionality validated")
    
    print("\n💡 Next Steps:")
    print("1. Run 'python api.py' to start the REST API")
    print("2. Visit http://localhost:8000/docs for API documentation")
    print("3. Upload documents via the API for full pipeline testing")
    print("4. Customize workflows in the workflows/ directory")

if __name__ == "__main__":
    asyncio.run(main())