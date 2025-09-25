# Document Remediation Workflow System

## Overview

This document describes the complete document remediation workflow that has been implemented for DocAutomate. The system uses Claude Code with SuperClaude framework delegation to analyze documents, identify issues, and generate improved versions automatically.

## System Architecture

### Core Components

1. **Unified DSL Schema** (`claudedocs/dsl/document-remediation.yaml`)
   - Defines issue types, severity levels, and remediation patterns
   - Establishes provenance tracking and validation gates
   - Configures agent roles and responsibilities

2. **Document Ingestion Pipeline** (`scripts/document-ingestion.py`)
   - Supports PDF, DOCX, Markdown, HTML, Plain Text
   - Extracts content with fidelity scoring
   - Creates searchable section indexes
   - Generates content-addressed document IDs

3. **Issue Detection Workflow** (`claudedocs/workflows/issue-detection.md`)
   - Multi-agent parallel analysis
   - Specialized domain expertise per agent
   - Consensus validation for critical issues
   - Deduplication and prioritization logic

4. **Remediation Templates** (`templates/remediation/`)
   - `define-term.yaml`: Adds definitions for unclear terms
   - `add-section.yaml`: Inserts missing required sections
   - `fix-structure.yaml`: Reorganizes content for better flow

5. **Generation Pipeline** (`scripts/generate-remediation.py`)
   - Template-based remediation generation
   - Context-aware content injection
   - Progressive enhancement with validation
   - Quality scoring and reporting

6. **Workflow Orchestrator** (`scripts/orchestrate-workflow.sh`)
   - End-to-end workflow execution
   - Agent command generation
   - Progress tracking and reporting

## Workflow Execution

### Phase 1: Document Ingestion

```bash
python scripts/document-ingestion.py <input_document>
```

**Process**:
1. Detect document format
2. Extract content with appropriate parser
3. Generate document ID from content hash
4. Create section index for navigation
5. Save to `docs/source/{doc_id}/`

**Output**:
- `content.txt`: Plain text content
- `structure.json`: Document structure
- `metadata.yaml`: Ingestion metadata

### Phase 2: Multi-Agent Analysis

```bash
# Initial structure analysis
--delegate general-purpose "Analyze document structure"

# Parallel specialist analysis
--delegate --parallel \
  technical-writer:"Check clarity and completeness" \
  requirements-analyst:"Validate requirements" \
  security-engineer:"Assess security gaps" \
  quality-engineer:"Evaluate quality metrics"

# Synthesize findings
--delegate system-architect "Consolidate all findings"
```

**Agent Responsibilities**:

| Agent | Focus Areas | Issue Types |
|-------|------------|-------------|
| technical-writer | Clarity, readability, examples | clarity, consistency |
| requirements-analyst | Completeness, traceability | completeness, structure |
| security-engineer | Vulnerabilities, compliance | security, compliance |
| quality-engineer | Testing, metrics, performance | performance, completeness |
| system-architect | Synthesis, prioritization | All types |

### Phase 3: Issue Synthesis & Consensus

```bash
# Multi-model consensus for critical issues
--zen consensus --model gpt-5 "Validate critical findings"

# Deep analysis for complex issues
--thinkdeep "Analyze root causes and remediation strategies"
```

**Synthesis Operations**:
1. Deduplication by location and content similarity
2. Priority calculation based on severity and dependencies
3. Consensus validation for high-severity issues
4. Remediation strategy selection

### Phase 4: Document Generation

```bash
python scripts/generate-remediation.py \
  <doc_id> \
  <issues_file> \
  <content_file>
```

**Generation Pipeline**:
1. **Parse Issues**: Normalize and validate issue format
2. **Categorize**: Group by type and severity
3. **Prioritize**: Order by impact and dependencies
4. **Select Templates**: Match issues to remediation templates
5. **Generate Content**: Apply templates with context injection
6. **Integrate**: Merge remediations into original document
7. **Validate**: Check quality gates and completeness

### Phase 5: Quality Validation

```bash
# Deep quality review
--zen-review --thinkdeep "Validate remediated document"

# Structural validation
--delegate quality-engineer "Verify document structure"

# Final consensus
--zen consensus "Approve remediated document"
```

**Validation Gates**:
- **Structural**: TOC completeness, heading hierarchy
- **Content**: Term definitions, example quality
- **Security**: Authentication docs, vulnerability disclosure
- **Completeness**: Required sections, API coverage

## Integration with SuperClaude

### Behavioral Modes

- **Brainstorming Mode**: Requirements discovery for document improvements
- **Task Management Mode**: Orchestrating multi-step remediation
- **Introspection Mode**: Analyzing remediation effectiveness
- **Token Efficiency Mode**: Compressed reporting for large documents

