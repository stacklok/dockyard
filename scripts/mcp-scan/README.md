# MCP Security Scanning Scripts

This directory contains scripts used for scanning MCP (Model Context Protocol) servers for security vulnerabilities using [Cisco AI Defense mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner).

## Scripts

### generate_mcp_config.py

Generates command/args configuration from our YAML server definitions for use with mcp-scanner's stdio mode.

**Usage:**
```bash
python3 generate_mcp_config.py <config_file> <protocol> <server_name>
```

**Example:**
```bash
python3 generate_mcp_config.py npx/context7/spec.yaml npx context7
```

**Output:**
Outputs a JSON configuration with command/args/mock_env for mcp-scanner:
```json
{
  "command": "npx",
  "args": "@upstash/context7-mcp@2.1.0",
  "server_name": "context7",
  "mock_env": []
}
```

For servers with `security.mock_env` defined in spec.yaml:
```json
{
  "command": "npx",
  "args": "mcp-searxng@0.8.0",
  "server_name": "mcp-searxng",
  "mock_env": [
    {"name": "SEARXNG_URL", "value": "https://mock-searxng.example.com", "description": "..."}
  ]
}
```

### run_scan.py

Wrapper script to run Cisco AI Defense mcp-scanner with proper configuration.

**Usage:**
```bash
# Recommended: config file mode (supports mock_env)
python3 run_scan.py --config <config.json>

# Legacy: positional arguments (no mock_env support)
python3 run_scan.py <command> <package_arg>
```

**Example:**
```bash
# Using config file (recommended)
python3 run_scan.py --config /tmp/scan-config.json

# Legacy mode
python3 run_scan.py npx "@upstash/context7-mcp@2.1.0"
```

**Config file format:**
```json
{
  "command": "npx",
  "args": "mcp-searxng@0.8.0",
  "mock_env": [
    {"name": "SEARXNG_URL", "value": "https://mock.example.com"}
  ]
}
```

When `mock_env` is provided, the script passes `--stdio-env KEY=VALUE` arguments to mcp-scanner for each entry, allowing servers that require environment variables to start and be scanned.

