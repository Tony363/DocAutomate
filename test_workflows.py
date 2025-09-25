import asyncio
import json
from datetime import datetime
from workflow import WorkflowEngine

async def test_all_workflows():
    engine = WorkflowEngine()
    
    # Test data for different workflows
    test_cases = [
        {
            'workflow': 'document_signature',
            'params': {
                'document_id': 'be31df81bdf7fcfb',
                'document_type': 'NDA',
                'parties': ['YOOBROO, INC.', 'TONY LIU'],
                'effective_date': '2025-06-30',
                'signature_fields': ['Recipient signature', 'Recipient address'],
                'original_action_type': 'signature_required'
            }
        },
        {
            'workflow': 'complete_missing_info',
            'params': {
                'document_id': 'be31df81bdf7fcfb',
                'field': 'recipient_address',
                'party': 'TONY LIU',
                'required': True,
                'original_action_type': 'address_completion'
            }
        },
        {
            'workflow': 'legal_compliance',
            'params': {
                'document_id': 'be31df81bdf7fcfb',
                'trigger': 'unauthorized_use_or_disclosure',
                'action': 'immediate_written_notification',
                'recipient': 'Company',
                'original_action_type': 'compliance_notification'
            }
        },
        {
            'workflow': 'document_management',
            'params': {
                'document_id': 'be31df81bdf7fcfb',
                'trigger': ['termination', 'written_request'],
                'action': ['return_all_information', 'destroy_and_certify'],
                'timeline': '5_days',
                'original_action_type': 'document_return'
            }
        }
    ]
    
    results = []
    
    for test in test_cases:
        workflow_name = test['workflow']
        params = test['params']
        
        print(f'\n{"="*60}')
        print(f'Testing: {workflow_name}')
        print(f'{"="*60}')
        
        try:
            result = await engine.execute_workflow(
                workflow_name,
                params['document_id'],
                params
            )
            
            status = 'SUCCESS' if result.status.name == 'SUCCESS' else 'FAILED'
            print(f'Status: {status}')
            print(f'Workflow Run ID: {result.run_id}')
            
            # Check completed steps
            if hasattr(result, 'outputs') and result.outputs:
                print(f'Completed steps: {len(result.outputs)}')
            
            results.append({
                'workflow': workflow_name,
                'status': status,
                'run_id': result.run_id
            })
            
        except Exception as e:
            print(f'Error: {e}')
            results.append({
                'workflow': workflow_name,
                'status': 'ERROR',
                'error': str(e)
            })
    
    # Summary
    print(f'\n{"="*60}')
    print('SUMMARY')
    print(f'{"="*60}')
    
    for result in results:
        status_icon = '✅' if result['status'] == 'SUCCESS' else '❌'
        print(f'{status_icon} {result["workflow"]}: {result["status"]}')
    
    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    print(f'\nTotal: {success_count}/{len(results)} workflows executed successfully')

if __name__ == '__main__':
    asyncio.run(test_all_workflows())
