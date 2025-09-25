# Document Issue Detection Workflow

## Overview
Multi-agent analysis workflow for comprehensive document issue detection using SuperClaude delegation framework.

## Workflow Stages

### Stage 1: Initial Analysis
**Agent**: `general-purpose`  
**Purpose**: Parse document structure and identify high-level issues

```bash
--delegate general-purpose "Analyze document structure and identify major sections in {doc_path}"
```

**Outputs**:
- Document structure map
- Section boundaries
- Initial quality assessment
- Format compliance check

### Stage 2: Parallel Specialized Analysis
**Agents**: Multiple specialists running concurrently  
**Purpose**: Deep domain-specific issue detection

```bash
--delegate --parallel \
  technical-writer:"Check documentation clarity and completeness" \
  requirements-analyst:"Validate requirements coverage and traceability" \
  security-engineer:"Identify security vulnerabilities and compliance gaps" \
  quality-engineer:"Assess testing coverage and quality metrics"
```

#### Technical Writer Analysis
**Focus Areas**:
- Terminology consistency
- Explanation clarity  
- Example quality
- Readability scores
- Grammar and style

**Issue Types Detected**:
- `clarity`: Ambiguous or unclear explanations
- `consistency`: Inconsistent terminology usage
- `completeness`: Missing examples or explanations

#### Requirements Analyst Analysis  
**Focus Areas**:
- Requirement completeness
- Acceptance criteria presence
- Traceability matrix
- Dependency documentation

**Issue Types Detected**:
- `completeness`: Missing requirements or specifications
- `structure`: Poor requirement organization
- `compliance`: Regulatory requirement gaps

#### Security Engineer Analysis
**Focus Areas**:
- Authentication documentation
- Authorization patterns
- Data protection measures
- Vulnerability disclosures
- Compliance requirements

**Issue Types Detected**:
- `security`: Security vulnerabilities or weak patterns
- `compliance`: Missing compliance documentation
- `completeness`: Undocumented security measures

#### Quality Engineer Analysis
**Focus Areas**:
- Test coverage documentation
- Error handling descriptions
- Performance considerations
- Monitoring requirements

**Issue Types Detected**:
- `completeness`: Missing test documentation
- `performance`: Undocumented performance impacts
- `structure`: Poor quality metric organization

### Stage 3: Issue Synthesis
**Agent**: `system-architect`  
**Purpose**: Consolidate and deduplicate findings

```bash
--delegate system-architect "Synthesize all findings and create consolidated issue report"
```

**Operations**:
1. **Deduplication**: Remove duplicate issues from different agents
2. **Correlation**: Link related issues across domains
3. **Priority Assignment**: Apply severity based on impact
4. **Dependency Analysis**: Identify blocking relationships

### Stage 4: Consensus Validation
**Tool**: `--zen consensus`  
**Purpose**: Multi-model agreement on critical issues

```bash
--zen consensus --model gpt-5 "Validate critical and high-severity issues for accuracy"
```

**Validation Criteria**:
- Issue severity accuracy
- Remediation feasibility
- Priority ordering correctness
- False positive elimination

## Issue Detection Patterns

### Pattern 1: Clarity Issues
```yaml
indicators:
  - Passive voice > 30%
  - Sentence length > 25 words average
  - Undefined technical terms
  - Missing context for acronyms

detection_rules:
  - name: undefined_terms
    pattern: Technical term used without prior definition
    severity: medium
  
  - name: complex_sentences
    pattern: Sentences exceeding complexity threshold
    severity: low
```

### Pattern 2: Completeness Issues
```yaml
indicators:
  - Missing required sections
  - Incomplete API documentation
  - Absent error handling docs
  - No examples for complex features

detection_rules:
  - name: missing_section
    pattern: Required section not found in document
    severity: high
    
  - name: incomplete_api
    pattern: API endpoint without full parameter documentation
    severity: medium
```

### Pattern 3: Security Issues
```yaml
indicators:
  - Hardcoded credentials in examples
  - Missing authentication documentation
  - Unencrypted data transmission examples
  - No security considerations section

detection_rules:
  - name: exposed_secrets
    pattern: Potential secrets or credentials in examples
    severity: critical
    
  - name: missing_auth
    pattern: No authentication flow documentation
    severity: high
```

