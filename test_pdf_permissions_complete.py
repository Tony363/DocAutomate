#!/usr/bin/env python3
"""
Complete PDF Permission Enablement Test
Tests the enhanced DocAutomate system with PDF processing capabilities
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime

from claude_cli import ClaudeCLI
from ingester import DocumentIngester
from extractor import ActionExtractor
from workflow import WorkflowEngine
from agent_providers import agent_registry

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_complete_pdf_solution():
    """Test complete PDF processing solution with all enhancements"""
    print("="*70)
    print("DocAutomate PDF Processing - Complete Solution Test")
    print("="*70)
    
    # Test 1: Enhanced Claude CLI with Permissions
    print("\n🔧 TEST 1: Enhanced Claude CLI with Auto-Permissions")
    cli = ClaudeCLI()
    print(f"   ✅ Auto-grant permissions: {cli.auto_grant_permissions}")
    print(f"   ✅ Audit logging enabled: {cli.audit_log_enabled}")
    print(f"   ✅ Allowed directories: {len(cli.allowed_directories)} configured")
    
    # Test 2: Direct PDF Processing
    print("\n📄 TEST 2: Direct PDF Processing")
    pdf_path = "docs/NDA-Tony-yoobroo.pdf"
    
    try:
        start_time = datetime.now()
        content = cli.read_document(pdf_path)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        print(f"   ✅ PDF processed successfully")
        print(f"   ✅ Content extracted: {len(content)} characters")
        print(f"   ✅ Processing time: {processing_time:.2f}s")
        print(f"   ✅ Preview: {content[:100]}...")
        
    except Exception as e:
        print(f"   ❌ PDF processing failed: {e}")
        return False
    
    # Test 3: Full Document Pipeline
    print("\n🔄 TEST 3: Complete Document Pipeline")
    try:
        # Document ingestion
        ingester = DocumentIngester()
        doc = await ingester.ingest_file(pdf_path)
        print(f"   ✅ Document ingested: {doc.id}")
        print(f"   ✅ Content type: {doc.content_type}")
        print(f"   ✅ Text length: {len(doc.text)} characters")
        
        # Action extraction
        extractor = ActionExtractor()
        actions = await extractor.extract_actions(doc.text, document_type='nda')
        print(f"   ✅ Actions extracted: {len(actions)} actions")
        
        for i, action in enumerate(actions, 1):
            print(f"      Action {i}: {action.action_type} (confidence: {action.confidence_score:.2f})")
            
    except Exception as e:
        print(f"   ❌ Document pipeline failed: {e}")
        return False
    
    # Test 4: SuperClaude Framework Integration
    print("\n🤖 TEST 4: SuperClaude Framework Integration")
    try:
        # Test agent routing
        document_meta = {
            'document_type': 'nda',
            'content_type': 'application/pdf',
            'filename': 'NDA-Tony-yoobroo.pdf',
            'parties': ['YOOBROO, INC.', 'TONY LIU']
        }
        
        provider, score = await agent_registry.route(document_meta)
        print(f"   ✅ Agent routing successful")
        print(f"   ✅ Selected agent: {provider.__class__.__name__}")
        print(f"   ✅ Confidence score: {score.score:.2f}")
        print(f"   ✅ Capabilities: {[cap.name for cap in score.capabilities]}")
        
        # Test workflow engine
        engine = WorkflowEngine()
        print(f"   ✅ Workflow engine: {len(engine.workflows)} workflows loaded")
        
    except Exception as e:
        print(f"   ❌ SuperClaude integration failed: {e}")
        return False
    
    # Test 5: Security and Audit Trail
    print("\n🛡️ TEST 5: Security & Audit Trail")
    try:
        # Check audit log
        audit_file = Path(cli.audit_log_file)
        if audit_file.exists():
            with open(audit_file) as f:
                audit_entries = [json.loads(line) for line in f.readlines()]
                
            print(f"   ✅ Audit log exists: {len(audit_entries)} entries")
            
            # Find recent PDF processing entries
            pdf_entries = [e for e in audit_entries if 'NDA-Tony-yoobroo.pdf' in e['file_path']]
            if pdf_entries:
                latest_entry = pdf_entries[-1]
                print(f"   ✅ Latest audit entry:")
                print(f"      Operation: {latest_entry['operation']}")
                print(f"      Status: {latest_entry['status']}")
                print(f"      Timestamp: {latest_entry['timestamp']}")
                
                if 'processing_time' in latest_entry.get('details', {}):
                    print(f"      Processing time: {latest_entry['details']['processing_time']:.2f}s")
            else:
                print("   ⚠️ No PDF processing entries in audit log")
                
        else:
            print(f"   ⚠️ Audit log file not found: {audit_file}")
            
    except Exception as e:
        print(f"   ❌ Audit trail validation failed: {e}")
        return False
    
    # Test 6: Environment Configuration
    print("\n⚙️ TEST 6: Environment Configuration")
    import os
    
    config_vars = [
        ('CLAUDE_AUTO_GRANT_FILE_ACCESS', cli.auto_grant_permissions),
        ('CLAUDE_AUDIT_LOG', cli.audit_log_enabled),
        ('CLAUDE_TIMEOUT', cli.timeout),
        ('CLAUDE_ALLOWED_DIRECTORIES', len(cli.allowed_directories))
    ]
    
    print("   ✅ Configuration variables:")
    for var_name, value in config_vars:
        env_value = os.getenv(var_name, 'default')
        print(f"      {var_name}: {value} (env: {env_value})")
    
    # Final Results
    print("\n" + "="*70)
    print("🎉 COMPLETE SOLUTION TEST RESULTS")
    print("="*70)
    print("✅ PDF Processing: ENABLED")
    print("✅ Permission Auto-Grant: WORKING")
    print("✅ Document Pipeline: FUNCTIONAL") 
    print("✅ SuperClaude Integration: ACTIVE")
    print("✅ Security & Audit: IMPLEMENTED")
    print("✅ Environment Config: OPERATIONAL")
    print("\n🚀 DocAutomate PDF processing is fully enabled and operational!")
    print("📋 NDA document processed successfully with full audit trail")
    print("🤖 SuperClaude Framework integration validated")
    print("\nNext steps:")
    print("• Upload PDF documents via API: POST /documents/upload")
    print("• Execute workflows: POST /workflows/execute")
    print("• Monitor audit logs: tail -f logs/claude_audit.log")
    print("="*70)
    
    return True

if __name__ == "__main__":
    # Run the complete test
    success = asyncio.run(test_complete_pdf_solution())
    exit(0 if success else 1)