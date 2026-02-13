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
  version: "1.1"
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

### Step 1: Verify CI Status (HARD GATE — Do This First)

**Always check CI before any other analysis. If CI is red, stop — do not approve.**

**IMPORTANT:** Do NOT use `mcp__github__pull_request_read` with method `get_status` — it only returns legacy commit statuses and misses GitHub Actions check runs entirely (returns `total_count: 0`).

**Use this `gh` command via Bash to get actual check run results:**
```bash
gh pr list --repo {owner}/{repo} --state open --json number,title,statusCheckRollup \
  --jq '.[] | {number, title, checks: [.statusCheckRollup[]? | {name: .name, status: .status, conclusion: .conclusion}]}'
```

When reviewing a single PR, add `| select(.number == {PR_NUMBER})` to the jq filter.

**Required checks — FAILURE on any of these blocks the PR:**
| Check | FAILURE | SUCCESS | NEUTRAL | SKIPPED |
|-------|---------|---------|---------|---------|
| `mcp-security-scan` | BLOCK | OK | OK | OK |
| `build-containers` | BLOCK | OK | — | OK |
| `Build` | BLOCK | OK | — | — |
| `Lint` | BLOCK | OK | — | — |

**Informational checks (do not block merge):**
- `verify-provenance` — note regressions but don't block
- `Trivy` — NEUTRAL is normal; review only if FAILURE
- `summary`, `discover-configs`, `save-pr-number` — infrastructure, ignore

**HARD GATE:** If ANY required check has `conclusion: "FAILURE"`, do NOT approve or recommend merging that PR. Report the failure and stop the review for that PR. Continue reviewing other PRs.

### Step 2: Identify the PR and Changed Files

Get the PR details and identify what changed:

1. Use `mcp__github__pull_request_read` with method `get` to get PR details
2. Use `mcp__github__pull_request_read` with method `get_files` to see changed files
3. Look for changes to `spec.yaml` files in `npx/`, `uvx/`, or `go/` directories

### Step 3: Analyze Version Changes

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

### Step 3a: Investigating Security Scan Failures (when mcp-security-scan fails)

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

### Step 4: Evaluate Upstream Repository Health (for new servers or major updates)

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

### CI Status (checked first)
- Build: [Pass/Fail]
- Lint: [Pass/Fail]
- MCP Security Scan: [Pass/Fail/Skipped]
- Container Build: [Pass/Fail/Skipped]
- Provenance Verification: [Pass/Fail] (informational)
- Trivy: [Neutral/Findings] (informational)

> If any required check FAILED, stop here: **DO NOT MERGE**

### Change Summary
- **Package:** [package name]
- **Version:** [old version] → [new version]
- **Change Type:** [Patch/Minor/Major]
- **Protocol:** [npx/uvx/go]

### Breaking Changes
[List any breaking changes from release notes]

### Security Considerations
[Any new security allowlist entries or concerns]

### Upstream Health (for major updates only)
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