**Environment Variables:**
- `MCP_SCANNER_ENABLE_LLM`: Set to `true` to enable LLM analyzer (optional)
- `MCP_SCANNER_LLM_API_KEY`: API key for LLM provider (required if LLM enabled)
- `MCP_SCANNER_LLM_MODEL`: LLM model to use (see [LLM Providers](#llm-providers) below)

### process_scan_results.py

Processes the output from mcp-scanner and generates a structured summary.

**Usage:**
```bash
python3 process_scan_results.py <scan_output_file> <server_name> [config_file]
```

**Example:**
```bash
python3 process_scan_results.py /tmp/mcp-scan-output.json context7 npx/context7/spec.yaml
```

**Output:**
- Outputs a JSON summary to stdout
- Prints human-readable status messages to stderr
- Exit codes:
  - 0: No blocking vulnerabilities found
  - 1: Vulnerabilities detected or error occurred

**Summary Format:**
```json
{
  "server": "context7",
  "status": "passed|failed|warning|error",
  "tools_scanned": 5,
  "blocking_issues": [...],
  "allowed_issues": [...],
  "message": "..."
}
```

## Issue Codes (AITech Taxonomy)

The Cisco mcp-scanner uses the AITech taxonomy for categorizing security issues:

| Code | Category | Description |
|------|----------|-------------|
| **AITech-1.1** | Prompt Injection | Tool description may contain prompt injection patterns |
| **AITech-8.2** | Data Exfiltration | Data leak flow - private data access + untrusted content + public sink |
| **AITech-9.1** | System Manipulation | Destructive flow - destructive operations + untrusted content |
| **AITech-12.1** | Tool Exploitation | Tool poisoning or exploitation patterns |

### Prefix Matching

The allowlist supports prefix matching:
- `AITech-8.2.1` matches allowlist entry `"AITech-8.2.1"` (exact)
- `AITech-8.2.1` matches allowlist entry `"AITech-8.2"` (parent)
- `AITech-8.2.1` matches allowlist entry `"AITech-8"` (grandparent)

## CI Integration

These scripts are used in the GitHub Actions workflow (`.github/workflows/build-containers.yml`) to:

1. Generate command/args for each server defined in our YAML files
2. Run mcp-scanner on each configuration using stdio mode
3. Process the results and fail the build if blocking vulnerabilities are found
4. Generate reports for pull requests

## Requirements

- Python 3.11+
- PyYAML (`pip install pyyaml`)
- Cisco AI Defense mcp-scanner (`uv tool install cisco-ai-mcp-scanner`)
- jq (for parsing JSON in shell scripts)

## Testing Locally

To test the scanning process locally:

```bash
# Install dependencies
uv tool install cisco-ai-mcp-scanner
pip install pyyaml

# Generate config and save to file
python3 scripts/mcp-scan/generate_mcp_config.py npx/context7/spec.yaml npx context7 > /tmp/scan-config.json

# Run scan using config file
python3 scripts/mcp-scan/run_scan.py --config /tmp/scan-config.json > /tmp/scan-output.json

# Process results
python3 scripts/mcp-scan/process_scan_results.py /tmp/scan-output.json context7 npx/context7/spec.yaml
```

### Testing with Mock Environment Variables

For servers that require environment variables:

```bash
# Generate config (will include mock_env if defined in spec.yaml)
python3 scripts/mcp-scan/generate_mcp_config.py npx/mcp-searxng/spec.yaml npx mcp-searxng > /tmp/scan-config.json

# Verify mock_env is in the config
cat /tmp/scan-config.json | jq '.mock_env'

# Run scan - mock_env values will be passed to mcp-scanner via --stdio-env
python3 scripts/mcp-scan/run_scan.py --config /tmp/scan-config.json > /tmp/scan-output.json
```

## Analyzers

By default, only the YARA analyzer is used (free, offline). To enable additional analysis:

- **YARA Analyzer**: Pattern-based detection using YARA rules (always enabled)
- **LLM Analyzer**: AI-powered semantic analysis (optional, requires API key)

The LLM analyzer provides more nuanced analysis and can reduce false positives by understanding context.

## LLM Providers

The scanner supports 100+ LLM providers through [LiteLLM](https://docs.litellm.ai/docs/providers). Common configurations:

### OpenAI (default)

```bash
export MCP_SCANNER_ENABLE_LLM=true
export MCP_SCANNER_LLM_API_KEY=sk-...
export MCP_SCANNER_LLM_MODEL=gpt-4o  # default
```

### Anthropic Claude

```bash
export MCP_SCANNER_ENABLE_LLM=true
export MCP_SCANNER_LLM_API_KEY=sk-ant-...
export MCP_SCANNER_LLM_MODEL=claude-sonnet-4-20250514
# Other options: claude-opus-4-20250514, claude-3-5-sonnet-20241022
```

### AWS Bedrock Claude

```bash
export MCP_SCANNER_ENABLE_LLM=true
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
export MCP_SCANNER_LLM_MODEL=bedrock/anthropic.claude-sonnet-4-5-20250929-v2:0
```

### Local LLM (Ollama)

```bash
export MCP_SCANNER_ENABLE_LLM=true
export MCP_SCANNER_LLM_API_KEY=test  # any value for local
export MCP_SCANNER_LLM_BASE_URL=http://localhost:11434
export MCP_SCANNER_LLM_MODEL=ollama/llama2
```

### All LLM Environment Variables

| Variable | Description |
|----------|-------------|
| `MCP_SCANNER_ENABLE_LLM` | Set to `true` to enable LLM analyzer |
| `MCP_SCANNER_LLM_API_KEY` | API key for the LLM provider |
| `MCP_SCANNER_LLM_MODEL` | Model identifier (provider-specific) |
| `MCP_SCANNER_LLM_BASE_URL` | Custom API endpoint (optional) |
| `MCP_SCANNER_LLM_TEMPERATURE` | Response randomness 0.0-1.0 (optional) |
| `MCP_SCANNER_LLM_MAX_TOKENS` | Maximum response tokens (optional) |
| `MCP_SCANNER_LLM_TIMEOUT` | Request timeout in seconds (optional) |

## CI Configuration

To enable LLM analysis in CI, configure these GitHub repository settings:

**Secrets:**
- `MCP_SCANNER_LLM_API_KEY`: Your LLM provider API key

**Variables:**
- `MCP_SCANNER_ENABLE_LLM`: Set to `true` to enable
- `MCP_SCANNER_LLM_MODEL`: Model to use (e.g., `claude-sonnet-4-20250514`)

## See Also

- [Cisco AI Defense mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner)
- [AITech Taxonomy](https://github.com/cisco-ai-defense/mcp-scanner#aitech-taxonomy)
