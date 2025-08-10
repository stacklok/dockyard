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

provenance:
  repository_uri: "{github-url}"
  repository_ref: "{git-ref}"  # refs/heads/main or refs/tags/v1.0.0

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
# Validate spec
dockhand build -c {protocol}/{server-name}/spec.yaml

# Build image
dockhand build -c {protocol}/{server-name}/spec.yaml -o Dockerfile
docker build -t test-server .

# Run test
docker run --rm test-server --help
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

## Quick Debugging

| Issue | Solution |
|-------|----------|
| Package not found | Verify exact package name in registry |
| Build fails | Check Dockerfile syntax with `dockhand build -c spec.yaml` |
| Version error | Ensure version exists in package registry |
| Wrong protocol | Verify package type matches directory (uvx/npx/go) |

## Resources

- [MCP Documentation](https://modelcontextprotocol.io/)
- [Dockyard Repository](https://github.com/stacklok/dockyard)
- [Example MCP Servers](https://github.com/modelcontextprotocol/servers)