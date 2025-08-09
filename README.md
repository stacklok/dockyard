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

### Step 2: Create Your MCP Server Directory and Configuration

Create a new directory for your MCP server in the appropriate protocol folder, then add a `spec.yaml` file:

```bash
# Create directory structure
mkdir -p {protocol}/{your-server-name}

# Create spec.yaml file
```

The `spec.yaml` file should have this structure:

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

Directory structure:
```
npx/
└── my-node-server/
    └── spec.yaml
```

Content of `npx/my-node-server/spec.yaml`:
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

Directory structure:
```
uvx/
└── my-python-server/
    └── spec.yaml
```

Content of `uvx/my-python-server/spec.yaml`:
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

Directory structure:
```
go/
└── my-go-server/
    └── spec.yaml
```

Content of `go/my-go-server/spec.yaml`:
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
2. Create your server directory and `spec.yaml` file in the appropriate protocol directory
3. Submit a pull request with:
   - Clear title: "Add [Your Server Name] MCP server"
   - Description of what your server does
   - Link to the package registry and source repository

**Note**: Your MCP server will be automatically scanned for security vulnerabilities. The PR will only be mergeable if the security scan passes.

### Step 5: Automated Building

Once your PR passes security scanning and is merged:
- ✅ Security scan ensures no vulnerabilities
- 🤖 GitHub Actions automatically detects your new configuration
- 🏗️ Builds a container image using ToolHive
- 📦 Publishes to `ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}`
- 🔄 Renovate keeps your package version up-to-date automatically

## 🔒 Security Scanning

Dockyard automatically scans all MCP servers for security vulnerabilities before building containers using [mcp-scan](https://github.com/invariantlabs-ai/mcp-scan) from Invariant Labs. This ensures that only secure MCP servers are deployed.

### What We Scan For

- **Prompt Injection Risks**: Detects dangerous words or patterns in tool descriptions that could be exploited
- **Toxic Flows**: Identifies combinations of tools that could lead to destructive behaviors
- **Tool Poisoning**: Checks for malicious tool implementations
- **Cross-Origin Escalation**: Detects potential privilege escalation vulnerabilities
- **Rug Pull Attacks**: Identifies suspicious patterns that could indicate malicious intent

### Security Requirements

All MCP servers must pass security scanning before being merged. If vulnerabilities are detected:
- The CI pipeline will fail
- A detailed report will be posted as a PR comment
- The vulnerabilities must be addressed before the PR can be merged

### Security Report Example

When vulnerabilities are found, you'll see a detailed report in your PR:

```
## 🔒 MCP Security Scan Results

### ❌ your-mcp-server
- **Status**: Failed
- **Tools scanned**: 3
- **Vulnerabilities found**: 2

**Security issues detected:**
- **[W001]** Tool description contains dangerous words that could be used for prompt injection
- **[TF002]** Destructive toxic flow detected
```

## 🏗️ How It Works

1. **Detection**: GitHub Actions detects changes to YAML files
2. **Security Scan**: Runs mcp-scan to check for vulnerabilities
3. **Validation**: Validates YAML structure and required fields
4. **Protocol Scheme**: Constructs protocol scheme (e.g., `npx://@upstash/context7-mcp@1.0.14`)
5. **Container Build**: Uses ToolHive's `BuildFromProtocolSchemeWithName` function (only if security scan passes)
6. **Publishing**: Pushes to GitHub Container Registry with automatic tagging
7. **Updates**: Renovate automatically creates PRs for new package versions

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
go run main.go -config npx/context7/spec.yaml
```

### Build with custom tag:

```bash
go run main.go -config npx/context7/spec.yaml -tag my-custom-tag:latest
```

## 🏗️ Project Structure

```
dockyard/
├── main.go                    # Main application
├── go.mod                     # Go module definition
├── renovate.json              # Renovate configuration for auto-updates
├── .github/workflows/         # CI/CD pipeline
│   └── build-containers.yml   # Automated container building with security scanning
├── scripts/                   # Utility scripts
│   └── mcp-scan/             # MCP security scanning tools
│       ├── generate_mcp_config.py    # Converts YAML to MCP config format
│       ├── process_scan_results.py   # Processes scan results
│       └── README.md                  # Scanning documentation
├── npx/                       # Node.js (NPX) configurations
│   └── {server-name}/        # Each server in its own directory
│       └── spec.yaml         # Server specification
├── uvx/                       # Python (UVX) configurations
│   └── {server-name}/        # Each server in its own directory
│       └── spec.yaml         # Server specification
└── go/                        # Go configurations
    └── {server-name}/        # Each server in its own directory
        └── spec.yaml         # Server specification
```

## 🔧 Dependencies

- **[ToolHive](https://github.com/stacklok/toolhive)** - Container building from protocol schemes
- **[gopkg.in/yaml.v3](https://gopkg.in/yaml.v3)** - YAML configuration parsing
- **[Renovate](https://renovatebot.com/)** - Automated dependency updates
- **[mcp-scan](https://github.com/invariantlabs-ai/mcp-scan)** - Security vulnerability scanning for MCP servers