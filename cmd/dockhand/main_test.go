package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/stacklok/toolhive/pkg/container/images"
	"github.com/stacklok/toolhive/pkg/container/templates"
	"github.com/stacklok/toolhive/pkg/runner"
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

// The tests above inject into hand-written Dockerfiles that mirror toolhive's templates.
// Those keep passing even if toolhive's real output drifts away from what the injection
// anchors expect, so the tests below run the injection against Dockerfiles generated by
// the toolhive version this module actually pins. A template change that breaks an anchor
// fails here instead of silently shipping an un-overridden image.
//
// These use dryRun=true, which returns the rendered template without touching a container
// runtime, so they need no Docker daemon.
func generateRealDockerfile(t *testing.T, scheme string, rc *templates.RuntimeConfig) string {
	t.Helper()
	ctx := context.Background()
	dockerfile, err := runner.BuildFromProtocolSchemeWithName(
		ctx, images.NewImageManager(ctx), scheme, "", "test:latest", nil, rc, true,
	)
	if err != nil {
		t.Fatalf("failed to generate Dockerfile for %s: %v", scheme, err)
	}
	return dockerfile
}

func TestInjectNpmOverrides_AgainstRealTemplate(t *testing.T) {
	t.Parallel()
	dockerfile := generateRealDockerfile(t, "npx://@brightdata/mcp@2.9.5", nil)

	out, err := injectNpmOverrides(dockerfile, []OverrideEntry{
		{Package: "@modelcontextprotocol/sdk", Version: "1.26.0", Reason: "CVE fix"},
	})
	if err != nil {
		t.Fatalf("injection failed against the real toolhive npx template: %v", err)
	}

	// The rewritten payload must be valid JSON carrying the override, and must preserve the
	// fields toolhive emitted rather than replacing them with our own values.
	payload := extractPackageJSONPayload(t, out)
	var pkg map[string]any
	if err := json.Unmarshal([]byte(payload), &pkg); err != nil {
		t.Fatalf("rewritten package.json is not valid JSON (%q): %v", payload, err)
	}
	overrides, ok := pkg["overrides"].(map[string]any)
	if !ok {
		t.Fatalf("expected an overrides block in the rewritten package.json, got %q", payload)
	}
	if overrides["@modelcontextprotocol/sdk"] != "1.26.0" {
		t.Errorf("expected the SDK override to be 1.26.0, got %v", overrides["@modelcontextprotocol/sdk"])
	}

	// Whatever toolhive put in the original payload must still be there.
	origPayload := extractPackageJSONPayload(t, dockerfile)
	var orig map[string]any
	if err := json.Unmarshal([]byte(origPayload), &orig); err != nil {
		t.Fatalf("could not parse the original package.json payload %q: %v", origPayload, err)
	}
	for k, v := range orig {
		if pkg[k] != v {
			t.Errorf("field %q from toolhive's package.json was lost or changed: got %v, want %v", k, pkg[k], v)
		}
	}
}

// extractPackageJSONPayload pulls the single-quoted JSON out of the
// "RUN echo '{...}' > package.json" step of a Dockerfile.
func extractPackageJSONPayload(t *testing.T, dockerfile string) string {
	t.Helper()
	for _, line := range strings.Split(dockerfile, "\n") {
		trimmed := strings.TrimSpace(line)
		if !strings.HasPrefix(trimmed, "RUN echo '") || !strings.Contains(trimmed, "> package.json") {
			continue
		}
		start := len("RUN echo '")
		end := strings.LastIndex(trimmed, "'")
		if end <= start {
			t.Fatalf("could not extract the package.json payload from %q", trimmed)
		}
		return trimmed[start:end]
	}
	t.Fatalf("no package.json creation step found in the generated Dockerfile")
	return ""
}

func TestInjectUvOverrides_AgainstRealTemplate(t *testing.T) {
	t.Parallel()
	// The uvx template conditionally emits its own flags between "uv tool install" and the
	// quoted package spec (RuntimeConfig.BuildWith renders as "--with '<spec>'"). Both the
	// plain and the flag-carrying form must still be found and rewritten.
	for _, tc := range []struct {
		name string
		rc   *templates.RuntimeConfig
	}{
		{"plain", nil},
		{"with build-time constraints", &templates.RuntimeConfig{BuildWith: []string{"mcp<2"}}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			dockerfile := generateRealDockerfile(t, "uvx://mcp-clickhouse@0.3.0", tc.rc)

			out, err := injectUvOverrides(dockerfile, []ConstraintEntry{
				{Spec: testFastmcpSpec, Reason: "CVE fix excluded by upstream cap"},
			})
			if err != nil {
				t.Fatalf("injection failed against the real toolhive uvx template: %v", err)
			}

			if !strings.Contains(out, "uv tool install --overrides /tmp/uv-overrides.txt") {
				t.Errorf("expected --overrides on the install step, got:\n%s", out)
			}
			if !strings.Contains(out, testFastmcpSpec) {
				t.Errorf("expected the constraint spec in the overrides file step, got:\n%s", out)
			}

			writeIdx := strings.Index(out, "> /tmp/uv-overrides.txt")
			installIdx := strings.Index(out, "uv tool install --overrides")
			if writeIdx == -1 || installIdx == -1 {
				t.Fatalf("expected both the overrides-file write and the install step")
			}
			if writeIdx > installIdx {
				t.Error("overrides file must be written before uv tool install runs")
			}

			// Exactly one real (non-comment) install command must exist, and it must be the
			// rewritten one -- so the step is neither duplicated nor left partially rewritten.
			// The template also mentions "uv tool install" in comments, which injection skips.
			var installCmds []string
			for _, line := range strings.Split(out, "\n") {
				trimmed := strings.TrimSpace(line)
				if strings.HasPrefix(trimmed, "#") {
					continue
				}
				if strings.Contains(line, "uv tool install ") {
					installCmds = append(installCmds, trimmed)
				}
			}
			if len(installCmds) != 1 {
				t.Fatalf("expected exactly one non-comment 'uv tool install' command, got %d: %q", len(installCmds), installCmds)
			}
			if !strings.Contains(installCmds[0], "--overrides /tmp/uv-overrides.txt") {
				t.Errorf("the install command was not rewritten with --overrides: %q", installCmds[0])
			}
		})
	}
}
