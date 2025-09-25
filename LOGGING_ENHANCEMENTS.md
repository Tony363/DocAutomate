# Logging and Timeout Enhancements for DocAutomate

## Overview
This document describes the extensive logging and timeout improvements made to the DocAutomate framework to address subprocess timeout issues and improve debugging capabilities.

## Problem Addressed
- **Original Issue**: "ERROR:__main__:Failed to upload document: Failed to read document: Command timed out after 30 seconds"
- **Root Cause**: Default 30-second timeout was insufficient for processing complex documents via Claude Code subprocess

## Implemented Solutions

### 1. Timeout Configuration Enhancement (`claude_cli.py`)
- **Increased default timeout**: 30 seconds → 120 seconds
- **Environment variable support**: `CLAUDE_TIMEOUT` for configurable timeout
- **Dynamic timeout adjustment**: Automatically increases timeout for large files
- **Retry logic**: 2 retry attempts with exponential backoff for timeout errors

### 2. Extensive Logging Implementation

#### A. Enhanced Logging Format
```python
format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
```
- Timestamp for all log entries
- Module name identification
- Log level (DEBUG, INFO, WARNING, ERROR)
- File name and line number for traceability

#### B. Debug Mode Support
- Environment variable `DEBUG=1` enables detailed logging
- DEBUG level shows:
  - Full command execution details
  - Input/output previews
  - Timing metrics
  - Stack traces for errors

### 3. Module-Specific Enhancements

#### `claude_cli.py`
- **Command execution logging**: Logs each subprocess call with timing
- **Retry attempt tracking**: Shows retry count and delay
- **File size-based timeout adjustment**: Increases timeout for large files
- **Partial output capture**: Logs partial stdout/stderr on timeout
- **Performance metrics**: Execution time for each operation

#### `api.py`
- **Request ID generation**: Unique 8-character ID for request tracking
- **Operation timing**: Start/end times for all operations
- **Background task tracking**: Separate IDs for background operations
- **File upload metrics**: Size, type, and processing time
- **Workflow execution logging**: Detailed workflow status updates

#### `extractor.py`
- **Extraction flow logging**: Step-by-step extraction process
- **Claude API call timing**: Measures API response times
- **Action detail logging**: Logs each extracted action with confidence scores
- **Fallback logging**: Tracks when fallback responses are used
- **Document type detection**: Logs auto-detected document types

### 4. Performance Monitoring

#### Key Metrics Tracked
- Document ingestion time
- Claude API response time
- Action extraction duration
- Workflow execution time
- File upload and processing time

#### Example Log Output
```
[12a3b4c5] Document upload started: filename=invoice.pdf, content_type=application/pdf
[12a3b4c5] File size: 245760 bytes (240.00 KB)
[12a3b4c5] Document ingested in 2.34s: id=doc_789xyz, status=ingested
[12a3b4c5] Calling Claude Code for action extraction
[12a3b4c5] Claude API responded in 8.45s, response_size=1523 chars
[12a3b4c5] Extracted 3 actions from document doc_789xyz
[12a3b4c5] Document upload completed in 11.23s: invoice.pdf -> doc_789xyz
```

### 5. Error Handling Improvements

#### Retry Mechanism
```python
retries: int = 2
retry_delay: int = 5  # seconds
# Exponential backoff: 5s, 10s, 20s...
```

#### Enhanced Error Context
- Stack traces in DEBUG mode (`exc_info=True`)
- Partial output on timeout failures
- Cleanup of temporary files on error
- Detailed error messages with context

### 6. Configuration Options

#### Environment Variables
- `CLAUDE_TIMEOUT`: Set Claude subprocess timeout (default: 120)
- `DEBUG`: Enable debug logging (set to "1")
- `CLAUDE_CLI_PATH`: Path to Claude executable (default: "claude")

#### Usage Examples
```bash
# Enable debug logging with custom timeout
export DEBUG=1
export CLAUDE_TIMEOUT=180
python api.py

# Run with default settings
python api.py

# Test the improvements
python test_timeout_fix.py
```

## Testing

### Test Script: `test_timeout_fix.py`
- Verifies timeout configuration
- Tests Claude CLI with logging
- Validates async operations
- Confirms extraction with detailed logging

### Test Results
```
✓ Timeout increased from 30s to 120s
✓ Extensive logging added to all modules
✓ Retry logic implemented with exponential backoff
✓ Request ID tracking for API calls
✓ Performance metrics logging
```

## Benefits

1. **Improved Reliability**: Longer timeouts prevent premature failures
2. **Better Debugging**: Detailed logs help identify issues quickly
3. **Performance Visibility**: Timing metrics identify bottlenecks
4. **Request Tracking**: Unique IDs enable end-to-end request tracing
5. **Graceful Degradation**: Retry logic handles transient failures
6. **Configurable Behavior**: Environment variables allow customization

## Monitoring Recommendations

1. **Log Aggregation**: Consider using tools like ELK stack for production
2. **Alert Thresholds**: Set alerts for operations exceeding expected durations
3. **Performance Baselines**: Track average processing times for different document types
4. **Error Rate Monitoring**: Track retry attempts and failure rates

## Future Enhancements

1. **Structured Logging**: Consider JSON format for machine parsing
2. **Log Rotation**: Implement log file rotation for long-running services
3. **Metrics Export**: Add Prometheus metrics for monitoring
4. **Distributed Tracing**: Consider OpenTelemetry for microservices
5. **Async Timeout Handling**: Implement circuit breakers for repeated failures