### MCP Server Usage

- **Sequential MCP**: Complex issue analysis and root cause identification
- **Zen MCP**: Multi-model consensus and validation
- **Magic MCP**: UI component documentation generation
- **Playwright MCP**: Interactive documentation testing

### Agent Delegation Patterns

```bash
# Automatic routing based on issue type
--delegate "Fix documentation issues in {doc_id}"

# Parallel execution for efficiency
--task-manage --parallel

# Quality iteration loops
--loop --validate "Improve until quality score >90%"
```

## DSL Structure

### Issue Definition
```yaml
issues:
  - id: unique_identifier
    type: [clarity|completeness|security|structure|consistency]
    severity: [critical|high|medium|low]
    confidence: 0.0-1.0
    location:
      type: [section|line|component]
      ref:
        path: "/section/path"
        line_range: [start, end]
    evidence:
      snippets: ["relevant text"]
    remediation:
      template_id: "template_name"
      parameters: {}
```

### Template Structure
```yaml
template:
  id: template_identifier
  applicable_to:
    issue_types: []
    severity_range: [min, max]
  generation:
    method: [insert|replace|rewrite]
    patterns:
      pattern_name: "template content"
  validators:
    - type: [structural|content|style]
      rules: []
```

## Usage Examples

### Example 1: Complete Workflow
```bash
# Run orchestrator
./scripts/orchestrate-workflow.sh api-docs.pdf

# Or step-by-step:
python scripts/document-ingestion.py api-docs.pdf
--delegate --parallel [agents]
python scripts/generate-remediation.py api_docs issues.yaml content.txt
--zen-review "Validate improvements"
```

### Example 2: Focused Security Audit
```bash
# Security-focused analysis
--delegate security-engineer "Comprehensive security audit"
--zen consensus "Validate security findings"
--delegate technical-writer "Add security documentation"
```

### Example 3: Structure Improvement
```bash
# Structure reorganization
--delegate requirements-analyst "Analyze document structure"
--think 2 "Propose optimal organization"
--delegate technical-writer "Reorganize content"
```

## Output Structure

```
docs/
├── source/{doc_id}/          # Ingested documents
│   ├── content.txt
│   ├── structure.json
│   └── metadata.yaml
├── analysis/{doc_id}/        # Analysis results
│   ├── issues.yaml
│   └── {run_id}/
├── generated/{doc_id}/       # Remediated documents
│   └── {run_id}/
│       ├── remediated_document.md
│       ├── validation_report.json
│       └── summary.yaml
└── validation/{doc_id}/      # Validation reports
```

## Quality Metrics

### Validation Scoring
- **Critical Issues**: Weight 10
- **High Issues**: Weight 5  
- **Medium Issues**: Weight 2
- **Low Issues**: Weight 1

**Pass Threshold**: 70% weighted resolution

### Fidelity Scores
- **Markdown**: 1.0 (perfect preservation)
- **DOCX**: 0.9 (excellent structure)
- **HTML**: 0.85 (good extraction)
- **PDF**: 0.8 (good text, structure varies)
- **Plain Text**: 0.5 (structure lost)

## Best Practices

1. **Start with High-Fidelity Formats**: Use Markdown or DOCX when possible
2. **Leverage Parallel Analysis**: Use `--parallel` for multi-agent efficiency
3. **Validate Critical Changes**: Use `--zen consensus` for important decisions
4. **Iterate on Quality**: Re-run if validation score <70%
5. **Use Appropriate Agents**: Match agent expertise to issue types
6. **Enable Deep Analysis**: Use `--thinkdeep` for complex problems
7. **Track Progress**: Use `--task-manage` for multi-step operations

## Troubleshooting

### Common Issues

**Low Validation Score**:
- Review issue detection accuracy
- Adjust template parameters
- Add more specific remediation templates

**Template Not Matching**:
- Check issue type mapping
- Verify template applicability rules
- Add fallback templates

**Performance Issues**:
- Use `--uc` mode for large documents
- Enable chunking for >1000 line documents
- Parallelize agent analysis

## Extension Points

### Adding Custom Templates
1. Create YAML in `templates/remediation/`
2. Define patterns and validators
3. Map to issue types in DSL

### Custom Issue Types
1. Extend DSL schema
2. Add detection patterns
3. Create matching templates

### New Agents
1. Define in DSL agent_roles
2. Specify focus areas
3. Map to issue types

## Conclusion

This document remediation workflow provides a comprehensive, automated solution for improving document quality through multi-agent analysis and template-based generation. By leveraging Claude Code with SuperClaude framework, it ensures consistent, high-quality documentation improvements with full traceability and validation.