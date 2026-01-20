# Contributing to Dockyard

Thank you for your interest in contributing to Dockyard! This document helps you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Reporting Security Vulnerabilities](#reporting-security-vulnerabilities)
- [Ways to Contribute](#ways-to-contribute)
- [Adding an MCP Server](#adding-an-mcp-server)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Commit Message Guidelines](#commit-message-guidelines)

## Code of Conduct

This project adheres to the [Contributor Covenant](CODE_OF_CONDUCT.md) code of conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to [code-of-conduct@stacklok.dev](mailto:code-of-conduct@stacklok.dev).

## Reporting Security Vulnerabilities

If you think you have found a security vulnerability in Dockyard, please **DO NOT** disclose it publicly until we've had a chance to fix it. Please don't report security vulnerabilities using GitHub issues; instead, follow the process in [SECURITY.MD](SECURITY.MD).

## Ways to Contribute

### Add an MCP Server

The most common contribution is adding a new MCP server to Dockyard. See [Adding an MCP Server](#adding-an-mcp-server) below.

### Report Bugs

Use [GitHub Issues](https://github.com/stacklok/dockyard/issues) to report bugs. Please include:
- Steps to reproduce the issue
- Expected vs actual behavior
- Container image name and version (if applicable)

### Suggest Enhancements

We welcome feature suggestions! Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

### Improve Documentation

Documentation improvements are always welcome. See the [docs/](docs/) directory.

## Adding an MCP Server

To add your MCP server to Dockyard:

1. Create a directory: `{protocol}/{server-name}/`
2. Add a `spec.yaml` configuration file
3. Submit a pull request

**Full guide:** [Adding MCP Servers](docs/adding-servers.md)

**Quick example:**

```yaml
metadata:
  name: my-server
  description: "What my server does"
  protocol: npx

spec:
  package: "@my-org/mcp-server"
  version: "1.0.0"
```

## Development Setup

### Prerequisites

- Go 1.21+
- Docker or Podman
- [Task](https://taskfile.dev/) (optional, for convenience)

### Build the CLI

```bash
go build -o build/dockhand ./cmd/dockhand
```

### Run Tests

```bash
go test ./...
```

### Generate a Dockerfile

```bash
./build/dockhand build -c npx/context7/spec.yaml
```

### Verify Provenance

```bash
./build/dockhand verify-provenance -c npx/context7/spec.yaml -v
```

## Pull Request Process

1. **Fork and clone** the repository
2. **Create a branch** for your changes
3. **Make your changes** with clear, focused commits
4. **Test locally** if adding an MCP server:
   ```bash
   task build -- {protocol}/{server-name}
   task scan -- {protocol}/{server-name}
   ```
5. **Submit a PR** with a clear description

### PR Requirements

- All commits must include a Signed-off-by trailer (DCO)
- CI checks must pass (security scan, build, etc.)
- One approval from a maintainer is required

### For MCP Server PRs

Include in your PR description:
- What the MCP server does
- Link to the package registry (npm/PyPI)
- Link to the source repository

## Commit Message Guidelines

Follow [Chris Beams' guidelines](https://chris.beams.io/posts/git-commit/):

1. Separate subject from body with a blank line
2. Limit the subject line to 50 characters
3. Capitalize the subject line
4. Do not end the subject line with a period
5. Use the imperative mood in the subject line
6. Use the body to explain what and why vs. how

**Example:**

```
Add context7 MCP server

Add packaging for context7 v1.0.14 from Upstash.
This server provides vector search and context management.

Package: https://www.npmjs.com/package/@upstash/context7-mcp
Repository: https://github.com/upstash/context7-mcp

Signed-off-by: Your Name <your.email@example.com>
```

## Questions?

- Open a [GitHub Discussion](https://github.com/stacklok/dockyard/discussions)
- Join the [Stacklok Discord](https://discord.gg/stacklok)
