#!/usr/bin/env python3
"""
Document Remediation Generation Pipeline
Generates new documents that address identified issues using templates
"""

import json
import yaml
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib
import re
from jinja2 import Template, Environment, FileSystemLoader


class RemediationGenerator:
    """Generate remediated documents from issues and templates"""
    
    def __init__(self, templates_dir: str = "templates/remediation",
                 output_dir: str = "docs/generated"):
        self.templates_dir = Path(templates_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Load templates
        self.templates = self._load_templates()
    
    def generate_remediation(self, doc_id: str, issues_file: str,
                           original_content_file: str) -> Dict[str, Any]:
        """
        Generate remediated document from issues
        
        Args:
            doc_id: Document identifier
            issues_file: Path to issues YAML/JSON file
            original_content_file: Path to original document content
            
        Returns:
            Generation result with paths and statistics
        """
        # Load issues
        issues = self._load_issues(issues_file)
        
        # Load original content
        original_content = self._load_original_content(original_content_file)
        
        # Create run ID
        run_id = self._create_run_id()
        
        # Process issues through pipeline
        pipeline_result = self._run_pipeline(issues, original_content)
        
        # Generate remediated document
        remediated_doc = self._generate_document(
            original_content,
            pipeline_result['remediations']
        )
        
        # Validate generated document
        validation_report = self._validate_document(remediated_doc, issues)
        
        # Save outputs
        output_paths = self._save_outputs(
            doc_id, run_id, remediated_doc, 
            pipeline_result, validation_report
        )
        
        return {
            "doc_id": doc_id,
            "run_id": run_id,
            "status": "success" if validation_report['passed'] else "partial",
            "issues_processed": len(issues),
            "issues_resolved": pipeline_result['resolved_count'],
            "validation_score": validation_report['score'],
            "output_paths": output_paths,
            "statistics": pipeline_result['statistics']
        }
    
    def _load_templates(self) -> Dict[str, Dict]:
        """Load all remediation templates"""
        templates = {}
        
        for template_file in self.templates_dir.glob("*.yaml"):
            with open(template_file) as f:
                template_data = yaml.safe_load(f)
                template_id = template_data['template']['id']
                templates[template_id] = template_data['template']
        
        return templates
    
    def _load_issues(self, issues_file: str) -> List[Dict]:
        """Load issues from file"""
        issues_path = Path(issues_file)
        
        if issues_path.suffix == '.yaml':
            with open(issues_path) as f:
                data = yaml.safe_load(f)
        else:
            with open(issues_path) as f:
                data = json.load(f)
        
        return data.get('issues', [])
    
    def _load_original_content(self, content_file: str) -> str:
        """Load original document content"""
        return Path(content_file).read_text(encoding='utf-8')
    
    def _create_run_id(self) -> str:
        """Create unique run ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_part = hashlib.sha256(timestamp.encode()).hexdigest()[:8]
        return f"{timestamp}_{hash_part}"
    
    def _run_pipeline(self, issues: List[Dict], 
                     original_content: str) -> Dict[str, Any]:
        """Run the remediation pipeline"""
        
        # Stage 1: Parse and normalize issues
        normalized_issues = self._normalize_issues(issues)
        
        # Stage 2: Categorize issues
        categorized = self._categorize_issues(normalized_issues)
        
        # Stage 3: Prioritize issues
        prioritized = self._prioritize_issues(categorized)
        
        # Stage 4: Select templates
        template_assignments = self._select_templates(prioritized)
        
        # Stage 5: Generate remediations
        remediations = self._generate_remediations(
            template_assignments,
            original_content
        )
        
        # Collect statistics
        statistics = {
            "total_issues": len(issues),
            "normalized": len(normalized_issues),
            "by_category": {k: len(v) for k, v in categorized.items()},
            "templates_used": len(set(t['template_id'] for t in template_assignments)),
            "remediations_generated": len(remediations)
        }
        
        return {
            "remediations": remediations,
            "resolved_count": len(remediations),
            "statistics": statistics
        }
    
    def _normalize_issues(self, issues: List[Dict]) -> List[Dict]:
        """Normalize and deduplicate issues"""
        normalized = []
        seen_hashes = set()
        
        for issue in issues:
            # Create hash for deduplication
            issue_hash = hashlib.sha256(
                f"{issue['type']}{issue.get('location', {}).get('ref', '')}"
                .encode()
            ).hexdigest()[:16]
            
            if issue_hash in seen_hashes:
                continue
            
            seen_hashes.add(issue_hash)
            
            # Normalize structure
            normalized_issue = {
                "id": issue.get('id', issue_hash),
                "type": issue['type'],
                "severity": issue.get('severity', 'medium'),
                "confidence": issue.get('confidence', 0.5),
                "location": issue.get('location', {}),
                "evidence": issue.get('evidence', {}),
                "remediation": issue.get('remediation', {})
            }
            
            normalized.append(normalized_issue)
        
        return normalized
    
    def _categorize_issues(self, issues: List[Dict]) -> Dict[str, List[Dict]]:
        """Group issues by type"""
        categorized = {}
        
        for issue in issues:
            issue_type = issue['type']
            if issue_type not in categorized:
                categorized[issue_type] = []
            categorized[issue_type].append(issue)
        
        return categorized
    
    def _prioritize_issues(self, categorized: Dict[str, List[Dict]]) -> List[Dict]:
        """Sort issues by priority"""
        severity_scores = {
            'critical': 1000,
            'high': 100,
            'medium': 10,
            'low': 1
        }
        
        all_issues = []
        for issues_list in categorized.values():
            all_issues.extend(issues_list)
        
        # Sort by severity and confidence
        all_issues.sort(
            key=lambda x: (
                severity_scores.get(x['severity'], 1) * x['confidence'],
                x['confidence']
            ),
            reverse=True
        )
        
        return all_issues
    
    def _select_templates(self, issues: List[Dict]) -> List[Dict]:
        """Match issues to templates"""
        assignments = []
        
        for issue in issues:
            # Get suggested template from issue
            suggested_template = issue.get('remediation', {}).get('template_id')
            
            # Find matching template
            template_id = suggested_template
            if not template_id:
                # Auto-select based on issue type
                template_id = self._auto_select_template(issue)
            
            if template_id and template_id in self.templates:
                assignments.append({
                    "issue": issue,
                    "template_id": template_id,
                    "template": self.templates[template_id],
                    "parameters": self._extract_parameters(issue, self.templates[template_id])
                })
        
        return assignments
    
    def _auto_select_template(self, issue: Dict) -> Optional[str]:
        """Automatically select template based on issue type"""
        type_to_template = {
            'clarity': 'define-term',
            'completeness': 'add-section',
            'structure': 'fix-structure',
            'security': 'add-section',  # Use add-section for security
            'consistency': 'define-term'
        }
        
        return type_to_template.get(issue['type'])
    
    def _extract_parameters(self, issue: Dict, template: Dict) -> Dict:
        """Extract parameters for template from issue"""
        params = {}
        
        # Get required inputs from template
        required_inputs = template.get('inputs', {}).get('required', {})
        
        # Extract from issue evidence and remediation
        evidence = issue.get('evidence', {})
        remediation = issue.get('remediation', {})
        
        # Map common parameters
        if 'term' in required_inputs:
            # Extract term from evidence
            snippets = evidence.get('snippets', [])
            if snippets:
                # Simple extraction - find quoted or capitalized terms
                term_match = re.search(r"['\"]([^'\"]+)['\"]", snippets[0])
                if term_match:
                    params['term'] = term_match.group(1)
        
        if 'definition' in required_inputs:
            params['definition'] = remediation.get('parameters', {}).get(
                'definition',
                'Definition to be provided'
            )
        
        if 'section_title' in required_inputs:
            params['section_title'] = remediation.get('parameters', {}).get(
                'section_title',
                f"New Section for {issue['type']}"
            )
        
        if 'context_section' in required_inputs:
            location = issue.get('location', {})
            params['context_section'] = location.get('ref', {}).get('path', '/')
        
        # Merge with provided parameters
        params.update(remediation.get('parameters', {}))
        
        return params
    
    def _generate_remediations(self, assignments: List[Dict],
                              original_content: str) -> List[Dict]:
        """Generate remediation content using templates"""
        remediations = []
        
        for assignment in assignments:
            template = assignment['template']
            params = assignment['parameters']
            issue = assignment['issue']
            
            # Select pattern based on logic
            pattern_name = self._select_pattern(template, issue)
            pattern = template['generation']['patterns'].get(
                pattern_name,
                list(template['generation']['patterns'].values())[0]
            )
            
            # Render template
            jinja_template = Template(pattern)
            rendered_content = jinja_template.render(**params)
            
            remediations.append({
                "issue_id": issue['id'],
                "template_id": assignment['template_id'],
                "method": template['generation']['method'],
                "content": rendered_content,
                "location": issue.get('location', {}),
                "validation_required": template.get('validators', [])
            })
        
        return remediations
    
    def _select_pattern(self, template: Dict, issue: Dict) -> str:
        """Select which pattern to use from template"""
        # Execute selection logic if provided
        selection_logic = template['generation'].get('selection_logic')
        
        if selection_logic:
            # Simple pattern matching for now
            if 'glossary' in str(issue.get('location', {})):
                return 'glossary_entry'
            elif issue['severity'] == 'low':
                return 'inline_definition'
            else:
                return 'detailed_definition'
        
        # Default to first pattern
        return list(template['generation']['patterns'].keys())[0]
    
    def _generate_document(self, original_content: str,
                         remediations: List[Dict]) -> str:
        """Apply remediations to generate new document"""
        lines = original_content.split('\n')
        
        # Group remediations by method
        inserts = []
        rewrites = []
        
        for remediation in remediations:
            if remediation['method'] == 'insert':
                inserts.append(remediation)
            elif remediation['method'] in ['rewrite', 'replace']:
                rewrites.append(remediation)
        
        # Apply inserts (in reverse order to preserve line numbers)
        for remediation in sorted(inserts, 
                                 key=lambda x: x.get('location', {})
                                 .get('ref', {}).get('line_range', [0])[0],
                                 reverse=True):
            location = remediation.get('location', {})
            line_range = location.get('ref', {}).get('line_range', [0, 0])
            
            if line_range[0] > 0:
                insert_point = min(line_range[0], len(lines))
                lines.insert(insert_point, remediation['content'])
        
        # Apply rewrites
        for remediation in rewrites:
            # Simple append for now - more sophisticated merging needed
            lines.append('\n' + remediation['content'])
        
        return '\n'.join(lines)
    
    def _validate_document(self, document: str, issues: List[Dict]) -> Dict:
        """Validate the generated document"""
        validation_results = []
        
        # Check if issues are addressed
        for issue in issues:
            addressed = self._check_issue_addressed(document, issue)
            validation_results.append({
                "issue_id": issue.get('id'),
                "addressed": addressed,
                "severity": issue.get('severity', 'medium')
            })
        
        # Calculate validation score
        severity_weights = {
            'critical': 10,
            'high': 5,
            'medium': 2,
            'low': 1
        }
        
        total_weight = sum(severity_weights.get(r['severity'], 1) 
                          for r in validation_results)
        addressed_weight = sum(severity_weights.get(r['severity'], 1)
                              for r in validation_results if r['addressed'])
        
        score = (addressed_weight / total_weight * 100) if total_weight > 0 else 0
        
        return {
            "passed": score >= 70,
            "score": score,
            "results": validation_results,
            "critical_unresolved": sum(1 for r in validation_results 
                                      if r['severity'] == 'critical' 
                                      and not r['addressed'])
        }
    
    def _check_issue_addressed(self, document: str, issue: Dict) -> bool:
        """Check if an issue has been addressed in the document"""
        # Simple checks - can be made more sophisticated
        
        if issue['type'] == 'clarity':
            # Check if term is now defined
            evidence = issue.get('evidence', {}).get('snippets', [])
            if evidence:
                term = re.search(r"['\"]([^'\"]+)['\"]", evidence[0])
                if term:
                    # Check if term has definition nearby
                    pattern = f"{term.group(1)}.*?\\(.*?\\)"
                    return bool(re.search(pattern, document, re.IGNORECASE))
        
        elif issue['type'] == 'completeness':
            # Check if section was added
            section_title = issue.get('remediation', {}).get('parameters', {})\
                                .get('section_title', '')
            if section_title:
                return section_title.lower() in document.lower()
        
        elif issue['type'] == 'structure':
            # Check if structure markers present
            return '## Table of Contents' in document or '### ' in document
        
        # Default: assume addressed if remediation was generated
        return True
    
    def _save_outputs(self, doc_id: str, run_id: str,
                     remediated_doc: str, pipeline_result: Dict,
                     validation_report: Dict) -> Dict[str, str]:
        """Save all outputs"""
        # Create output directory
        output_dir = self.output_dir / doc_id / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save remediated document
        doc_file = output_dir / "remediated_document.md"
        doc_file.write_text(remediated_doc, encoding='utf-8')
        
        # Save pipeline results
        pipeline_file = output_dir / "pipeline_results.json"
        with open(pipeline_file, 'w') as f:
            json.dump(pipeline_result, f, indent=2)
        
        # Save validation report
        validation_file = output_dir / "validation_report.json"
        with open(validation_file, 'w') as f:
            json.dump(validation_report, f, indent=2)
        
        # Create summary
        summary = {
            "doc_id": doc_id,
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "issues_processed": pipeline_result['statistics']['total_issues'],
            "issues_resolved": pipeline_result['resolved_count'],
            "validation_score": validation_report['score'],
            "validation_passed": validation_report['passed']
        }
        
        summary_file = output_dir / "summary.yaml"
        with open(summary_file, 'w') as f:
            yaml.dump(summary, f, default_flow_style=False)
        
        return {
            "document": str(doc_file),
            "pipeline_results": str(pipeline_file),
            "validation_report": str(validation_file),
            "summary": str(summary_file)
        }


def main():
    """CLI interface for remediation generation"""
    parser = argparse.ArgumentParser(
        description="Generate remediated document from issues"
    )
    parser.add_argument("doc_id", help="Document ID")
    parser.add_argument("issues_file", help="Path to issues file (YAML/JSON)")
    parser.add_argument("content_file", help="Path to original content")
    parser.add_argument("--templates-dir", default="templates/remediation",
                       help="Directory containing templates")
    parser.add_argument("--output-dir", default="docs/generated",
                       help="Output directory")
    parser.add_argument("--verbose", action="store_true",
                       help="Verbose output")
    
    args = parser.parse_args()
    
    # Run generation
    generator = RemediationGenerator(
        templates_dir=args.templates_dir,
        output_dir=args.output_dir
    )
    
    try:
        result = generator.generate_remediation(
            args.doc_id,
            args.issues_file,
            args.content_file
        )
        
        if args.verbose:
            print(f"Remediation generation complete!")
            print(f"Document ID: {result['doc_id']}")
            print(f"Run ID: {result['run_id']}")
            print(f"Issues processed: {result['issues_processed']}")
            print(f"Issues resolved: {result['issues_resolved']}")
            print(f"Validation score: {result['validation_score']:.1f}%")
            print(f"Output: {result['output_paths']['document']}")
        else:
            print(json.dumps(result, indent=2))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()