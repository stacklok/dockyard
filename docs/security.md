# Dockyard Security Overview

Dockyard provides multiple layers of security to ensure safe distribution of MCP server containers and agent skill artifacts.

## Security Guarantees

When you use a Dockyard container or skill artifact, you can be confident that:

1. **Source Integrity** - The image/artifact was built from the exact source code in this repository (for skills, from the exact upstream commit pinned in `spec.ref`)
2. **Build Transparency** - Full build provenance is available and verifiable
3. **Security Scanning** - MCP servers are scanned with mcp-scanner and skills are scanned with skill-scanner before packaging
4. **Container Vulnerability Scanning** - MCP server images are additionally scanned with Trivy for CVEs, secrets, and misconfigurations
5. **Dependency Tracking** - Complete SBOM is available for vulnerability management
6. **Non-repudiation** - Signatures prove the image/artifact came from our CI/CD pipeline
7. **Continuous Monitoring** - Weekly scans catch newly disclosed vulnerabilities in MCP server containers

## MCP Security Scanning

All MCP servers are scanned using [Cisco AI Defense mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner) before building containers. This scan is **blocking** - servers that fail cannot be packaged.

### What We Scan For

| Category | Description |
|----------|-------------|
| **Prompt Injection** | Dangerous patterns in tool descriptions that could be exploited |
| **Toxic Flows** | Tool combinations that could lead to destructive behaviors |
| **Tool Poisoning** | Malicious tool implementations |
| **Cross-Origin Escalation** | Potential privilege escalation vulnerabilities |
| **Rug Pull Attacks** | Suspicious patterns indicating malicious intent |

### Scan Results

When vulnerabilities are found in a PR, you'll see a detailed report:

```
## MCP Security Scan Results

### your-mcp-server
- **Status**: Failed
- **Tools scanned**: 3
- **Vulnerabilities found**: 2

**Security issues detected:**
- **[W001]** Tool description contains dangerous words
- **[TF002]** Destructive toxic flow detected
```

### Allowing Known Issues

Some warnings may be false positives for containerized deployments. Add them to the allowlist in your spec.yaml:

```yaml
security:
  allowed_issues:
    - code: "AITech-1.1"
      reason: "Imperative instructions required for proper AI agent operation"
    - code: "AITech-9.1"
      reason: "Destructive flow mitigated by container sandboxing"
```

Each allowed issue must include:
- `code` - The issue code from mcp-scanner
- `reason` - Clear explanation of why it's acceptable

## Agent Skill Security Scanning

All agent skills are scanned using [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) at the pinned commit before packaging. This scan is **blocking** at `HIGH` severity and above — skills with unallowlisted findings at or above that threshold cannot be packaged.

### What We Scan For

Skill-scanner runs its core pattern-based (static and YARA) rules plus the PromptGuard rule pack, behavioral (AST/taint) analysis, and LLM-based semantic analysis, under the scanner's `quiet` policy preset. It looks for the same broad categories as mcp-scanner (prompt injection, tool/agent poisoning, credential harvesting, PII exposure) applied to a skill's `SKILL.md` and reference files instead of MCP tool descriptions.

The scan fails if the LLM analysis doesn't run or errors, rather than passing on pattern rules alone. `MEDIUM` findings, and any files too large for the LLM to read in full, are listed in the PR's scan results comment for a reviewer to check, but don't block.

### Allowing Known Issues

Skill documentation is prose- and example-heavy, so pattern rules produce many false positives (shell variable expansion in documented setup commands, code-fence language tokens, example IP addresses, placeholder credentials). Add them to the allowlist in the skill's `spec.yaml`, matching by `rule_id` (exact) or `category` (broader):

```yaml
security:
  allowed_issues:
    - rule_id: PG_PII_CREDENTIAL_HARVESTING
      reason: "FP: matched advice to store credentials in a dedicated
        `~/.mcp-env` file (SKILL.md:213). The skill tells users where to keep
        their own credentials; it never asks the user for them."
```

