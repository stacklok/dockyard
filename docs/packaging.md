# Packaging MCP Servers for Dockyard

Quick guide for packaging MCP servers as container images using the dockhand CLI.

## Directory Structure

```
{protocol}/{server-name}/spec.yaml
```

Protocols: `uvx` (Python/PyPI), `npx` (Node.js/npm), `go` (Go modules)

## spec.yaml Template

```yaml
# {Server Name} MCP Server Configuration
# {Brief description}
# Package: {package-registry-url}
# Repository: {source-repository-url}
# Will build as: ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}

metadata:
  name: {package-name}
  description: "{one-line description}"
  version: "{semantic-version}"
  protocol: {uvx|npx|go}

spec:
  package: "{package-identifier}"  # PyPI/npm name or Go module
  version: "{exact-version}"
  args:                            # Optional: CLI arguments for the package
    - "{arg1}"                     # Passed to the entrypoint command
    - "{arg2}"

provenance:
  repository_uri: "{github-url}"
  repository_ref: "{git-ref}"  # refs/heads/main or refs/tags/v1.0.0

  # Attestation information (if available)
  # Document package provenance for supply chain security
  attestations:
    available: true              # Whether the package has provenance attestations
    verified: true               # Whether you've verified the attestations
    publisher:
      kind: "{GitHub|GitLab}"   # Publisher type
      repository: "{owner/repo}" # Publisher repository
      workflow: "{workflow.yml}" # Publishing workflow (optional)

# Optional: Security allowlist
security:
  allowed_issues:
    - code: "{code}"
      reason: "{explanation}"
```

## Real Examples

### Python (uvx)
```yaml
metadata:
  name: mcp-clickhouse
  description: "MCP server for ClickHouse database operations"
  version: "0.1.11"
  protocol: uvx

spec:
  package: "mcp-clickhouse"
  version: "0.1.11"

provenance:
  repository_uri: "https://github.com/ClickHouse/mcp-clickhouse"
  repository_ref: "refs/heads/main"
```

### Node.js (npx)
```yaml
metadata:
  name: context7
  description: "MCP server for context management"
  version: "1.0.0"
  protocol: npx

spec:
  package: "@context7/mcp-server"
  version: "1.0.0"

provenance:
  repository_uri: "https://github.com/context7/mcp-server"
  repository_ref: "refs/tags/v1.0.0"
```

## Using dockhand CLI

```bash
# Generate Dockerfile to stdout
dockhand build -c uvx/mcp-clickhouse/spec.yaml

# Save Dockerfile
dockhand build -c uvx/mcp-clickhouse/spec.yaml -o Dockerfile

# Custom tag
dockhand build -c uvx/mcp-clickhouse/spec.yaml -t myregistry/image:v1.0.0
```

Flags:
- `-c, --config`: YAML spec file (required)
- `-o, --output`: Output file (default: stdout)
- `-t, --tag`: Custom image tag
- `-v, --verbose`: Verbose output

## Adding a New MCP Server

1. Find package info:
```bash
# Python
curl -s https://pypi.org/pypi/{package}/json | jq -r '.info.version'

# Node.js
npm view {package} version
```

2. Create structure:
```bash
mkdir -p {protocol}/{server-name}
```

3. Create `spec.yaml` using template above

4. Test:
```bash
# Validate spec and generate Dockerfile
task build -- {protocol}/{server-name}

# Run security scan
task scan -- {protocol}/{server-name}

# Optional: Build and test container image
task test-build -- {protocol}/{server-name}
```

5. Commit with descriptive message:
```bash
git add {protocol}/{server-name}/spec.yaml
git commit -m "feat: add {server-name} MCP server package

Add packaging for {server-name} v{version}.
Package: {package-url}
Repository: {repo-url}"
```

## Key Rules

1. **Always use exact versions** - no ranges or latest tags
2. **Test locally before committing**
3. **Include all metadata fields**
4. **Use correct protocol directory** (uvx/npx/go)
5. **Reference official package registries** in comments

## CI/CD

- Pushes to main trigger automatic builds
- Images published to `ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}`
- Multi-architecture builds (amd64, arm64)
- Automated security scanning

### Verifying CI Builds

After pushing changes:
1. Check workflow runs: `https://github.com/stacklok/dockyard/actions`
2. Look for your package in the build jobs (e.g., `build-containers (uvx/mcp-clickhouse/spec.yaml)`)
3. Verify security scan passed: `mcp-security-scan (uvx/mcp-clickhouse/spec.yaml)`
4. Manual trigger if needed: Actions → Build MCP Server Containers → Run workflow

Note: Only spec.yaml changes trigger automatic builds. Manual triggers build all packages.

## Quick Debugging

| Issue | Solution |
|-------|----------|
| Package not found | Verify exact package name in registry |
| Build fails | Check Dockerfile syntax with `dockhand build -c spec.yaml` |
| Version error | Ensure version exists in package registry |
| Wrong protocol | Verify package type matches directory (uvx/npx/go) |

## Verifying Package Provenance

Before adding a new MCP server, verify its provenance:

```bash
# After creating the spec.yaml, verify the package
dockhand verify-provenance -c {protocol}/{server-name}/spec.yaml

# With verbose output to see details
dockhand verify-provenance -c {protocol}/{server-name}/spec.yaml -v
```

### Understanding Provenance Status

- **VERIFIED**: Package has attestations that were cryptographically verified
- **ATTESTATIONS**: Package has attestations (npm) or PEP 740 attestations (PyPI)
- **SIGNATURES**: Package has signatures (older npm format)
- **TRUSTED_PUBLISHER**: Package uses PyPI Trusted Publishers
- **NONE**: No provenance information available

### Documenting Provenance in spec.yaml

If provenance is available, document it in your spec.yaml:

```yaml
provenance:
  repository_uri: "https://github.com/owner/repo"
  repository_ref: "refs/tags/v1.0.0"

  attestations:
    available: true
    verified: true
    publisher:
      kind: "GitHub"
      repository: "owner/repo"
      workflow: ".github/workflows/release.yml"
```

This helps future maintainers verify that attestations haven't been removed and establishes the expected publisher identity.

### Provenance Best Practices

1. **Always check provenance** before adding new packages
2. **Prefer packages with attestations** when multiple options exist
3. **Document attestation info** in spec.yaml for verification
4. **Re-verify** when updating package versions

## Resources

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Dockyard Repository](https://github.com/stacklok/dockyard)
- [Example MCP Servers](https://github.com/modelcontextprotocol/servers)
- [npm Provenance](https://docs.npmjs.com/generating-provenance-statements)
- [PyPI Attestations (PEP 740)](https://peps.python.org/pep-0740/)
- [Sigstore Documentation](https://docs.sigstore.dev/)