# spec.yaml Full Reference

Complete reference for Dockyard MCP server specification files.

## File Location

```
{protocol}/{server-name}/spec.yaml
```

Where `{protocol}` is one of: `npx`, `uvx`, `go`

## Full Schema

```yaml
# Comments documenting the package (optional but recommended)
# Package URL: https://...
# Repository: https://...
# Will build as: ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}

metadata:
  name: string           # Required: Server identifier (lowercase, hyphens)
  description: string    # Optional: Brief description
  version: string        # Optional: Server version (informational)
  protocol: string       # Required: npx | uvx | go

spec:
  package: string        # Required: Package identifier from registry
  version: string        # Required: Exact version (no ranges)
  args:                  # Optional: CLI arguments array
    - string

provenance:
  repository_uri: string    # Optional: Expected source repository URL
  repository_ref: string    # Optional: Git ref (refs/tags/v1.0.0)

  attestations:             # Optional: Document provenance status
    available: boolean      # Whether attestations exist
    verified: boolean       # Whether you verified them
    publisher:
      kind: string          # Publisher type: GitHub, GitLab
      repository: string    # Publisher repository (owner/repo)
      workflow: string      # Publishing workflow file (optional)

security:
  allowed_issues:           # Optional: Security scan allowlist
    - code: string          # Issue code from mcp-scanner
      reason: string        # Explanation of why it's acceptable
```

## Field Details

### metadata.name

- **Required**: Yes
- **Format**: Lowercase letters, numbers, hyphens only
- **Purpose**: Unique identifier, used in container image name
- **Example**: `context7`, `aws-documentation-mcp-server`

### metadata.protocol

- **Required**: Yes
- **Values**: `npx`, `uvx`, `go`
- **Purpose**: Determines build method and base image

### spec.package

- **Required**: Yes
- **Format**: Registry-specific package identifier
- **Examples**:
  - npm: `@upstash/context7-mcp` or `my-mcp-server`
  - PyPI: `mcp-clickhouse`
  - Go: `github.com/org/repo`

### spec.version

- **Required**: Yes
- **Format**: Exact version, no ranges
- **Examples**:
  - npm/PyPI: `1.0.14`, `0.1.13`
  - Go: `v0.3.1` (must include `v` prefix)

### spec.args

- **Required**: No
- **Format**: Array of strings
- **Purpose**: Additional CLI arguments passed to entrypoint
- **Example**:
  ```yaml
  args:
    - "start"
    - "--port"
    - "8080"
  ```

### provenance.repository_uri

- **Required**: No (but recommended)
- **Format**: Full HTTPS URL
- **Purpose**: Expected source repository for verification
- **Example**: `https://github.com/upstash/context7-mcp`

### provenance.attestations

- **Required**: No
- **Purpose**: Document package provenance status
- **Fields**:
  - `available`: Whether the package has attestations
  - `verified`: Whether you've verified them cryptographically
  - `publisher.kind`: Publisher type (GitHub, GitLab)
  - `publisher.repository`: Owner/repo format
  - `publisher.workflow`: Workflow file path (optional)

### security.allowed_issues

- **Required**: No
- **Purpose**: Allowlist false positives from security scan
- **Fields**:
  - `code`: Issue code from mcp-scanner (e.g., `AITech-1.1`)
  - `reason`: Clear explanation of why it's acceptable

## Examples by Protocol

### npm (npx)

```yaml
# Context7 MCP Server
# Package: https://www.npmjs.com/package/@upstash/context7-mcp
# Repository: https://github.com/upstash/context7-mcp
# Will build as: ghcr.io/stacklok/dockyard/npx/context7:2.1.0

metadata:
  name: context7
  description: "Upstash vector search and context management"
  version: "1.0.14"
  protocol: npx

spec:
  package: "@upstash/context7-mcp"
  version: "1.0.14"

provenance:
  repository_uri: "https://github.com/upstash/context7-mcp"
  repository_ref: "refs/tags/v1.0.14"
```

### npm with args

```yaml
# LaunchDarkly MCP Server
metadata:
  name: launchdarkly-mcp-server
  description: "LaunchDarkly feature flag management"
  version: "0.4.2"
  protocol: npx

spec:
  package: "@launchdarkly/mcp-server"
  version: "0.4.2"
  args:
    - "start"  # Required by this package

provenance:
  repository_uri: "https://github.com/launchdarkly/mcp-server"
  repository_ref: "refs/tags/v0.4.2"
```

### PyPI (uvx)

```yaml
# ClickHouse MCP Server
# Package: https://pypi.org/project/mcp-clickhouse/
# Repository: https://github.com/ClickHouse/mcp-clickhouse
# Will build as: ghcr.io/stacklok/dockyard/uvx/mcp-clickhouse:0.1.13

metadata:
  name: mcp-clickhouse
  description: "MCP server for ClickHouse database operations"
  version: "0.1.13"
  protocol: uvx

spec:
  package: "mcp-clickhouse"
  version: "0.1.13"

provenance:
  repository_uri: "https://github.com/ClickHouse/mcp-clickhouse"
  repository_ref: "refs/heads/main"

  attestations:
    available: true
    verified: true
    publisher:
      kind: "GitHub"
      repository: "ClickHouse/mcp-clickhouse"
```

### Go

```yaml
# NetBird MCP Server
# Module: github.com/netbirdio/netbird-mcp
# Will build as: ghcr.io/stacklok/dockyard/go/netbird:v0.1.0

metadata:
  name: netbird
  description: "NetBird network management MCP server"
  version: "0.1.0"
  protocol: go

spec:
  package: "github.com/netbirdio/netbird-mcp"
  version: "v0.1.0"  # Note: Go versions must include 'v' prefix

provenance:
  repository_uri: "https://github.com/netbirdio/netbird-mcp"
  repository_ref: "refs/tags/v0.1.0"
```

### With Security Allowlist

```yaml
metadata:
  name: my-server
  protocol: npx

spec:
  package: "my-mcp-server"
  version: "1.0.0"

security:
  allowed_issues:
    - code: "AITech-1.1"
      reason: "Tool description contains imperative instructions necessary for proper AI agent operation"
    - code: "AITech-9.1"
      reason: "Destructive flow is mitigated by container sandboxing - isolated from host"
```

## Container Image Naming

Images are published to:

```
ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}
```

Where:
- `{protocol}` matches `metadata.protocol`
- `{name}` matches `metadata.name`
- `{version}` matches `spec.version`
