# Dockyard - MCP Server Container Builder

> **A centralized repository for packaging Model Context Protocol (MCP) servers into containers**

Dockyard automatically builds and publishes container images for MCP servers that aren't already containerized. It uses [ToolHive](https://docs.stacklok.com/toolhive) to build containers from protocol schemes and provides a simple YAML-based configuration system.

## 🚀 Quick Start

Want to add your MCP server? Just create a YAML file in the appropriate protocol directory and submit a PR! Our automated CI/CD pipeline will build and publish the container image automatically.

## 📦 Supported Protocols

- **`npx://`** - Node.js packages from npm registry
- **`uvx://`** - Python packages using uv package manager
- **`go://`** - Go packages and modules

## 🏗️ Available MCP Servers

| Server | Protocol | Container Image | Description |
|--------|----------|-----------------|-------------|
| [Context7](https://github.com/upstash/context7-mcp) | npx | `ghcr.io/stacklok/dockyard/npx/context7:1.0.14` | Upstash vector search and context management |
| [AWS Documentation](https://github.com/awslabs/mcp) | uvx | `ghcr.io/stacklok/dockyard/uvx/aws-documentation-mcp-server:1.1.2` | AWS Labs documentation server |

## 🤝 Contributing Your Own MCP Server

Adding your MCP server to Dockyard is simple! Follow these steps:

### Step 1: Choose the Right Protocol Directory

- **`npx/`** - For Node.js packages published to npm
- **`uvx/`** - For Python packages published to PyPI
- **`go/`** - For Go modules and packages

### Step 2: Create Your YAML Configuration

Create a new `.yaml` file in the appropriate directory with this structure:

```yaml
# Comments are encouraged! Describe what your MCP server does
# Package URL: https://...
# Repository: https://...
# Will build as: ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}

metadata:
  name: your-server-name           # Required: Unique server name
  description: "Brief description" # Optional: What does your server do?
  version: "1.0.0"                # Optional: Server version
  protocol: npx                   # Required: npx, uvx, or go

spec:
  package: "your-package-name"    # Required: Package name from registry
  version: "1.0.0"               # Required: Specific version to build

provenance:                       # Optional but recommended
  repository_uri: "https://github.com/user/repo"  # Source repository
  repository_ref: "refs/tags/v1.0.0"              # Git tag/branch/commit
```

### Step 3: Protocol-Specific Examples

#### NPX (Node.js) Example
```yaml
# NPM package: https://www.npmjs.com/package/@your-org/mcp-server
metadata:
  name: my-node-server
  description: "My awesome Node.js MCP server"
  version: "2.1.0"
  protocol: npx

spec:
  package: "@your-org/mcp-server"  # NPM package name
  version: "2.1.0"

provenance:
  repository_uri: "https://github.com/your-org/mcp-server"
  repository_ref: "refs/tags/v2.1.0"
```

#### UVX (Python) Example
```yaml
# PyPI package: https://pypi.org/project/your-mcp-server/
metadata:
  name: my-python-server
  description: "My awesome Python MCP server"
  version: "1.5.2"
  protocol: uvx

spec:
  package: "your-mcp-server"      # PyPI package name
  version: "1.5.2"

provenance:
  repository_uri: "https://github.com/your-org/python-mcp-server"
  repository_ref: "refs/tags/v1.5.2"
```

#### Go Example
```yaml
# Go module: go get github.com/your-org/go-mcp-server
metadata:
  name: my-go-server
  description: "My awesome Go MCP server"
  version: "0.3.1"
  protocol: go

spec:
  package: "github.com/your-org/go-mcp-server"  # Go module path
  version: "v0.3.1"                            # Go version tag

provenance:
  repository_uri: "https://github.com/your-org/go-mcp-server"
  repository_ref: "refs/tags/v0.3.1"
```

### Step 4: Submit Your Pull Request

1. Fork this repository
2. Create your YAML file in the appropriate directory
3. Submit a pull request with:
   - Clear title: "Add [Your Server Name] MCP server"
   - Description of what your server does
   - Link to the package registry and source repository

### Step 5: Automated Building

Once your PR is merged:
- 🤖 GitHub Actions automatically detects your new configuration
- 🏗️ Builds a container image using ToolHive
- 📦 Publishes to `ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}`
- 🔄 Renovate keeps your package version up-to-date automatically

## 🏗️ How It Works

1. **Detection**: GitHub Actions detects changes to YAML files
2. **Validation**: Validates YAML structure and required fields
3. **Protocol Scheme**: Constructs protocol scheme (e.g., `npx://@upstash/context7-mcp@1.0.14`)
4. **Container Build**: Uses ToolHive's `BuildFromProtocolSchemeWithName` function
5. **Publishing**: Pushes to GitHub Container Registry with automatic tagging
6. **Updates**: Renovate automatically creates PRs for new package versions

## 📋 Container Image Naming

All containers follow this naming pattern:
```
ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}
```

Examples:
- `ghcr.io/stacklok/dockyard/npx/context7:1.0.14`
- `ghcr.io/stacklok/dockyard/uvx/aws-documentation-mcp-server:1.1.2`
- `ghcr.io/stacklok/dockyard/go/my-mcp-server:latest`

## 🛠️ Local Development

### Prerequisites
- Go 1.21+
- Docker or Podman
- ToolHive library

### Build a container locally:

```bash
go run main.go -config npx/context7.yaml
```

### Build with custom tag:

```bash
go run main.go -config npx/context7.yaml -tag my-custom-tag:latest
```

## 🏗️ Project Structure

```
dockyard/
├── main.go                    # Main application
├── go.mod                     # Go module definition
├── renovate.json              # Renovate configuration for auto-updates
├── .github/workflows/         # CI/CD pipeline
│   └── build-containers.yml   # Automated container building
├── npx/                       # Node.js (NPX) configurations
│   └── *.yaml                # YAML files for npm packages
├── uvx/                       # Python (UVX) configurations
│   └── *.yaml                # YAML files for PyPI packages
└── go/                        # Go configurations
    └── *.yaml                # YAML files for Go modules
```

## 🔧 Dependencies

- **[ToolHive](https://github.com/stacklok/toolhive)** - Container building from protocol schemes
- **[gopkg.in/yaml.v3](https://gopkg.in/yaml.v3)** - YAML configuration parsing
- **[Renovate](https://renovatebot.com/)** - Automated dependency updates