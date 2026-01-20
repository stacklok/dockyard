# Dockyard

[![Build Status](https://github.com/stacklok/dockyard/actions/workflows/build-containers.yml/badge.svg)](https://github.com/stacklok/dockyard/actions/workflows/build-containers.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**A centralized repository for packaging Model Context Protocol (MCP) servers into secure, verified containers.**

Dockyard automatically builds, scans, and publishes container images for MCP servers. Every container is security-scanned, signed with Sigstore, and includes full build provenance.

## Quick Start

```bash
# Pull a container
docker pull ghcr.io/stacklok/dockyard/npx/context7:2.1.0

# Verify its signature
cosign verify \
  --certificate-identity-regexp "https://github.com/stacklok/dockyard/.github/workflows/build-containers.yml@refs/heads/.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/stacklok/dockyard/npx/context7:2.1.0

# Run it
docker run -it ghcr.io/stacklok/dockyard/npx/context7:2.1.0
```

## Documentation

| I want to... | Go here |
|--------------|---------|
| **Use Dockyard containers** | [Getting Started](docs/getting-started.md) |
| **Add my MCP server** | [Adding MCP Servers](docs/adding-servers.md) |
| **Understand the security model** | [Security Overview](docs/security.md) |
| **Verify attestations** | [Container Attestations](docs/attestations.md) |
| **Check package provenance** | [Package Provenance](docs/provenance.md) |

## Supported Protocols

| Protocol | Registry | Example |
|----------|----------|---------|
| `npx://` | npm | `ghcr.io/stacklok/dockyard/npx/context7:2.1.0` |
| `uvx://` | PyPI | `ghcr.io/stacklok/dockyard/uvx/aws-documentation-mcp-server:1.1.16` |
| `go://` | Go modules | `ghcr.io/stacklok/dockyard/go/netbird:0.1.0` |

Browse available servers: [npx/](npx/) | [uvx/](uvx/) | [go/](go/)

## Add Your MCP Server

Create a `spec.yaml` in the appropriate directory and submit a PR:

```yaml
metadata:
  name: your-server
  description: "What your server does"
  protocol: npx  # or uvx, go

spec:
  package: "your-package-name"
  version: "1.0.0"
```

Our CI/CD pipeline will automatically:
1. Scan for security vulnerabilities (blocking)
2. Verify package provenance (informational)
3. Build multi-arch containers
4. Sign and attest with Sigstore
5. Publish to `ghcr.io/stacklok/dockyard`

See [Adding MCP Servers](docs/adding-servers.md) for the full guide.

## Security

Every container includes:
- **MCP Security Scan** - Scanned with [mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner) before build
- **Container Scan** - Trivy vulnerability scanning
- **Signed Images** - Sigstore/Cosign keyless signatures
- **Attestations** - SBOM, build provenance, and security scan results

See [Security Overview](docs/security.md) for details.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

To add an MCP server, see [Adding MCP Servers](docs/adding-servers.md).

## License

Apache 2.0 - see [LICENSE](LICENSE) for details.

## Links

- [ToolHive](https://docs.stacklok.com/toolhive) - Container building technology
- [MCP Documentation](https://modelcontextprotocol.io/) - Model Context Protocol
- [Sigstore](https://docs.sigstore.dev/) - Container signing
