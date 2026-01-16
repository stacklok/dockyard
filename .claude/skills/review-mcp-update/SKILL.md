---
name: review-mcp-update
description: >-
  Reviews pull requests for MCP server updates in the Dockyard repository.
  Use when reviewing PRs that update MCP server versions (spec.yaml changes),
  add new MCP servers, or modify security allowlists. Evaluates against
  ToolHive registry criteria including security, provenance, and quality.
license: Apache-2.0
compatibility: Requires GitHub MCP server for API access
metadata:
  author: stacklok
  version: "1.0"
---

# MCP Server Update PR Review Skill

This skill helps you review pull requests that update MCP server packages in the Dockyard repository. Dockyard automatically packages MCP servers into OCI container images using declarative `spec.yaml` configurations.

## When to Use This Skill

Use this skill when:
- Reviewing Renovate bot PRs that update MCP server versions
- Reviewing PRs that add new MCP servers to the registry
- Reviewing PRs that modify security allowlists
- Evaluating MCP servers against ToolHive registry criteria

## Review Process

### Step 1: Identify the PR and Changed Files

First, get the PR details and identify what changed:

1. Use `mcp__github__pull_request_read` with method `get` to get PR details
2. Use `mcp__github__pull_request_read` with method `get_files` to see changed files
3. Look for changes to `spec.yaml` files in `npx/`, `uvx/`, or `go/` directories

### Step 2: Analyze Version Changes

For each changed `spec.yaml`:

1. **Identify the version bump type:**
   - **Patch** (x.y.Z): Bug fixes, safe to merge after CI passes
   - **Minor** (x.Y.z): New features, review changelog for new capabilities
   - **Major** (X.y.z): Breaking changes, requires careful review

2. **Review the release notes** in the PR description (Renovate includes these)

3. **Check for breaking changes** that might affect:
   - Tool names or signatures
   - Required arguments (`spec.args`)
   - Authentication requirements
   - API endpoints

### Step 3: Verify CI Status

Check that all required CI checks pass:

1. Use `mcp__github__pull_request_read` with method `get_status` to check CI status
2. **Required checks:**
   - `MCP Security Scan` - Must pass (blocks merge if failed)
   - `Verify Provenance` - Informational, check for regressions
   - `Build Containers` - Must pass
   - `Trivy Vulnerability Scan` - Review findings

3. **If MCP Security Scan fails**, check for:
   - Prompt injection risks (AITech-1.1)
   - Data exfiltration (AITech-8.2) and system manipulation (AITech-9.1) flows
   - Tool exploitation (AITech-12.1)
   - Whether a security allowlist entry is needed in `spec.yaml`

### Step 3a: Investigating Security Scan Failures

When the MCP Security Scan fails, determine if issues are **real security concerns** or **false positives** before adding allowlist entries:

1. **Get detailed scan output** by running mcp-scanner directly:
   ```bash
   uv tool run mcp-scanner stdio --stdio-command npx --stdio-arg "@package/name@version" --format raw
   ```

2. **Examine the upstream source code** to understand what's triggering the warning:
   - Find tool definitions in the MCP server source
   - Look at the actual tool descriptions being flagged

3. **Analyze the semantic context**:
   - **False positive**: Flagged words appear in defensive context (e.g., "Do NOT include passwords...")
   - **Real issue**: Flagged words attempt to extract data or manipulate behavior

4. **If false positive**, add allowlist with clear justification explaining WHY it's safe

See [references/INVESTIGATING_SECURITY_ISSUES.md](references/INVESTIGATING_SECURITY_ISSUES.md) for detailed investigation procedures, issue code meanings, and examples of identifying false positives.

### Step 4: Evaluate Upstream Repository Health

For new servers or major version updates, evaluate against ToolHive registry criteria:

**Required Criteria:**
- [ ] Open source with acceptable license (Apache-2.0, MIT, BSD-2/3-Clause)
- [ ] Source code publicly accessible
- [ ] NOT using copyleft licenses (AGPL, GPL)

