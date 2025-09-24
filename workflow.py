#!/usr/bin/env python3
"""
Workflow Execution Engine
Executes YAML-defined workflows with state management
"""

import yaml
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
from jinja2 import Template
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class WorkflowRun:
    """Represents a workflow execution instance"""
    run_id: str
    workflow_name: str
    document_id: str
    status: WorkflowStatus
    current_step: Optional[str]
    parameters: Dict[str, Any]
    state: Dict[str, Any]
    started_at: str
    completed_at: Optional[str]
    error: Optional[str]
    outputs: Dict[str, Any]

class WorkflowEngine:
    """
    Executes workflows defined in YAML files
    Manages state and provides action registry
    """
    
    def __init__(self, workflows_dir: str = "./workflows", state_dir: str = "./state"):
        self.workflows_dir = Path(workflows_dir)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Action registry - maps action types to handler functions
        self.action_registry: Dict[str, Callable] = {
            'api_call': self._execute_api_call,
            'mcp_task': self._execute_mcp_task,
            'send_email': self._execute_send_email,
            'data_transform': self._execute_data_transform,
            'conditional': self._execute_conditional,
            'parallel': self._execute_parallel,
            'webhook': self._execute_webhook,
            'claude_analyze': self._execute_claude_analyze
        }
        
        # Load workflow definitions
        self.workflows = self._load_workflows()
    
    def _load_workflows(self) -> Dict[str, Dict]:
        """Load all workflow definitions from YAML files"""
        workflows = {}
        
        for yaml_file in self.workflows_dir.glob("*.yaml"):
            try:
                with open(yaml_file, 'r') as f:
                    workflow = yaml.safe_load(f)
                    workflows[workflow['name']] = workflow
                    logger.info(f"Loaded workflow: {workflow['name']}")
            except Exception as e:
                logger.error(f"Failed to load workflow {yaml_file}: {e}")
        
        return workflows
    
    async def execute_workflow(
        self,
        workflow_name: str,
        document_id: str,
        initial_parameters: Dict[str, Any]
    ) -> WorkflowRun:
        """
        Execute a workflow with given parameters
        Returns the workflow run result
        """
        if workflow_name not in self.workflows:
            raise ValueError(f"Workflow '{workflow_name}' not found")
        
        workflow = self.workflows[workflow_name]
        
        # Create workflow run
        run = WorkflowRun(
            run_id=self._generate_run_id(),
            workflow_name=workflow_name,
            document_id=document_id,
            status=WorkflowStatus.RUNNING,
            current_step=None,
            parameters=initial_parameters,
            state={},
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            error=None,
            outputs={}
        )
        
        # Save initial state
        await self._save_state(run)
        
        try:
            # Validate parameters
            self._validate_parameters(workflow, initial_parameters)
            
            # Execute workflow steps
            for step in workflow.get('steps', []):
                run.current_step = step['id']
                await self._save_state(run)
                
                logger.info(f"Executing step: {step['id']} ({step.get('description', '')})")
                
                # Resolve template variables
                resolved_config = self._resolve_templates(
                    step.get('config', {}),
                    initial_parameters,
                    run.state
                )
                
                # Execute action
                action_type = step['type']
                if action_type not in self.action_registry:
                    raise ValueError(f"Unknown action type: {action_type}")
                
                action_handler = self.action_registry[action_type]
                result = await action_handler(resolved_config, run.state)
                
                # Store step result
                run.state[f"steps.{step['id']}"] = result
                run.outputs[step['id']] = result
                
                # Check for step failure
                if isinstance(result, dict) and result.get('status') == 'failed':
                    raise Exception(f"Step {step['id']} failed: {result.get('error', 'Unknown error')}")
            
            # Workflow completed successfully
            run.status = WorkflowStatus.SUCCESS
            run.completed_at = datetime.utcnow().isoformat()
            
        except Exception as e:
            # Workflow failed
            logger.error(f"Workflow {workflow_name} failed: {str(e)}")
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.utcnow().isoformat()
        
        # Save final state
        await self._save_state(run)
        
        return run
    
    def _generate_run_id(self) -> str:
        """Generate unique run ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _validate_parameters(self, workflow: Dict, parameters: Dict):
        """Validate parameters against workflow requirements"""
        required_params = workflow.get('parameters', [])
        
        for param_def in required_params:
            param_name = param_def.get('name')
            if param_def.get('required', False) and param_name not in parameters:
                raise ValueError(f"Required parameter '{param_name}' not provided")
            
            # Type validation could be added here
            param_type = param_def.get('type')
            if param_name in parameters and param_type:
                value = parameters[param_name]
                # Simple type checking
                if param_type == 'string' and not isinstance(value, str):
                    raise TypeError(f"Parameter '{param_name}' must be a string")
                elif param_type == 'float' and not isinstance(value, (int, float)):
                    raise TypeError(f"Parameter '{param_name}' must be a number")
    
    def _resolve_templates(
        self,
        config: Dict,
        parameters: Dict,
        state: Dict
    ) -> Dict:
        """Resolve Jinja2 template variables in configuration"""
        def resolve_value(value):
            if isinstance(value, str) and '{{' in value:
                template = Template(value)
                context = {**parameters, 'steps': state}
                return template.render(context)
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(item) for item in value]
            return value
        
        return resolve_value(config)
    
    async def _save_state(self, run: WorkflowRun):
        """Persist workflow run state"""
        state_file = self.state_dir / f"{run.run_id}.json"
        with open(state_file, 'w') as f:
            json.dump(asdict(run), f, indent=2)
    
    # Action Handlers
    
    async def _execute_api_call(self, config: Dict, state: Dict) -> Dict:
        """Execute an API call action"""
        url = config['url']
        method = config.get('method', 'GET')
        headers = config.get('headers', {})
        params = config.get('query_params', {})
        body = config.get('body', None)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body if body else None
                ) as response:
                    result = {
                        'status': 'success',
                        'status_code': response.status,
                        'response': await response.json() if response.content_type == 'application/json' else await response.text()
                    }
                    return result
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    async def _execute_mcp_task(self, config: Dict, state: Dict) -> Dict:
        """Execute a task via MCP/Claude agent"""
        # In production, this would interface with Claude's Task agent system
        agent_name = config.get('agent_name')
        action = config.get('action')
        params = config.get('params', {})
        
        logger.info(f"Executing MCP task: {agent_name}.{action} with params: {params}")
        
        # Simulated execution
        return {
            'status': 'success',
            'agent': agent_name,
            'action': action,
            'result': f"Executed {action} successfully"
        }
    
    async def _execute_send_email(self, config: Dict, state: Dict) -> Dict:
        """Send an email notification"""
        # In production, configure with real SMTP settings
        to = config.get('to')
        subject = config.get('subject')
        body = config.get('body')
        
        logger.info(f"Sending email to {to}: {subject}")
        
        # Simulated email sending
        return {
            'status': 'success',
            'sent_to': to,
            'subject': subject
        }
    
    async def _execute_data_transform(self, config: Dict, state: Dict) -> Dict:
        """Transform data using expressions"""
        transformations = config.get('transformations', {})
        result = {}
        
        for key, expression in transformations.items():
            try:
                # Simple evaluation (in production, use safe evaluation)
                template = Template(expression)
                context = {'state': state, **state}
                result[key] = template.render(context)
            except Exception as e:
                logger.error(f"Transform failed for {key}: {e}")
                result[key] = None
        
        return {
            'status': 'success',
            'transformed': result
        }
    
    async def _execute_conditional(self, config: Dict, state: Dict) -> Dict:
        """Execute conditional logic"""
        condition = config.get('condition')
        if_true = config.get('if_true', {})
        if_false = config.get('if_false', {})
        
        # Evaluate condition (simplified)
        template = Template(condition)
        result = template.render(state=state)
        
        if result.lower() == 'true' or result == '1':
            branch = if_true
        else:
            branch = if_false
        
        # Execute the selected branch
        if branch.get('type'):
            handler = self.action_registry.get(branch['type'])
            if handler:
                return await handler(branch.get('config', {}), state)
        
        return {'status': 'success', 'branch_taken': 'true' if result else 'false'}
    
    async def _execute_parallel(self, config: Dict, state: Dict) -> Dict:
        """Execute multiple actions in parallel"""
        tasks = config.get('tasks', [])
        
        async def run_task(task):
            handler = self.action_registry.get(task['type'])
            if handler:
                return await handler(task.get('config', {}), state)
            return {'status': 'failed', 'error': f"Unknown task type: {task['type']}"}
        
        results = await asyncio.gather(*[run_task(task) for task in tasks])
        
        return {
            'status': 'success',
            'results': results
        }
    
    async def _execute_webhook(self, config: Dict, state: Dict) -> Dict:
        """Execute a webhook call"""
        # Similar to API call but with webhook-specific handling
        return await self._execute_api_call(config, state)
    
    async def _execute_claude_analyze(self, config: Dict, state: Dict) -> Dict:
        """Use Claude to analyze data"""
        prompt = config.get('prompt')
        data = config.get('data')
        
        logger.info(f"Claude analysis requested: {prompt[:100]}...")
        
        # In production, this would call Claude API
        # Simulated response
        return {
            'status': 'success',
            'analysis': f"Analysis complete for: {prompt[:50]}...",
            'insights': ["Insight 1", "Insight 2", "Insight 3"]
        }
    
    def get_run_status(self, run_id: str) -> Optional[WorkflowRun]:
        """Get status of a workflow run"""
        state_file = self.state_dir / f"{run_id}.json"
        if not state_file.exists():
            return None
        
        with open(state_file, 'r') as f:
            data = json.load(f)
            return WorkflowRun(**data)
    
    def list_runs(self, workflow_name: Optional[str] = None) -> List[WorkflowRun]:
        """List all workflow runs, optionally filtered by workflow name"""
        runs = []
        
        for state_file in self.state_dir.glob("*.json"):
            with open(state_file, 'r') as f:
                data = json.load(f)
                run = WorkflowRun(**data)
                if workflow_name is None or run.workflow_name == workflow_name:
                    runs.append(run)
        
        return sorted(runs, key=lambda x: x.started_at, reverse=True)

# Example usage
if __name__ == "__main__":
    async def main():
        engine = WorkflowEngine()
        
        # Example parameters
        params = {
            'invoice_id': 'INV-2024-001',
            'amount': 5000.00,
            'vendor_name': 'ABC Corp'
        }
        
        # Execute workflow (would need actual workflow YAML file)
        # run = await engine.execute_workflow('process_invoice', 'doc123', params)
        # print(f"Workflow run {run.run_id}: {run.status}")
        
        print("Workflow Engine initialized")
        print(f"Loaded workflows: {list(engine.workflows.keys())}")
        print(f"Available actions: {list(engine.action_registry.keys())}")
    
    asyncio.run(main())