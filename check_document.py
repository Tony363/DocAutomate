#!/usr/bin/env python3
"""
Check document processing status
"""

import requests
import json
import sys

def check_document(doc_id):
    """Check the status of a document"""
    
    # Get document status
    response = requests.get(f"http://localhost:8001/documents/{doc_id}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Document ID: {data['document_id']}")
        print(f"Status: {data['status']}")
        print(f"Filename: {data['filename']}")
        print(f"Workflow runs: {data.get('workflow_runs', [])}")
        
        actions = data.get('extracted_actions')
        if actions:
            print(f"\nExtracted {len(actions)} actions:")
            for i, action in enumerate(actions, 1):
                print(f"  {i}. {action.get('action_type', 'unknown')}: {action.get('description', 'N/A')}")
        else:
            print("\nNo actions extracted yet")
            
        return data
    else:
        print(f"Failed to get document: {response.status_code}")
        return None

def list_recent_documents():
    """List recent documents"""
    response = requests.get("http://localhost:8001/documents")
    
    if response.status_code == 200:
        docs = response.json()
        print(f"Found {len(docs)} documents:\n")
        
        for doc in docs[-5:]:  # Show last 5
            print(f"- {doc['document_id']}: {doc['filename']} [{doc['status']}]")
            if doc.get('extracted_actions'):
                print(f"  Actions: {len(doc['extracted_actions'])}")
            else:
                print(f"  Actions: None")
        
        return docs
    else:
        print(f"Failed to list documents: {response.status_code}")
        return []

if __name__ == "__main__":
    if len(sys.argv) > 1:
        doc_id = sys.argv[1]
        check_document(doc_id)
    else:
        print("Recent documents:")
        print("-" * 40)
        list_recent_documents()