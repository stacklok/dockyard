---
name: package-mcp-server
description: Creates spec.yaml configurations for packaging MCP servers as containers. Use when adding a new MCP server to Dockyard, creating a spec.yaml file, or packaging npm/PyPI/Go MCP servers.
---

# Package MCP Server for Dockyard

This skill helps you package MCP servers for distribution via Dockyard containers.

## When to Use This Skill

Use this skill when:
- Adding a new MCP server to Dockyard
- Creating a spec.yaml configuration file
- Packaging an npm (npx), PyPI (uvx), or Go MCP server
- The user mentions "package", "add server", "spec.yaml", or "dockyard"

## Prerequisites

- The MCP server must be published to npm, PyPI, or as a Go module
- Know the exact package name and version

## Workflow

### Step 1: Gather Information

Ask the user for:
1. **Package name** - The exact registry name (e.g., `@upstash/context7-mcp`, `mcp-clickhouse`)
2. **Package type** - npm (npx), PyPI (uvx), or Go
3. **Version** - Specific version to package (not "latest")
4. **Source repository** - GitHub URL for the source code

If not provided, look up the package:

```bash
# For npm packages
npm view {package-name} version
npm view {package-name} repository.url

# For PyPI packages
curl -s https://pypi.org/pypi/{package-name}/json | jq -r '.info.version, .info.project_urls.Homepage'
```

### Step 2: Determine Protocol Directory

| Package Type | Directory | Registry |
|--------------|-----------|----------|
| Node.js/npm | `npx/` | npm |
| Python/PyPI | `uvx/` | PyPI |
| Go module | `go/` | Go modules |

### Step 3: Create Directory Structure

```bash
mkdir -p {protocol}/{server-name}
```

The server name should be:
- Lowercase with hyphens
- Based on the package name (without scope)
- Example: `@upstash/context7-mcp` becomes `context7`

### Step 4: Create spec.yaml

Write the configuration file to `{protocol}/{server-name}/spec.yaml`:

```yaml
# {Server Name} MCP Server Configuration
# Package: {package-registry-url}
# Repository: {source-repository-url}
# Will build as: ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}

metadata:
  name: {server-name}
  description: "{brief-description}"
  version: "{version}"
  protocol: {npx|uvx|go}

spec:
  package: "{full-package-name}"
  version: "{exact-version}"
  # args:                          # Optional: CLI arguments
  #   - "start"                    # Some packages need specific commands

provenance:
  repository_uri: "{github-repo-url}"
  repository_ref: "refs/tags/v{version}"

  # Optional: Document attestations if available
  # attestations:
  #   available: true
  #   verified: true
  #   publisher:
  #     kind: "GitHub"
  #     repository: "{owner/repo}"
```

### Step 5: Build dockhand CLI (First Time Only)

```bash
# Build the dockhand CLI tool
task build-setup
```

### Step 6: Verify Provenance (Recommended)

Check if the package has provenance attestations:

```bash
# Check provenance
./build/dockhand verify-provenance -c {protocol}/{server-name}/spec.yaml -v
```

If provenance exists, update the spec.yaml with attestation information.

### Step 7: Test Locally

```bash
# Setup scanner (first time only)
task scan-setup

# Validate spec and generate Dockerfile
task build -- {protocol}/{server-name}

# Run security scan
task scan -- {protocol}/{server-name}

# Optional: Full build test
task test-build -- {protocol}/{server-name}
```

### Step 8: Commit

```bash
git add {protocol}/{server-name}/spec.yaml
git commit -m "feat: add {server-name} MCP server

Add packaging for {server-name} v{version}.
Package: {package-url}
Repository: {repo-url}"
```

## Protocol-Specific Notes

### npm (npx)

- Package name may include scope: `@org/package-name`
- Some packages require CLI args (e.g., `args: ["start"]`)
- Check if package has npm provenance signatures

### PyPI (uvx)

- Package name is usually lowercase with hyphens
- Check for PEP 740 attestations
- AWS Labs packages have verified attestations

### Go

- Package is the full module path: `github.com/org/repo`
- Version must include `v` prefix: `v0.3.1`

## Common Issues

| Issue | Solution |
|-------|----------|
| Package not found | Verify exact name in registry |
| Version doesn't exist | Check available versions with `npm view` or PyPI API |
| Security scan fails | Review issues, add allowlist if false positive |
| Build fails | Check Dockerfile output with `dockhand build -c spec.yaml` |

## See Also

- [SPEC-YAML-REFERENCE.md](references/SPEC-YAML-REFERENCE.md) - Full spec.yaml reference
- [docs/adding-servers.md](../../../docs/adding-servers.md) - Complete contribution guide
- [docs/provenance.md](../../../docs/provenance.md) - Provenance verification details
