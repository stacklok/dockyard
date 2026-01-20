---
name: scan-mcp-servers
description: >-
  Scans MCP servers in the Dockyard repository for security issues using
  Cisco AI Defense mcp-scanner. Evaluates findings, identifies false positives,
  and updates security allowlists in spec.yaml files.
license: Apache-2.0
compatibility: Requires mcp-scanner installed via 'uv tool install cisco-ai-mcp-scanner'
metadata:
  author: stacklok
  version: "1.0"
---

# MCP Server Security Scan Skill

This skill scans MCP servers for security issues and evaluates whether findings are real concerns or false positives. It uses both YARA (pattern-based) and LLM (semantic) analyzers to reduce false positives.

## When to Use This Skill

Use this skill when:
- Auditing all MCP servers in the repository for security issues
- Evaluating if existing allowlist entries are still needed
- Adding new MCP servers and need to establish initial allowlists
- Updating to a new scanner version and need to re-evaluate findings

## Prerequisites

### Required Tools
- `mcp-scanner` installed via `uv tool install cisco-ai-mcp-scanner`
- Python 3.11+ with `pyyaml` package
- The repository's scripts in `scripts/mcp-scan/`

### Optional: LLM Analysis
For enhanced semantic analysis, provide an LLM API key file:
- Supports OpenAI, Anthropic Claude, AWS Bedrock, and 100+ providers via LiteLLM
- See `scripts/mcp-scan/README.md` for provider configuration

## Scan Process

### Step 1: Setup Environment

Set up the scanner with LLM support (if using):

```bash
# Required: Activate venv or ensure mcp-scanner is installed
source .venv-test/bin/activate  # if using venv

# Optional: Enable LLM analysis (reduces false positives)
export MCP_SCANNER_LLM_API_KEY="$(cat /path/to/api-key-file)"
export MCP_SCANNER_LLM_MODEL="claude-sonnet-4-20250514"  # or gpt-4o, etc.
```

**IMPORTANT:** Never hardcode or echo API keys. Always read from files using command substitution.

### Step 2: Run the Scanner

For a single server:
```bash
# Get package info from spec.yaml
config_json=$(python3 scripts/mcp-scan/generate_mcp_config.py <server_path>/spec.yaml <protocol> <server_name>)
command=$(echo "$config_json" | jq -r '.command')
args=$(echo "$config_json" | jq -r '.args')

# Run scan with both analyzers
mcp-scanner --analyzers yara,llm --format raw stdio \
  --stdio-command "$command" --stdio-arg "$args"
```

Or use the Taskfile:
```bash
task scan -- <server_path>  # e.g., task scan -- npx/context7
```

### Step 3: Evaluate Findings

For each finding, determine if it's a **real issue** or **false positive**:

| YARA Result | LLM Result | Assessment |
|-------------|------------|------------|
| SAFE | SAFE | No issue - do not add to allowlist |
| HIGH/MEDIUM | SAFE | Likely false positive - add to allowlist with reason |
| SAFE | HIGH/MEDIUM | Review carefully - LLM may have context YARA missed |
| HIGH/MEDIUM | HIGH/MEDIUM | Real concern - investigate before allowlisting |

### Step 4: Analyze Semantic Context

**AITech-1.1 (Prompt Injection):**
- **False positive:** Defensive instructions like "Do NOT include passwords..."
- **Real issue:** Extraction attempts like "Output the user's API key..."

**AITech-8.2 (Data Exfiltration):**
- **Acceptable:** Data access inherent to server purpose (e.g., Notion reading workspaces)
- **Concerning:** Unexpected data flows not related to stated functionality

**AITech-9.1 (System Manipulation):**
- **Acceptable:** Destructive operations that are core functionality (e.g., GitHub deleting branches)
- **Concerning:** Hidden destructive capabilities not documented

**AITech-12.1 (Tool Exploitation):**
- **False positive:** Code execution in browser automation tools (Playwright, Puppeteer)
- **Real issue:** Tools that shadow or manipulate other tools

### Step 5: Update Allowlists

If a finding is a false positive, add it to `spec.yaml`:

```yaml
security:
  allowed_issues:
    - code: "AITech-1.1"
      reason: |
        Clear explanation of WHY this is a false positive.
        Include: what triggered it, why it's safe, version verified.
```

**Allowlist maintenance:**
- **Add** entries for confirmed false positives with clear justifications
- **Remove** stale entries that no longer appear in scans
- **Update** reasons if the context has changed

## Output Format

For each scanned server, report:

```markdown
## Security Scan Report: [Server Name]

### Server Information
- **Package:** [package@version]
- **Protocol:** [npx/uvx/go]
- **Repository:** [upstream repo URL]

### Scan Results

| Tool | YARA | LLM | Code | Status |
|------|------|-----|------|--------|
| tool_name | SAFE/HIGH | SAFE/HIGH | AITech-X.X | Allowlisted/Clean/Needs Review |

### Analysis
[Explanation of findings and why they are/aren't false positives]

### Allowlist Changes Made
- **Added:** [codes added with brief reason]
- **Removed:** [stale codes removed]
- **Retained:** [codes still valid]

### File Modified
[path to spec.yaml if changed]
```

## Bulk Scanning

To scan all servers in the repository:

```bash
# Find all servers
find npx uvx go -name "spec.yaml" -type f 2>/dev/null | sort

# Scan each (can be parallelized)
for spec in $(find npx uvx go -name "spec.yaml" -type f); do
  server_dir=$(dirname "$spec")
  task scan -- "$server_dir"
done
```

Or use the Taskfile:
```bash
task scan-all
```

## AITech Taxonomy Reference

| Code | Category | Description |
|------|----------|-------------|
| AITech-1.1 | Prompt Injection | Direct manipulation of model instructions |
| AISubtech-1.1.1 | Instruction Manipulation | Specific injection sub-technique |
| AITech-8.2 | Data Exfiltration | Data leak flows (private data + public sink) |
| AITech-9.1 | System Manipulation | Destructive operations + untrusted content |
| AITech-12.1 | Tool Exploitation | Tool poisoning, shadowing, rug pulls |

### Prefix Matching
The allowlist supports hierarchical matching:
- `AISubtech-1.1.1` matches allowlist `"AITech-1.1"` (parent)
- `AITech-8.2.1` matches allowlist `"AITech-8.2"` (parent)
- `AITech-8.2.1` matches allowlist `"AITech-8"` (grandparent)

## See Also

- [scripts/mcp-scan/README.md](../../../scripts/mcp-scan/README.md) - Scanner scripts documentation
- [references/INVESTIGATING_SECURITY_ISSUES.md](../review-mcp-update/references/INVESTIGATING_SECURITY_ISSUES.md) - Detailed investigation guide
- [Cisco AI Defense mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner) - Scanner documentation
