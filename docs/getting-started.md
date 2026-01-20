# Getting Started with Dockyard Containers

This guide shows you how to pull, run, and verify MCP server containers from Dockyard.

## Quick Start

Pull and run an MCP server container:

```bash
# Pull a container
docker pull ghcr.io/stacklok/dockyard/npx/context7:2.1.0

# Run it
docker run -it ghcr.io/stacklok/dockyard/npx/context7:2.1.0
```

## Available Containers

All containers follow this naming pattern:

```
ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}
```

Where:
- `protocol` is `npx` (Node.js), `uvx` (Python), or `go`
- `name` is the server name
- `version` is the specific package version

### Example Containers

| Server | Image | Description |
|--------|-------|-------------|
| Context7 | `ghcr.io/stacklok/dockyard/npx/context7:2.1.0` | Upstash vector search |
| AWS Docs | `ghcr.io/stacklok/dockyard/uvx/aws-documentation-mcp-server:1.1.16` | AWS documentation server |
| ClickHouse | `ghcr.io/stacklok/dockyard/uvx/mcp-clickhouse:0.1.13` | ClickHouse database operations |

Browse all available containers in the [npx/](https://github.com/stacklok/dockyard/tree/main/npx), [uvx/](https://github.com/stacklok/dockyard/tree/main/uvx), and [go/](https://github.com/stacklok/dockyard/tree/main/go) directories.

## Verifying Container Signatures

All Dockyard containers are signed with Sigstore/Cosign. Verify a container before running:

```bash
# Install cosign
brew install cosign  # or see https://docs.sigstore.dev/cosign/installation/

# Verify the signature
cosign verify \
  --certificate-identity-regexp "https://github.com/stacklok/dockyard/.github/workflows/build-containers.yml@refs/heads/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/stacklok/dockyard/npx/context7:2.1.0
```

For detailed verification options including attestations, see [Container Attestations](attestations.md).

## Using with ToolHive

[ToolHive](https://docs.stacklok.com/toolhive) can run Dockyard containers directly:

```bash
# Install ToolHive
brew install stacklok/tap/toolhive

# Run an MCP server
thv run ghcr.io/stacklok/dockyard/npx/context7:2.1.0
```

## Multi-Architecture Support

All containers are built for both `linux/amd64` and `linux/arm64` architectures. Docker automatically pulls the correct architecture for your system.

## Environment Variables

MCP servers may require environment variables for API keys or configuration. Pass them when running:

```bash
docker run -it \
  -e API_KEY=your-key \
  -e CONFIG_PATH=/app/config \
  ghcr.io/stacklok/dockyard/npx/your-server:version
```

Check the original MCP server's documentation for required environment variables.

## What's Next?

- [Security Overview](security.md) - Understand the security guarantees
- [Container Attestations](attestations.md) - Verify build provenance and security scans
- [Add Your Own Server](adding-servers.md) - Contribute an MCP server to Dockyard