**Security Criteria:**
- [ ] Check for software provenance (Sigstore, GitHub Attestations)
- [ ] Look for SLSA compliance indicators
- [ ] Verify pinned dependencies in the upstream repo
- [ ] Check for published SBOMs

**Quality Criteria:**
- [ ] Active commit history (recent commits within last 3 months)
- [ ] Responsive maintainers (issues addressed within 3-4 weeks)
- [ ] Automated testing and CI/CD
- [ ] Semantic versioning compliance

Use `mcp__github__search_repositories` or direct GitHub API calls to check:
- Repository stars and forks
- Recent commit activity
- Open issues and response times
- License information

### Step 5: Verify Provenance Information

If the `spec.yaml` includes provenance information:

1. Verify `repository_uri` matches the actual source
2. Check that `repository_ref` aligns with the version being installed
3. For packages with attestations:
   - Verify the publisher workflow is still the same
   - Check if attestation status changed (available/verified)

### Step 6: Review Security Allowlist Changes

If the PR adds or modifies `security.allowed_issues`:

1. **Verify each allowlist entry has:**
   - A specific issue code (AITech-1.1, AITech-8.2, AITech-9.1, AITech-12.1, etc.)
   - A clear, justified reason explaining why it's acceptable

2. **Common acceptable allowlist reasons:**
   - AITech-1.1: "Tool description contains legitimate usage instructions"
   - AITech-8.2: "Data access flow is inherent to the server's design"
   - AITech-9.1: "Destructive operations are essential for the server's purpose"

3. **Red flags requiring extra scrutiny:**
   - Multiple new AITech-9.1 (destructive flow) entries
   - Tool poisoning issues (AITech-12.1)
   - Cross-origin escalation warnings

## Output Format

After completing the review, provide a structured summary:

```markdown
## MCP Server Update Review: [Server Name]

### Change Summary
- **Package:** [package name]
- **Version:** [old version] → [new version]
- **Change Type:** [Patch/Minor/Major]
- **Protocol:** [npx/uvx/go]

### CI Status
- MCP Security Scan: [Pass/Fail/Pending]
- Provenance Verification: [Verified/Signatures/None]
- Container Build: [Pass/Fail/Pending]
- Vulnerability Scan: [Clean/Findings]

### Breaking Changes
[List any breaking changes from release notes]

### Security Considerations
[Any new security allowlist entries or concerns]

### Upstream Health (for major updates)
- License: [license type]
- Recent Activity: [active/stale]
- Open Issues: [count]
- Maintainer Response: [responsive/slow]

### Recommendation
[APPROVE / REQUEST_CHANGES / COMMENT]
[Justification for recommendation]
```

## Quick Reference: spec.yaml Structure

```yaml
metadata:
  name: "server-name"           # Unique identifier
  description: "..."            # What the server does
  protocol: "npx|uvx|go"        # Package ecosystem

spec:
  package: "package-name"       # Registry package name
  version: "x.y.z"              # Exact version
  args:                         # Optional CLI arguments
    - "arg1"

provenance:
  repository_uri: "https://..."
  repository_ref: "refs/tags/..."
  attestations:
    available: true|false
    verified: true|false
    publisher:
      kind: "GitHub"
      repository: "owner/repo"
      workflow: ".github/workflows/..."

security:
  allowed_issues:
    - code: "AITech-1.1|AITech-8.2|AITech-9.1|..."
      reason: "Clear justification"
```

## See Also

- [references/REGISTRY_CRITERIA.md](references/REGISTRY_CRITERIA.md) - Full ToolHive registry criteria
- [references/INVESTIGATING_SECURITY_ISSUES.md](references/INVESTIGATING_SECURITY_ISSUES.md) - Detailed guide for investigating security scan failures
- [ToolHive Registry Criteria (online)](https://docs.stacklok.com/toolhive/concepts/registry-criteria) - Official documentation
- [Cisco AI Defense mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner) - Security scanner documentation
