#!/bin/bash

# Simplified Document Orchestration Script
# Uses API endpoints instead of complex logic

set -e  # Exit on error

# Configuration
API_URL="${API_URL:-http://localhost:8001}"
VERBOSE="${VERBOSE:-0}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Print functions
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[ℹ]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] <document_file>

Orchestrate document processing through API

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -t, --type TYPE     Workflow type (full, analysis_only, remediation_only)
    -a, --api URL       API URL (default: http://localhost:8001)

EXAMPLE:
    $0 document.pdf
    $0 --type analysis_only --verbose report.docx

EOF
    exit 0
}

# Parse arguments
WORKFLOW_TYPE="full"
DOCUMENT_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -t|--type)
            WORKFLOW_TYPE="$2"
            shift 2
            ;;
        -a|--api)
            API_URL="$2"
            shift 2
            ;;
        *)
            DOCUMENT_FILE="$1"
            shift
            ;;
    esac
done

if [ -z "$DOCUMENT_FILE" ]; then
    print_error "No document file specified"
    usage
fi

if [ ! -f "$DOCUMENT_FILE" ]; then
    print_error "Document file not found: $DOCUMENT_FILE"
    exit 1
fi

print_info "Starting Document Orchestration via API"
print_info "API URL: $API_URL"
print_info "Document: $DOCUMENT_FILE"
print_info "Workflow Type: $WORKFLOW_TYPE"

# Step 1: Upload document
print_status "Uploading document to API..."

UPLOAD_RESPONSE=$(curl -s -X POST \
    -F "file=@$DOCUMENT_FILE" \
    -F "auto_process=true" \
    "$API_URL/documents/upload")

if [ $VERBOSE -eq 1 ]; then
    echo "Upload response: $UPLOAD_RESPONSE"
fi

DOCUMENT_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '"document_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$DOCUMENT_ID" ]; then
    print_error "Failed to extract document ID from upload response"
    exit 1
fi

print_info "Document ID: $DOCUMENT_ID"

# Step 2: Start orchestration
print_status "Starting orchestration workflow..."

ORCHESTRATION_REQUEST='{
    "document_id": "'$DOCUMENT_ID'",
    "workflow_type": "'$WORKFLOW_TYPE'",
    "agents": ["general-purpose", "technical-writer", "security-engineer", "quality-engineer", "requirements-analyst"],
    "models": ["gpt-5", "claude-opus-4.1", "gpt-4.1"]
}'

ORCHESTRATION_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "$ORCHESTRATION_REQUEST" \
    "$API_URL/orchestrate/workflow")

if [ $VERBOSE -eq 1 ]; then
    echo "Orchestration response: $ORCHESTRATION_RESPONSE"
fi

ORCHESTRATION_ID=$(echo "$ORCHESTRATION_RESPONSE" | grep -o '"orchestration_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ORCHESTRATION_ID" ]; then
    print_error "Failed to start orchestration"
    exit 1
fi

print_info "Orchestration ID: $ORCHESTRATION_ID"

# Step 3: Poll for completion
print_status "Waiting for orchestration to complete..."

MAX_WAIT=300  # 5 minutes
POLL_INTERVAL=5
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
    
    STATUS_RESPONSE=$(curl -s "$API_URL/orchestrate/runs/$ORCHESTRATION_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    
    if [ "$STATUS" == "completed" ]; then
        print_status "Orchestration completed!"
        break
    elif [ "$STATUS" == "failed" ]; then
        print_error "Orchestration failed"
        echo "$STATUS_RESPONSE"
        exit 1
    else
        echo -ne "\rStatus: $STATUS (${ELAPSED}s elapsed)..."
    fi
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    print_error "Orchestration timed out after ${MAX_WAIT} seconds"
    exit 1
fi

# Step 4: Get results
print_status "Retrieving orchestration results..."

# Get document status with orchestration results
DOCUMENT_STATUS=$(curl -s "$API_URL/documents/$DOCUMENT_ID")

if [ $VERBOSE -eq 1 ]; then
    echo "Document status: $DOCUMENT_STATUS"
fi

# Extract key metrics
QUALITY_SCORE=$(echo "$DOCUMENT_STATUS" | grep -o '"quality_score":[0-9.]*' | cut -d: -f2)
ISSUES_FOUND=$(echo "$DOCUMENT_STATUS" | grep -o '"issues_found":[0-9]*' | cut -d: -f2)
ISSUES_RESOLVED=$(echo "$DOCUMENT_STATUS" | grep -o '"issues_resolved":[0-9]*' | cut -d: -f2)

# Step 5: Display summary
echo ""
print_status "=== ORCHESTRATION SUMMARY ==="
echo "Document ID: $DOCUMENT_ID"
echo "Orchestration ID: $ORCHESTRATION_ID"
echo "Workflow Type: $WORKFLOW_TYPE"
echo ""
echo "Results:"
echo "  Quality Score: ${QUALITY_SCORE:-N/A}%"
echo "  Issues Found: ${ISSUES_FOUND:-0}"
echo "  Issues Resolved: ${ISSUES_RESOLVED:-0}"
echo ""

# Check for remediated document
REMEDIATED_PATH="docs/generated/${DOCUMENT_ID}/remediated_document.md"
if [ -f "$REMEDIATED_PATH" ]; then
    print_info "Remediated document available: $REMEDIATED_PATH"
fi

print_info "View full details at: $API_URL/orchestrate/runs/$ORCHESTRATION_ID"

# Optional: Execute specific workflows
if [ "$WORKFLOW_TYPE" == "analysis_only" ]; then
    print_info "Analysis complete. To remediate, run:"
    echo "  curl -X POST $API_URL/documents/$DOCUMENT_ID/remediate"
fi

exit 0