# Dockyard - MCP Server Container Builder

Dockyard is a tool for packaging Model Context Protocol (MCP) servers that are not currently containerized. It uses [ToolHive](https://docs.stacklok.com/toolhive) to build containers from protocol schemes.

## Overview

This tool reads YAML configuration files that describe MCP servers and builds container images using ToolHive's build capabilities. It supports the following protocols:

- `npx://` - Node.js packages from npm
- `uvx://` - Python packages using uv package manager  
- `go://` - Go packages

## Project Structure

```
dockyard/
├── main.go              # Main application
├── go.mod              # Go module definition
├── npx/                # NPX protocol configurations
│   └── *.yaml         # YAML files for npm packages
├── uvx/                # UVX protocol configurations  
│   └── *.yaml         # YAML files for Python packages
└── go/                 # Go protocol configurations
    └── *.yaml         # YAML files for Go packages
```

## YAML Configuration Format

Each YAML file describes an MCP server package with the following structure:

```yaml
metadata:
  name: server-name           # Required: Server name
  description: "Description"  # Optional: Server description
  version: "1.0.0"           # Optional: Version
  protocol: npx              # Required: Protocol (npx, uvx, go)

spec:
  package: "package-name"     # Required: Package name/reference
  version: "1.0.0"           # Optional: Package version

provenance:                   # Optional: Supply chain information
  repository_uri: "https://..." # Package source repository URI
  repository_ref: "refs/tags/v1.0.0" # Git reference (tag, branch, or commit)
```

## Usage

Build a container from a YAML configuration:

```bash
go run main.go -config npx/context7.yaml
```

Build with a custom container tag:

```bash
go run main.go -config npx/context7.yaml -tag ghcr.io/stacklok/dockyard/npx/context7:1.0.14
```

## Container Image Naming

By default, container images are tagged using the pattern:
```
ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}
```

For example:
- `ghcr.io/stacklok/dockyard/npx/context7:1.0.14`
- `ghcr.io/stacklok/dockyard/uvx/mcp-server-git:0.5.0`
- `ghcr.io/stacklok/dockyard/go/my-mcp-server:latest`

## How It Works

1. Reads the YAML configuration file
2. Validates the configuration structure and required fields
3. Constructs a protocol scheme (e.g., `npx://@upstash/context7-mcp@1.0.14`)
4. Uses ToolHive's `BuildFromProtocolSchemeWithName` function to build the container
5. Generates an appropriate container image tag
6. Returns the built container image name

## Dependencies

- [ToolHive](https://github.com/stacklok/toolhive) - For container building capabilities
- [gopkg.in/yaml.v3](https://gopkg.in/yaml.v3) - For YAML parsing

## Example

The `npx/context7.yaml` file demonstrates packaging the Upstash Context7 MCP server:

```yaml
metadata:
  name: context7
  description: "Upstash Context7 MCP server for vector search and context management"
  version: "1.0.14"
  protocol: npx

spec:
  package: "@upstash/context7-mcp"
  version: "1.0.14"

provenance:
  repository_uri: "https://github.com/upstash/context7-mcp"
  repository_ref: "refs/tags/v1.0.14"
```

This would build a container tagged as `ghcr.io/stacklok/dockyard/npx/context7:1.0.14`.