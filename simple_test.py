import asyncio
from workflow import WorkflowEngine

async def simple_test():
    engine = WorkflowEngine()
    
    # Test just the template resolution with a simple workflow
    print("Testing template resolution...")
    
    # Create a simple test config
    config = {
        "url": "https://test.com/{{ document_id }}",
        "body": {
            "id": "{{ document_id }}",
            "parties": "{{ parties | join(', ') }}"
        }
    }
    
    params = {
        "document_id": "test123",
        "parties": ["Party A", "Party B"]
    }
    
    # Mock state with steps
    state = {
        "steps": {
            "step1": {"analysis": {"result": "completed"}}
        }
    }
    
    # Test template resolution
    resolved = engine._resolve_templates(config, params, state)
    print("Resolved config:", resolved)
    
    # Test if we can access steps in templates
    test_template = "{{ steps.step1.analysis.result }}"
    from jinja2 import Template
    template = Template(test_template)
    context = {**params, 'steps': state.get('steps', {})}
    resolved_value = template.render(context)
    print(f"Template '{test_template}' resolves to: '{resolved_value}'")

asyncio.run(simple_test())