### Pattern 4: Structure Issues
```yaml
indicators:
  - Inconsistent heading hierarchy
  - Orphaned sections
  - Circular references
  - Poor information architecture

detection_rules:
  - name: heading_skip
    pattern: Heading level skipped (H1 -> H3)
    severity: low
    
  - name: orphan_section
    pattern: Section not linked from TOC or parent
    severity: medium
```

## Issue Categorization Logic

### Severity Assignment
```python
def assign_severity(issue):
    if issue.type == 'security' and issue.subtype == 'exposed_secrets':
        return 'critical'
    elif issue.type == 'compliance':
        return 'high'
    elif issue.type == 'completeness' and issue.affects_core_functionality:
        return 'high'
    elif issue.type == 'clarity' and issue.affects_api_usage:
        return 'medium'
    elif issue.type == 'structure':
        return 'low' if issue.cosmetic else 'medium'
    else:
        return 'low'
```

### Priority Calculation
```python
def calculate_priority(issue):
    severity_weights = {
        'critical': 1000,
        'high': 100,
        'medium': 10,
        'low': 1
    }
    
    base_score = severity_weights[issue.severity]
    
    # Adjust for dependencies
    if issue.blocks_other_issues:
        base_score *= 1.5
    
    # Adjust for user impact
    if issue.affects_getting_started:
        base_score *= 2
    
    return base_score
```

## Deduplication Strategy

### Similarity Detection
Issues are considered duplicates if:
- Same issue type AND
- Location overlap > 80% AND  
- Description similarity > 0.85 (cosine similarity)

### Merge Rules
When duplicates found:
1. Keep issue with highest confidence score
2. Merge evidence from all duplicates
3. Union of all affected locations
4. Maximum severity across duplicates

## Output Format

### Issue Report Structure
```yaml
analysis_summary:
  total_issues: 47
  by_severity:
    critical: 2
    high: 8
    medium: 15
    low: 22
  by_type:
    clarity: 18
    completeness: 12
    security: 5
    structure: 8
    consistency: 4

issues:
  - id: "iss_7f3a4b2c"
    type: "clarity"
    severity: "medium"
    confidence: 0.85
    title: "Undefined term 'session token' in authentication section"
    
    location:
      file: "api-docs.md"
      section: "/authentication/oauth"
      lines: [145, 162]
    
    evidence:
      - "Line 145: 'The session token must be included...'"
      - "No prior definition of 'session token' found"
    
    detected_by: ["technical-writer", "requirements-analyst"]
    
    suggested_remediation:
      type: "addition"
      template: "define-term"
      parameters:
        term: "session token"
        definition: "A temporary credential issued after successful authentication"
    
    impact:
      users_affected: "all API users"
      functionality: "authentication flow understanding"
      
    relationships:
      blocks: []
      blocked_by: []
      related: ["iss_8c2d5e1a"]
```

## Execution Commands

### Full Workflow
```bash
# 1. Ingest document
python scripts/document-ingestion.py input-doc.pdf

# 2. Run initial analysis
--delegate general-purpose "Parse and analyze docs/source/{doc_id}/content.txt"

# 3. Parallel specialist analysis
--task-manage --parallel \
  "Technical clarity review by technical-writer" \
  "Requirements validation by requirements-analyst" \
  "Security assessment by security-engineer" \
  "Quality metrics by quality-engineer"

# 4. Synthesize findings
--delegate system-architect "Consolidate all analysis results"

# 5. Validate critical issues
--zen consensus "Validate high-severity findings"

# 6. Generate issue report
--delegate technical-writer "Create comprehensive issue report"
```

### Quick Analysis Mode
```bash
# For rapid assessment
--delegate general-purpose "Quick scan for critical issues only"
--think 2 "Prioritize top 5 issues for immediate attention"
```

## Integration Points

### With Generation Pipeline
Issues feed directly into:
- Template selection
- Parameter extraction  
- Validation criteria

### With Version Control
Each analysis run:
- Creates branch: `analysis/{doc_id}/{timestamp}`
- Saves issue report as YAML
- Tracks issue resolution status

### With Validation Gates
Issues determine:
- Which gates to apply
- Acceptance thresholds
- Iteration requirements