Each allowed issue must include:
- `rule_id` (or `category`) - The finding identifier from skill-scanner
- `reason` - Clear explanation, citing the specific matched text/location, of why it's a false positive or an accepted risk

See [Adding Skills](adding-skills.md#security-scanning) for the full workflow, and `scripts/skill-scan/README.md` for the scanner wrapper scripts.

## Container Vulnerability Scanning

Built containers are scanned with [Trivy](https://trivy.dev/) for:

| Category | Description |
|----------|-------------|
| **Vulnerabilities** | CVEs in OS packages and dependencies (CRITICAL, HIGH, MEDIUM) |
| **Secrets** | Exposed API keys, tokens, credentials |
| **Misconfigurations** | Security issues in container configuration |

### Scan Schedule

- **Every PR** - Immediate feedback on new/changed containers
- **On main branch** - Scans all published images after build
- **Weekly (Monday 2am UTC)** - Comprehensive scans to catch new CVEs
- **Manual trigger** - On-demand via GitHub Actions

### Viewing Results

Trivy results are uploaded to the GitHub Security tab:

```
https://github.com/stacklok/dockyard/security/code-scanning
```

Filter by `trivy-{server-name}` to see specific results.

## Container Signing

All images are signed with [Sigstore/Cosign](https://docs.sigstore.dev/cosign/) using keyless OIDC via GitHub Actions.

### Verify Image Signature

```bash
cosign verify \
  --certificate-identity-regexp "https://github.com/stacklok/dockyard/.github/workflows/build-containers.yml@refs/heads/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/stacklok/dockyard/npx/context7:2.1.0
```

## Container Attestations

Each image includes multiple attestations:

| Type | Format | Description |
|------|--------|-------------|
| SBOM | SPDX | Software Bill of Materials |
| Build Provenance | SLSA | Build integrity attestation |
| MCP Security Scan | SCAI v0.3 | Security scan results |
| Signature | Sigstore | Keyless OIDC signature |

### View Attestations

```bash
# View SBOM
docker buildx imagetools inspect \
  ghcr.io/stacklok/dockyard/npx/context7:2.1.0 \
  --format "{{ json .SBOM }}"

# View Provenance
docker buildx imagetools inspect \
  ghcr.io/stacklok/dockyard/npx/context7:2.1.0 \
  --format "{{ json .Provenance }}"

# View Security Scan Attestation
cosign verify-attestation \
  --type https://in-toto.io/attestation/scai/v0.3 \
  --certificate-identity-regexp "https://github.com/stacklok/dockyard/.github/workflows/build-containers.yml@refs/heads/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/stacklok/dockyard/npx/context7:2.1.0
```

For detailed attestation schemas and policy examples, see [Container Attestations](attestations.md).

> Skill artifacts get the same SBOM, build provenance, and SCAI security-scan
> attestations, signed by the `build-skills.yml` workflow instead of
> `build-containers.yml` — substitute that workflow name in the
> `--certificate-identity-regexp` above and the artifact reference with
> `ghcr.io/stacklok/dockyard/skills/{name}:{version}`. See
> [Adding Skills](adding-skills.md#what-ci-does).

## Package Provenance

Dockyard verifies package provenance for npm and PyPI packages before building:

- **npm** - Checks for signatures and modern Sigstore attestations
- **PyPI** - Verifies PEP 740 attestations and Trusted Publishers

For details on provenance verification, see [Package Provenance](provenance.md).

## Policy Enforcement

SCAI attestations integrate with policy engines for Kubernetes:

- **Kyverno** - Verify attestations before pod deployment
- **OPA/Gatekeeper** - Custom policies based on scan results

Example policies are provided in [Container Attestations](attestations.md).

## Reporting Security Issues

If you discover a security vulnerability:

1. **Do NOT** disclose publicly until we've had a chance to fix it
2. **Do NOT** use GitHub issues for security reports
3. Follow the process in [SECURITY.MD](../SECURITY.MD)
