# MCP Security Scanning Scripts

This directory contains scripts used for scanning MCP (Model Context Protocol) servers for security vulnerabilities using [mcp-scan](https://github.com/invariantlabs-ai/mcp-scan).

## Scripts

### generate_mcp_config.py

Generates an MCP configuration file from our YAML server definitions that can be used by mcp-scan.

**Usage:**
```bash
python3 generate_mcp_config.py <config_file> <protocol> <server_name>
```

**Example:**
```bash
python3 generate_mcp_config.py npx/context7.yaml npx context7
```

**Output:**
Outputs a JSON configuration to stdout that can be used with mcp-scan:
```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["@upstash/context7-mcp@1.0.14"],
      "env": {}
    }
  }
}
```

### process_scan_results.py

Processes the output from mcp-scan and generates a structured summary.

**Usage:**
```bash
python3 process_scan_results.py <scan_output_file> <server_name>
```

**Example:**
```bash
python3 process_scan_results.py /tmp/mcp-scan-output.json context7
```

**Output:**
- Outputs a JSON summary to stdout
- Prints human-readable status messages to stderr
- Exit codes:
  - 0: No vulnerabilities found
  - 1: Vulnerabilities detected or error occurred

**Summary Format:**
```json
{
  "server": "context7",
  "status": "passed|failed|warning|error",
  "tools_scanned": 5,
  "vulnerabilities": [...],
  "message": "..."
}
```

## CI Integration

These scripts are used in the GitHub Actions workflow (`.github/workflows/build-containers.yml`) to:

1. Generate MCP configurations for each server defined in our YAML files
2. Run mcp-scan on each configuration
3. Process the results and fail the build if vulnerabilities are found
4. Generate reports for pull requests

## Security Considerations

- **Data Sharing**: mcp-scan sends tool names and descriptions to invariantlabs.ai for analysis
- **Privacy**: No actual usage data or tool call contents are shared
- **Opt-out**: The CI can use `--opt-out` flag to disable anonymous analytics

## Requirements

- Python 3.11+
- PyYAML (`pip install pyyaml`)
- mcp-scan (`uv tool install mcp-scan`)

## Testing Locally

To test the scanning process locally:

```bash
# Install dependencies
uv tool install mcp-scan
pip install pyyaml

# Generate config
python3 scripts/mcp-scan/generate_mcp_config.py npx/context7.yaml npx context7 > /tmp/config.json

# Run scan
mcp-scan scan /tmp/config.json --json > /tmp/scan-output.json

# Process results
python3 scripts/mcp-scan/process_scan_results.py /tmp/scan-output.json context7