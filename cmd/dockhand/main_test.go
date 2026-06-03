package main

import (
	"strings"
	"testing"
)

const (
	testOverrideVersion = "1.0.0"
	testFastmcpSpec     = "fastmcp>=3.2.0"
)

// sampleNpxDockerfile mirrors the package.json + npm install steps that toolhive's
// BuildFromProtocolSchemeWithName emits for an npx package.
const sampleNpxDockerfile = `FROM node:24-alpine AS builder
WORKDIR /build

# Create a package.json to install the MCP package
RUN echo '{"name":"mcp-container","version":"1.0.0"}' > package.json

# Install the MCP package and its dependencies at build time
RUN npm install --save @brightdata/mcp@2.9.5

ENTRYPOINT ["npx", "@brightdata/mcp"]
`

// sampleUvxDockerfile mirrors the "uv tool install" step that toolhive emits for a uvx package.
const sampleUvxDockerfile = `FROM python:3.14-slim AS builder
WORKDIR /build

ENV UV_TOOL_DIR=/opt/uv-tools \
    UV_TOOL_BIN_DIR=/opt/uv-tools/bin
# Convert @ version separator to == for Python package specification
RUN package="mcp-clickhouse@0.3.0"; \
    package_spec=$(echo "$package" | sed 's/@/==/'); \
    uv tool install "$package_spec" && \
    ls -la /opt/uv-tools/bin/

ENTRYPOINT ["sh", "-c", "exec 'mcp-clickhouse' \"$@\"", "--"]
`

func TestInjectNpmOverrides(t *testing.T) {
	t.Parallel()
	overrides := []OverrideEntry{
		{Package: "@modelcontextprotocol/sdk", Version: "1.26.0", Reason: "CVE fix; upstream hard-pins 1.21.2"},
	}

	out, err := injectNpmOverrides(sampleNpxDockerfile, overrides)
	if err != nil {
		t.Fatalf("injectNpmOverrides returned error: %v", err)
	}

	// The package.json line must now carry an overrides block with the pinned version.
	if !strings.Contains(out, `"overrides":`) {
		t.Errorf("expected an overrides block in the generated package.json, got:\n%s", out)
	}
	if !strings.Contains(out, `"@modelcontextprotocol/sdk":"1.26.0"`) {
		t.Errorf("expected the pinned SDK override in the package.json, got:\n%s", out)
	}

	// The override must appear on the package.json line, which must precede the npm install.
	pkgIdx := strings.Index(out, "> package.json")
	installIdx := strings.Index(out, "npm install --save")
	if pkgIdx == -1 || installIdx == -1 {
		t.Fatalf("expected both the package.json step and the npm install step to be present")
	}
	if pkgIdx > installIdx {
		t.Errorf("package.json (with overrides) must be created before npm install")
	}

	// The npm install line must be left intact.
	if !strings.Contains(out, "RUN npm install --save @brightdata/mcp@2.9.5") {
		t.Errorf("npm install line should be unchanged, got:\n%s", out)
	}
}

func TestInjectUvOverrides(t *testing.T) {
	t.Parallel()
	constraints := []ConstraintEntry{
		{Spec: testFastmcpSpec, Reason: "CRITICAL CVE-2026-32871 fix; upstream caps <3.0.0"},
	}

	out, err := injectUvOverrides(sampleUvxDockerfile, constraints)
	if err != nil {
		t.Fatalf("injectUvOverrides returned error: %v", err)
	}

	// The install step must now use the overrides file.
	if !strings.Contains(out, "uv tool install --overrides /tmp/uv-overrides.txt") {
		t.Errorf("expected --overrides flag on the uv tool install step, got:\n%s", out)
	}

	// The overrides file must be written with the constraint spec.
	if !strings.Contains(out, "'fastmcp>=3.2.0'") {
		t.Errorf("expected the constraint spec to be written to the overrides file, got:\n%s", out)
	}
	if !strings.Contains(out, "> /tmp/uv-overrides.txt") {
		t.Errorf("expected the overrides file to be written, got:\n%s", out)
	}

	// The file-writing step must precede the install step.
	writeIdx := strings.Index(out, "> /tmp/uv-overrides.txt")
	installIdx := strings.Index(out, "uv tool install --overrides")
	if writeIdx == -1 || installIdx == -1 {
		t.Fatalf("expected both the overrides-file write and the install step")
	}
	if writeIdx > installIdx {
		t.Errorf("overrides file must be written before uv tool install runs")
	}
}

func TestInjectDependencyOverrides_NoOp(t *testing.T) {
	t.Parallel()
	// npx spec with no overrides should pass the Dockerfile through unchanged.
	spec := &MCPServerSpec{
		Metadata: MCPServerMetadata{Protocol: protocolNpx},
	}
	out, err := injectDependencyOverrides(sampleNpxDockerfile, spec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out != sampleNpxDockerfile {
		t.Errorf("expected Dockerfile to be unchanged when no overrides are set")
	}

	// go protocol should also be a no-op even if (invalidly) overrides were present.
	goSpec := &MCPServerSpec{Metadata: MCPServerMetadata{Protocol: protocolGo}}
	out, err = injectDependencyOverrides("FROM golang:1.23\n", goSpec)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out != "FROM golang:1.23\n" {
		t.Errorf("expected go Dockerfile to be unchanged")
	}
}

func TestValidateDependencyOverrides(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		spec    MCPServerSpec
		wantErr bool
	}{
		{
			name: "valid npx override",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolNpx},
				Spec: MCPServerPackageSpec{
					Overrides: []OverrideEntry{{Package: "p", Version: testOverrideVersion, Reason: "because"}},
				},
			},
			wantErr: false,
		},
		{
			name: "npx override missing reason",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolNpx},
				Spec: MCPServerPackageSpec{
					Overrides: []OverrideEntry{{Package: "p", Version: testOverrideVersion}},
				},
			},
			wantErr: true,
		},
		{
			name: "npx override missing version",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolNpx},
				Spec: MCPServerPackageSpec{
					Overrides: []OverrideEntry{{Package: "p", Reason: "because"}},
				},
			},
			wantErr: true,
		},
		{
			name: "valid uvx constraint",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolUvx},
				Spec: MCPServerPackageSpec{
					Constraints: []ConstraintEntry{{Spec: testFastmcpSpec, Reason: "cve"}},
				},
			},
			wantErr: false,
		},
		{
			name: "uvx constraint missing reason",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolUvx},
				Spec: MCPServerPackageSpec{
					Constraints: []ConstraintEntry{{Spec: testFastmcpSpec}},
				},
			},
			wantErr: true,
		},
		{
			name: "overrides on uvx protocol rejected",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolUvx},
				Spec: MCPServerPackageSpec{
					Overrides: []OverrideEntry{{Package: "p", Version: testOverrideVersion, Reason: "x"}},
				},
			},
			wantErr: true,
		},
		{
			name: "constraints on npx protocol rejected",
			spec: MCPServerSpec{
				Metadata: MCPServerMetadata{Protocol: protocolNpx},
				Spec: MCPServerPackageSpec{
					Constraints: []ConstraintEntry{{Spec: "x>=1", Reason: "x"}},
				},
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			err := validateDependencyOverrides(&tt.spec)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateDependencyOverrides() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}
