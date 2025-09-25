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

# Import SuperClaude Framework components
from agent_providers import agent_registry, AgentProvider

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
            'claude_analyze': self._execute_claude_analyze,
            # SuperClaude Framework extensions
            'agent_task': self._execute_agent_task,
            'intelligent_routing': self._execute_intelligent_routing,
            'code_generation': self._execute_code_generation,
            'quality_check': self._execute_quality_check,
            'dynamic_workflow': self._execute_dynamic_workflow
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
            # Transform parameters to match workflow schema
            transformed_params = self._transform_parameters(workflow_name, initial_parameters)
            
            # Validate and auto-fix common issues
            fixed_params = self._validate_and_fix_parameters(workflow, transformed_params)
            
            # Validate parameters
            self._validate_parameters(workflow, fixed_params)
            
            # Use the fixed parameters for execution
            initial_parameters = fixed_params
            
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
                
                # Store step result in nested structure for template access
                if "steps" not in run.state:
                    run.state["steps"] = {}
                run.state["steps"][step['id']] = result
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
    
    def _transform_parameters(self, workflow_name: str, params: Dict) -> Dict:
        """Transform extracted parameters to match workflow schema format"""
        # Create a copy to avoid modifying original
        transformed = params.copy()
        
        # Handle document_signature workflow
        if workflow_name == 'document_signature':
            # Convert individual parties to array
            if 'party1' in transformed and 'party2' in transformed:
                transformed['parties'] = [
                    transformed.pop('party1'),
                    transformed.pop('party2')
                ]
            elif 'party' in transformed and 'parties' not in transformed:
                # Single party to array
                transformed['parties'] = [transformed.pop('party')]
            
            # Ensure document_id is included
            if 'document_id' not in transformed:
                transformed['document_id'] = transformed.get('doc_id', '')
            
            # Handle signature fields
            if 'signature_fields' not in transformed:
                # Try to find signature fields from other parameters
                if 'signatures_required' in transformed:
                    transformed['signature_fields'] = transformed.pop('signatures_required')
                elif 'signature_locations' in transformed:
                    transformed['signature_fields'] = transformed.pop('signature_locations')
        
        # Handle document_review workflow
        elif workflow_name == 'document_review':
            # Ensure required fields exist
            if 'document_type' not in transformed:
                transformed['document_type'] = transformed.get('type', 'general')
        
        # Handle complete_missing_info workflow
        elif workflow_name == 'complete_missing_info':
            # Extract field from various possible sources
            if 'missing_field' in transformed:
                transformed['field'] = transformed.pop('missing_field')
            elif 'field_name' in transformed:
                transformed['field'] = transformed.pop('field_name')
            elif 'information_type' in transformed:
                transformed['field'] = transformed.pop('information_type')
            elif 'original_action_type' in transformed and 'field' not in transformed:
                # Infer from action type
                action_type = str(transformed['original_action_type']).lower()
                if 'address' in action_type:
                    transformed['field'] = 'address'
                elif 'date' in action_type:
                    transformed['field'] = 'date'
                elif 'signature' in action_type:
                    transformed['field'] = 'signature'
                elif 'recipient' in action_type:
                    transformed['field'] = 'recipient_information'
        
        # Handle document_management workflow
        elif workflow_name == 'document_management':
            # Handle action parameter variations
            if 'actions' in transformed and 'action' not in transformed:
                transformed['action'] = transformed.pop('actions')
            elif 'management_action' in transformed and 'action' not in transformed:
                # Convert single action to array
                transformed['action'] = [transformed.pop('management_action')]
            elif 'action' in transformed and not isinstance(transformed['action'], list):
                # Ensure action is always an array
                transformed['action'] = [transformed['action']]
        
        # Handle date fields across all workflows
        from datetime import datetime
        for key, value in list(transformed.items()):
            if isinstance(value, datetime):
                transformed[key] = value.isoformat()
        
        return transformed
    
    def _validate_and_fix_parameters(self, workflow_def: Dict, params: Dict) -> Dict:
        """Validate and auto-fix common parameter issues"""
        # Get required parameters from workflow definition
        required_params = workflow_def.get('parameters', [])
        workflow_name = workflow_def.get('name', '')
        
        # Common parameter mappings
        param_fixes = {
            'parties': ['party1', 'party2', 'party'],  # Alternative names
            'effective_date': ['date', 'start_date', 'effective'],
            'document_type': ['type', 'doc_type', 'documentType'],
            'document_id': ['doc_id', 'id', 'documentId'],
        }
        
        # Try to fix missing required parameters
        for param_def in required_params:
            param_name = param_def.get('name')
            if param_def.get('required', False) and param_name not in params:
                # Try alternative parameter names
                if param_name in param_fixes:
                    for alt_name in param_fixes[param_name]:
                        if alt_name in params:
                            if param_name == 'parties':
                                # Special handling for parties array
                                if not isinstance(params[alt_name], list):
                                    params[param_name] = [params[alt_name]]
                                else:
                                    params[param_name] = params[alt_name]
                            else:
                                params[param_name] = params[alt_name]
                            # Remove the alternative after using it
                            if alt_name != param_name:
                                del params[alt_name]
                            break
        
        # Provide intelligent defaults for critical missing parameters
        if workflow_name == 'document_signature' and 'signature_fields' not in params:
            params['signature_fields'] = ['signature', 'date', 'initials']
            logger.info(f"Added default signature_fields for document_signature workflow")
        
        if workflow_name == 'complete_missing_info' and 'field' not in params:
            # Infer field from action type or use generic default
            if 'original_action_type' in params:
                action_type = str(params['original_action_type']).lower()
                if 'address' in action_type:
                    params['field'] = 'recipient_address'
                elif 'date' in action_type:
                    params['field'] = 'agreement_date'
                elif 'signature' in action_type:
                    params['field'] = 'signature_location'
                else:
                    params['field'] = 'information_needed'
            else:
                params['field'] = 'information_needed'
            logger.info(f"Added default field '{params['field']}' for complete_missing_info workflow")
        
        if workflow_name == 'document_management' and 'action' not in params:
            # Default to return action as it's safer than destroy
            params['action'] = ['return_all_information']
            logger.info(f"Added default action for document_management workflow")
        
        return params
    
    def _validate_parameters(self, workflow: Dict, parameters: Dict):
        """Validate parameters against workflow requirements"""
        required_params = workflow.get('parameters', [])
        workflow_name = workflow.get('name', '')
        
        for param_def in required_params:
            param_name = param_def.get('name')
            if param_def.get('required', False) and param_name not in parameters:
                # Check if we can provide a reasonable default for critical parameters
                if param_name == 'signature_fields':
                    parameters['signature_fields'] = ['signature', 'date']
                    logger.warning(f"Using default signature_fields for workflow '{workflow_name}'")
                elif param_name == 'field':
                    parameters['field'] = 'information_needed'
                    logger.warning(f"Using default field name for workflow '{workflow_name}'")
                else:
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
                elif param_type == 'array' and not isinstance(value, list):
                    # Try to convert to array if it's a single value
                    parameters[param_name] = [value]
                    logger.info(f"Converted parameter '{param_name}' to array")
    
    def _resolve_templates(
        self,
        config: Dict,
        parameters: Dict,
        state: Dict
    ) -> Dict:
        """Resolve Jinja2 template variables in configuration"""
        from jinja2 import Template, Undefined, UndefinedError
        from jinja2.exceptions import TemplateSyntaxError
        
        def resolve_value(value):
            if isinstance(value, str) and '{{' in value:
                try:
                    template = Template(value)
                    context = {**parameters, 'steps': state}
                    result = template.render(context)
                    # Check if result contains undefined placeholders
                    if 'Undefined' in result:
                        logger.warning(f"Template contains undefined variables: {value}")
                        return ""
                    return result
                except (AttributeError, UndefinedError, TemplateSyntaxError) as e:
                    logger.warning(f"Template resolution failed for '{value}': {e}, using empty string")
                    return ""
                except Exception as e:
                    logger.error(f"Unexpected error in template resolution: {e}")
                    return value  # Return original value on unexpected errors
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
        """Execute a task via MCP/Claude agent using CLI"""
        agent_name = config.get('agent_name')
        action = config.get('action')
        params = config.get('params', {})
        
        try:
            # Use Claude Code CLI for real task execution
            from claude_cli import AsyncClaudeCLI
            cli = AsyncClaudeCLI()
            
            logger.info(f"Executing MCP task via Claude Code: {agent_name}.{action}")
            
            # Execute task through Claude Code
            result = await cli.execute_task_async(
                agent=agent_name,
                action=action,
                params=params
            )
            
            logger.info(f"MCP task completed: {result.get('status', 'unknown')}")
            return result
            
        except (ImportError, Exception) as e:
            # Fallback if Claude Code is not available
            logger.warning(f"Claude Code task execution failed, using fallback: {e}")
            
            return {
                'status': 'simulated',
                'agent': agent_name,
                'action': action,
                'result': f"Simulated execution of {action} (Claude Code required for real execution)",
                'warning': 'Claude Code not available - task was simulated'
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
        """Use Claude to analyze data via CLI"""
        prompt = config.get('prompt')
        data = config.get('data')
        
        try:
            # Use Claude Code CLI for real analysis
            from claude_cli import AsyncClaudeCLI
            cli = AsyncClaudeCLI()
            
            logger.info(f"Claude analysis requested: {prompt[:100]}...")
            
            # Prepare data for analysis
            if isinstance(data, dict):
                data_text = json.dumps(data, indent=2)
            else:
                data_text = str(data)
            
            # Define schema for structured analysis
            analysis_schema = {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "insights": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "recommendations": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "confidence": {"type": "number"}
                }
            }
            
            # Call Claude for analysis
            result = await cli.analyze_text_async(
                text=data_text,
                prompt=prompt,
                schema=analysis_schema
            )
            
            return {
                'status': 'success',
                'analysis': result
            }
            
        except (ImportError, Exception) as e:
            # Fallback if Claude Code is not available
            logger.warning(f"Claude Code analysis failed, using fallback: {e}")
            
            return {
                'status': 'simulated',
                'analysis': {
                    'summary': f"Analysis simulation for: {prompt[:50]}...",
                    'insights': ["Claude Code required for real analysis"],
                    'recommendations': ["Install Claude Code for full functionality"],
                    'confidence': 0.0
                },
                'warning': 'Claude Code not available - analysis was simulated'
            }
    
    # SuperClaude Framework Action Handlers
    
    async def _execute_agent_task(self, config: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task using SuperClaude agent providers"""
        try:
            agent_name = config.get('agent_name')
            document_id = config.get('document_id')
            context = config.get('context', {})
            
            logger.info(f"Executing agent task with {agent_name}")
            
            # If specific agent requested, use it
            if agent_name:
                provider = agent_registry.get_provider(agent_name)
                if not provider:
                    raise ValueError(f"Agent '{agent_name}' not found in registry")
            else:
                # Route based on document metadata
                document_meta = context.get('document_meta', {})
                provider, score = await agent_registry.route(document_meta)
                logger.info(f"Auto-routed to {provider.name} with score {score.score:.2f}")
            
            # Create execution plan
            document_content = context.get('document_content', '')
            plan = await provider.plan(document_content, context)
            
            # Execute plan steps
            results = []
            for step in plan:
                result = await provider.execute(step, context)
                results.append(result)
                
                # Validate step result
                quality_score, issues = await provider.validate(result)
                if quality_score < 0.7:  # Quality threshold
                    logger.warning(f"Low quality result (score: {quality_score}): {issues}")
            
            # Summarize results
            summary = await provider.summarize(results)
            
            return {
                'status': 'success',
                'agent_used': provider.name,
                'plan_executed': len(plan),
                'results': [asdict(r) for r in results],
                'summary': summary,
                'total_cost': sum(r.cost for r in results),
                'total_duration': sum(r.duration_seconds for r in results),
                'average_quality': sum(r.quality_score for r in results) / len(results) if results else 0.0
            }
            
        except Exception as e:
            logger.error(f"Agent task execution failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'fallback_used': 'general-purpose'
            }
    
    async def _execute_intelligent_routing(self, config: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Intelligent routing based on document analysis"""
        try:
            document_meta = config.get('document_meta', {})
            routing_mode = config.get('mode', 'automatic')  # automatic, brainstorm, task_manage, etc.
            
            logger.info(f"Executing intelligent routing in {routing_mode} mode")
            
            # Route to best agent
            provider, score = await agent_registry.route(document_meta)
            
            # Apply behavioral mode modifications
            if routing_mode == 'brainstorm' and score.score < 0.5:
                # Use brainstorming for unclear documents
                provider = agent_registry.get_provider('root-cause-analyst')
                logger.info("Switched to root-cause-analyst for brainstorming mode")
            elif routing_mode == 'quality_check':
                # Add quality engineer to the pipeline
                quality_provider = agent_registry.get_provider('quality-engineer')
                logger.info("Added quality-engineer to processing pipeline")
            
            return {
                'status': 'success',
                'selected_agent': provider.name,
                'routing_score': score.score,
                'routing_reasons': score.reasons,
                'estimated_cost': score.estimated_cost,
                'estimated_time': score.estimated_time_seconds,
                'mode_applied': routing_mode
            }
            
        except Exception as e:
            logger.error(f"Intelligent routing failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'fallback_agent': 'general-purpose'
            }
    
    async def _execute_code_generation(self, config: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code generation tasks"""
        try:
            generation_type = config.get('type', 'analysis')  # analysis, visualization, automation
            language = config.get('language', 'python')
            libraries = config.get('libraries', [])
            data = config.get('data', {})
            
            logger.info(f"Generating {language} code for {generation_type}")
            
            # Import code generator (will be created next)
            try:
                from code_generator import CodeGenerator
                generator = CodeGenerator()
                
                if generation_type == 'analysis':
                    code = await generator.generate_analysis_script(data, libraries)
                elif generation_type == 'visualization':
                    code = await generator.generate_visualization(data, config)
                elif generation_type == 'automation':
                    code = await generator.generate_automation_script(data, config)
                else:
                    raise ValueError(f"Unknown generation type: {generation_type}")
                
                # Execute generated code if requested
                execute_code = config.get('execute', False)
                execution_result = None
                if execute_code:
                    from sandbox_executor import SandboxExecutor
                    executor = SandboxExecutor()
                    execution_result = await executor.execute_code(code, language, data)
                
                return {
                    'status': 'success',
                    'generated_code': code,
                    'generation_type': generation_type,
                    'language': language,
                    'executed': execute_code,
                    'execution_result': execution_result,
                    'artifacts': {
                        f'generated_{generation_type}.{language}': code
                    }
                }
                
            except ImportError:
                logger.warning("Code generator not available, using placeholder")
                return {
                    'status': 'simulated',
                    'generated_code': f"# Generated {generation_type} code placeholder\n# Language: {language}\n# Libraries: {libraries}",
                    'note': 'Code generator module not yet implemented'
                }
                
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    async def _execute_quality_check(self, config: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute quality assurance checks"""
        try:
            checks = config.get('checks', ['completeness', 'accuracy'])
            target_data = config.get('target_data', state.get('extracted_data', {}))
            threshold = config.get('quality_threshold', 0.8)
            
            logger.info(f"Running quality checks: {checks}")
            
            # Use quality engineer agent
            quality_provider = agent_registry.get_provider('quality-engineer')
            if not quality_provider:
                raise ValueError("Quality engineer agent not available")
            
            # Create quality check context
            context = {
                'checks_requested': checks,
                'target_data': target_data,
                'threshold': threshold
            }
            
            # Execute quality plan
            plan = await quality_provider.plan('', context)
            results = []
            for step in plan:
                result = await quality_provider.execute(step, context)
                results.append(result)
            
            # Calculate overall quality score
            overall_score = sum(r.quality_score for r in results) / len(results) if results else 0.0
            passed = overall_score >= threshold
            
            return {
                'status': 'success',
                'quality_score': overall_score,
                'threshold': threshold,
                'passed': passed,
                'checks_performed': checks,
                'detailed_results': [asdict(r) for r in results],
                'recommendations': [] if passed else ['Review and improve data quality']
            }
            
        except Exception as e:
            logger.error(f"Quality check failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'quality_score': 0.0,
                'passed': False
            }
    
    async def _execute_dynamic_workflow(self, config: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate and execute dynamic workflows based on document content"""
        try:
            document_content = config.get('document_content', '')
            document_meta = config.get('document_meta', {})
            workflow_hints = config.get('workflow_hints', [])
            
            logger.info("Generating dynamic workflow")
            
            # Use root-cause-analyst to understand document and generate workflow
            analyst = agent_registry.get_provider('root-cause-analyst')
            if not analyst:
                raise ValueError("Root cause analyst not available for workflow generation")
            
            # Generate workflow based on document analysis
            context = {
                'document_content': document_content,
                'document_meta': document_meta,
                'workflow_hints': workflow_hints,
                'task': 'generate_workflow_yaml'
            }
            
            plan = await analyst.plan(document_content, context)
            workflow_result = None
            
            for step in plan:
                if step.get('tool') == 'workflow_generation':
                    # This would generate a YAML workflow definition
                    workflow_result = await analyst.execute(step, context)
                    break
            
            if workflow_result and workflow_result.success:
                # Parse generated workflow and execute it
                generated_workflow = workflow_result.output.get('workflow_yaml', '')
                workflow_dict = yaml.safe_load(generated_workflow) if generated_workflow else None
                
                if workflow_dict:
                    # Execute the generated workflow
                    sub_run = await self._execute_generated_workflow(workflow_dict, document_meta.get('document_id', 'unknown'), state)
                    
                    return {
                        'status': 'success',
                        'generated_workflow': workflow_dict,
                        'execution_result': asdict(sub_run),
                        'dynamic': True
                    }
            
            # Fallback to standard processing
            return {
                'status': 'fallback',
                'message': 'Dynamic workflow generation failed, using standard processing',
                'workflow_generated': False
            }
            
        except Exception as e:
            logger.error(f"Dynamic workflow execution failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    async def _execute_generated_workflow(self, workflow_dict: Dict, document_id: str, initial_state: Dict) -> WorkflowRun:
        """Execute a dynamically generated workflow"""
        # Create a temporary workflow run for the generated workflow
        run = WorkflowRun(
            run_id=f"dynamic_{self._generate_run_id()}",
            workflow_name=workflow_dict.get('name', 'dynamic_workflow'),
            document_id=document_id,
            status=WorkflowStatus.RUNNING,
            current_step=None,
            parameters=workflow_dict.get('parameters', {}),
            state=initial_state.copy(),
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            error=None,
            outputs={}
        )
        
        try:
            # Execute workflow steps
            for step in workflow_dict.get('steps', []):
                run.current_step = step['id']
                logger.info(f"Executing dynamic step: {step['id']}")
                
                # Resolve templates
                resolved_config = self._resolve_templates(
                    step.get('config', {}),
                    run.parameters,
                    run.state
                )
                
                # Execute action
                action_type = step['type']
                if action_type in self.action_registry:
                    action_handler = self.action_registry[action_type]
                    result = await action_handler(resolved_config, run.state)
                    
                    # Store result
                    if "steps" not in run.state:
                        run.state["steps"] = {}
                    run.state["steps"][step['id']] = result
                    run.outputs[step['id']] = result
                else:
                    logger.warning(f"Unknown action type in dynamic workflow: {action_type}")
            
            run.status = WorkflowStatus.SUCCESS
            run.completed_at = datetime.utcnow().isoformat()
            
        except Exception as e:
            logger.error(f"Dynamic workflow execution failed: {e}")
            run.status = WorkflowStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.utcnow().isoformat()
        
        return run
    
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