// Package main implements the Dockyard CLI tool for containerizing MCP servers.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"github.com/stacklok/toolhive-core/logging"
	"github.com/stacklok/toolhive/pkg/container/images"
	"github.com/stacklok/toolhive/pkg/runner"
	"gopkg.in/yaml.v3"

	"github.com/stacklok/dockyard/internal/provenance/domain"
	"github.com/stacklok/dockyard/internal/provenance/npm"
	"github.com/stacklok/dockyard/internal/provenance/pypi"
	"github.com/stacklok/dockyard/internal/provenance/service"
	skillpkg "github.com/stacklok/dockyard/internal/skills"
)

// Supported package protocols.
const (
	protocolNpx = "npx"
	protocolUvx = "uvx"
	protocolGo  = "go"

	// mcpContainerVersion is the placeholder version toolhive's npx template stamps into
	// the generated package.json; we reuse it when re-emitting that file with overrides.
	mcpContainerVersion = "1.0.0"
)

// MCPServerSpec defines the structure of our YAML configuration files
type MCPServerSpec struct {
	// Metadata about the MCP server
	Metadata MCPServerMetadata `yaml:"metadata"`
	// Spec defines the package and build configuration
	Spec MCPServerPackageSpec `yaml:"spec"`
	// Provenance information for supply chain security
	Provenance MCPServerProvenance `yaml:"provenance,omitempty"`
}

// MCPServerMetadata contains basic information about the MCP server
type MCPServerMetadata struct {
	Name        string `yaml:"name"`
	Description string `yaml:"description,omitempty"`
	Protocol    string `yaml:"protocol"` // npx, uvx, go
}

// MCPServerPackageSpec defines the package to be containerized
type MCPServerPackageSpec struct {
	Package string   `yaml:"package"`           // e.g., "@upstash/context7-mcp"
	Version string   `yaml:"version,omitempty"` // e.g., "1.0.14"
	Args    []string `yaml:"args,omitempty"`    // Additional arguments for the package

	// Overrides forces specific versions of transitive npm dependencies (npx protocol).
	// Each entry is injected into an "overrides" block of the generated package.json so
	// that npm resolves the pinned version regardless of upstream's declared range.
	Overrides []OverrideEntry `yaml:"overrides,omitempty"`

	// Constraints forces specific versions of transitive Python dependencies (uvx protocol).
	// Each entry is written to a uv overrides requirements file and passed to
	// "uv tool install --overrides" so that uv resolves the pinned version even when
	// upstream caps the dependency.
	Constraints []ConstraintEntry `yaml:"constraints,omitempty"`
}

// OverrideEntry pins a transitive npm dependency to a specific version (npx protocol).
// Reason is mandatory so the justification for circumventing the upstream pin is auditable
// in-repo, mirroring security.allowed_issues.
type OverrideEntry struct {
	Package string `yaml:"package"` // e.g., "@modelcontextprotocol/sdk"
	Version string `yaml:"version"` // e.g., "1.26.0"
	Reason  string `yaml:"reason"`  // why this override is needed (required)
}

// ConstraintEntry pins a transitive Python dependency via a uv override requirement
// (uvx protocol). Reason is mandatory so the justification is auditable in-repo.
type ConstraintEntry struct {
	Spec   string `yaml:"spec"`   // a PEP 508 requirement, e.g., "fastmcp>=3.2.0"
	Reason string `yaml:"reason"` // why this constraint is needed (required)
}

// MCPServerProvenance contains supply chain provenance information
type MCPServerProvenance struct {
	// Expected source repository for verification
	RepositoryURI string `yaml:"repository_uri,omitempty"`
	RepositoryRef string `yaml:"repository_ref,omitempty"`

	// Attestation information
	Attestations *AttestationInfo `yaml:"attestations,omitempty"`

	// Legacy fields (kept for backwards compatibility)
	SigstoreURL       string `yaml:"sigstore_url,omitempty"`
	SignerIdentity    string `yaml:"signer_identity,omitempty"`
	RunnerEnvironment string `yaml:"runner_environment,omitempty"`
	CertIssuer        string `yaml:"cert_issuer,omitempty"`
}

// AttestationInfo contains information about package attestations
type AttestationInfo struct {
	Available bool           `yaml:"available"`
	Publisher *PublisherInfo `yaml:"publisher,omitempty"`
	Verified  bool           `yaml:"verified,omitempty"`
}

// PublisherInfo contains trusted publisher information
type PublisherInfo struct {
	Kind       string `yaml:"kind"`       // e.g., "GitHub", "GitLab"
	Repository string `yaml:"repository"` // e.g., "owner/repo"
	Workflow   string `yaml:"workflow,omitempty"`
}

var (
	// Global flags
	verbose bool

	// Build command flags
	configFile string
	outputTag  string
	output     string

	// Verify command flags
	checkProvenance    bool
	warnOnNoProvenance bool
)

func main() {
	// Initialize the logger
	slog.SetDefault(logging.New(logging.WithFormat(logging.FormatText)))

	rootCmd := &cobra.Command{
		Use:   "dockhand",
		Short: "A tool for containerizing MCP servers",
		Long: `Dockhand is a CLI tool that reads YAML configuration files and uses ToolHive 
to build container images from protocol schemes (npx://, uvx://, go://).

It simplifies the process of packaging MCP (Model Context Protocol) servers 
into container images for easy deployment and distribution.`,
		Version: "0.1.0",
	}

	// Add global flags
	rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "Enable verbose output")

	// Add build command
	buildCmd := &cobra.Command{
		Use:   "build",
		Short: "Build a container image from an MCP server specification",
		Long: `Build reads a YAML configuration file that describes an MCP server
and generates a Dockerfile or builds a container image using ToolHive.

The configuration file should follow the structure:
  {protocol}/{name}/spec.yaml

Where protocol is one of: npx, uvx, or go`,
		Example: `  # Generate a Dockerfile to stdout
  dockhand build -c npx/context7/spec.yaml

  # Generate a Dockerfile and save to file
  dockhand build -c npx/context7/spec.yaml -o Dockerfile

  # Generate with custom tag
  dockhand build -c npx/context7/spec.yaml -t myregistry/myimage:v1.0.0`,
		RunE: runBuild,
	}

	// Add build command flags
	buildCmd.Flags().StringVarP(&configFile, "config", "c", "", "Path to the YAML configuration file (required)")
	buildCmd.Flags().StringVarP(&outputTag, "tag", "t", "", "Custom container image tag (optional)")
	buildCmd.Flags().StringVarP(&output, "output", "o", "", "Output file for Dockerfile (optional, defaults to stdout)")
	buildCmd.Flags().BoolVar(&checkProvenance, "check-provenance", false, "Check package provenance before building")
	buildCmd.Flags().BoolVar(&warnOnNoProvenance, "warn-no-provenance", true, "Warn if provenance is not available (default: true)")
	if err := buildCmd.MarkFlagRequired("config"); err != nil {
		// This should never fail for a valid flag name
		panic(fmt.Sprintf("failed to mark config flag as required: %v", err))
	}

	// Add verify-provenance command
	verifyCmd := &cobra.Command{
		Use:   "verify-provenance",
		Short: "Verify provenance for an MCP server package",
		Long: `Verify checks if a package has provenance attestations or signatures
available from the package registry. This helps ensure supply chain security
by verifying the authenticity and origin of the package.`,
		Example: `  # Verify provenance for a package
  dockhand verify-provenance -c npx/context7/spec.yaml

  # Verify with verbose output
  dockhand verify-provenance -c uvx/mcp-clickhouse/spec.yaml -v`,
		RunE: runVerifyProvenance,
	}

	verifyCmd.Flags().StringVarP(&configFile, "config", "c", "", "Path to the YAML configuration file (required)")
	if err := verifyCmd.MarkFlagRequired("config"); err != nil {
		panic(fmt.Sprintf("failed to mark config flag as required: %v", err))
	}

	// Add build-skill command
	var skillConfigFile string
	var skillTag string
	var skillPush bool

	buildSkillCmd := &cobra.Command{
		Use:   "build-skill",
		Short: "Build an OCI skill artifact from a skill specification",
		Long: `Build-skill reads a skill spec.yaml that references a skill in a git repository,
clones the repo, validates the SKILL.md, and packages it as an OCI skill artifact.

The configuration file should follow the structure:
  skills/{name}/spec.yaml`,
		Example: `  # Build a skill artifact (dry run, no push)
  dockhand build-skill -c skills/my-skill/spec.yaml

  # Build and push to GHCR
  dockhand build-skill -c skills/my-skill/spec.yaml --push

  # Build with custom OCI tag
  dockhand build-skill -c skills/my-skill/spec.yaml -t ghcr.io/myorg/skills/my-skill:v1.0.0`,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return runBuildSkill(cmd, skillConfigFile, skillTag, skillPush)
		},
	}

	buildSkillCmd.Flags().StringVarP(&skillConfigFile, "config", "c", "", "Path to the skill spec.yaml file (required)")
	buildSkillCmd.Flags().StringVarP(&skillTag, "tag", "t", "", "Custom OCI artifact tag (optional)")
	buildSkillCmd.Flags().BoolVar(&skillPush, "push", false, "Push the artifact to the registry")
	if err := buildSkillCmd.MarkFlagRequired("config"); err != nil {
		panic(fmt.Sprintf("failed to mark config flag as required: %v", err))
	}

	// Add validate-skill command
	var validateSkillConfigFile string

	validateSkillCmd := &cobra.Command{
		Use:   "validate-skill",
		Short: "Validate a skill from a git repository",
		Long: `Validate-skill reads a skill spec.yaml, clones the referenced git repository,
and validates the SKILL.md without packaging. Useful for PR checks.`,
		Example: `  # Validate a skill spec
  dockhand validate-skill -c skills/my-skill/spec.yaml`,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return runValidateSkill(cmd, validateSkillConfigFile)
		},
	}

	validateSkillCmd.Flags().StringVarP(&validateSkillConfigFile, "config", "c", "", "Path to the skill spec.yaml file (required)")
	if err := validateSkillCmd.MarkFlagRequired("config"); err != nil {
		panic(fmt.Sprintf("failed to mark config flag as required: %v", err))
	}

	// Add commands to root
	rootCmd.AddCommand(buildCmd, verifyCmd, buildSkillCmd, validateSkillCmd)

	// Execute
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func runBuild(cmd *cobra.Command, _ []string) error {
	// Read and parse the YAML configuration
	spec, err := loadMCPServerSpec(configFile)
	if err != nil {
		return fmt.Errorf("failed to load configuration: %w", err)
	}

	// Check provenance if requested
	if checkProvenance || warnOnNoProvenance {
		provenanceService, err := createProvenanceService()
		if err != nil {
			return fmt.Errorf("failed to create provenance service: %w", err)
		}

		pkg := domain.PackageIdentifier{
			Protocol: domain.PackageProtocol(spec.Metadata.Protocol),
			Name:     spec.Spec.Package,
			Version:  spec.Spec.Version,
		}

		ctx := context.Background()
		result, err := provenanceService.VerifyProvenance(ctx, pkg)
		if err != nil && checkProvenance {
			return fmt.Errorf("provenance verification failed: %w", err)
		}

		// Print provenance status
		if result != nil {
			cmd.Printf("Provenance check: %s\n", result.Status)
			if result.Status == domain.ProvenanceStatusNone && warnOnNoProvenance {
				cmd.Printf("⚠  Warning: Package has no provenance information\n")
			}
		}
	}

	// Generate Dockerfile
	ctx := context.Background()
	dockerfile, err := generateDockerfile(ctx, spec, outputTag)
	if err != nil {
		return fmt.Errorf("failed to generate Dockerfile: %w", err)
	}

	// Output Dockerfile
	if output != "" {
		// Write to file
		if err := os.WriteFile(output, []byte(dockerfile), 0600); err != nil {
			return fmt.Errorf("failed to write Dockerfile to %s: %w", output, err)
		}
		cmd.Printf("Dockerfile written to: %s\n", output)
	} else {
		// Output to stdout using cobra's command
		cmd.Print(dockerfile)
	}

	return nil
}

// validateConfigPath ensures the config path is safe and within expected directories
func validateConfigPath(configPath string) error {
	// Clean the path to prevent directory traversal
	cleanPath := filepath.Clean(configPath)

	// Check if it follows the new structure: protocol/name/spec.yaml
	if !strings.HasSuffix(cleanPath, "/spec.yaml") && !strings.HasSuffix(cleanPath, "spec.yaml") {
		return fmt.Errorf("config file must be named 'spec.yaml'")
	}

	// Ensure it's in one of the expected directories
	validPrefixes := []string{"npx/", "uvx/", "go/", "skills/"}
	for _, prefix := range validPrefixes {
		if strings.HasPrefix(cleanPath, prefix) {
			// Validate the structure: {type}/{name}/spec.yaml
			parts := strings.Split(cleanPath, "/")
			if len(parts) == 3 && parts[2] == "spec.yaml" {
				return nil
			}
		}
	}

	return fmt.Errorf("config file must follow the structure: {type}/{name}/spec.yaml where type is npx/, uvx/, go/, or skills/")
}

// loadMCPServerSpec reads and parses a YAML configuration file
func loadMCPServerSpec(configPath string) (*MCPServerSpec, error) {
	// Validate the config path for security
	if err := validateConfigPath(configPath); err != nil {
		return nil, fmt.Errorf("invalid config path: %w", err)
	}

	// #nosec G304 - Path is validated above to prevent directory traversal
	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var spec MCPServerSpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return nil, fmt.Errorf("failed to parse YAML: %w", err)
	}

	// Validate required fields
	if spec.Metadata.Name == "" {
		return nil, fmt.Errorf("metadata.name is required")
	}
	if spec.Metadata.Protocol == "" {
		return nil, fmt.Errorf("metadata.protocol is required")
	}
	if spec.Spec.Package == "" {
		return nil, fmt.Errorf("spec.package is required")
	}

	// Validate protocol
	validProtocols := []string{protocolNpx, protocolUvx, protocolGo}
	isValid := false
	for _, p := range validProtocols {
		if spec.Metadata.Protocol == p {
			isValid = true
			break
		}
	}
	if !isValid {
		return nil, fmt.Errorf("invalid protocol %s, must be one of: %v", spec.Metadata.Protocol, validProtocols)
	}

	// Validate dependency overrides/constraints
	if err := validateDependencyOverrides(&spec); err != nil {
		return nil, err
	}

	return &spec, nil
}

// validateDependencyOverrides validates the optional overrides (npx) and constraints
// (uvx) blocks. Every entry must carry a non-empty Reason so the justification for
// circumventing an upstream version pin is auditable in-repo.
func validateDependencyOverrides(spec *MCPServerSpec) error {
	if len(spec.Spec.Overrides) > 0 && spec.Metadata.Protocol != protocolNpx {
		return fmt.Errorf("spec.overrides is only supported for the npx protocol, got %q", spec.Metadata.Protocol)
	}
	if len(spec.Spec.Constraints) > 0 && spec.Metadata.Protocol != protocolUvx {
		return fmt.Errorf("spec.constraints is only supported for the uvx protocol, got %q", spec.Metadata.Protocol)
	}

	for i, o := range spec.Spec.Overrides {
		if o.Package == "" {
			return fmt.Errorf("spec.overrides[%d].package is required", i)
		}
		if o.Version == "" {
			return fmt.Errorf("spec.overrides[%d].version is required", i)
		}
		if strings.TrimSpace(o.Reason) == "" {
			return fmt.Errorf("spec.overrides[%d].reason is required (document why %s is pinned to %s)", i, o.Package, o.Version)
		}
	}

	for i, c := range spec.Spec.Constraints {
		if strings.TrimSpace(c.Spec) == "" {
			return fmt.Errorf("spec.constraints[%d].spec is required", i)
		}
		if strings.TrimSpace(c.Reason) == "" {
			return fmt.Errorf("spec.constraints[%d].reason is required (document why %q is constrained)", i, c.Spec)
		}
	}

	return nil
}

// generateDockerfile generates a Dockerfile using toolhive's library
func generateDockerfile(ctx context.Context, spec *MCPServerSpec, customTag string) (string, error) {
	// Create the protocol scheme string
	packageRef := spec.Spec.Package
	if spec.Spec.Version != "" {
		packageRef = fmt.Sprintf("%s@%s", packageRef, spec.Spec.Version)
	}
	protocolScheme := fmt.Sprintf("%s://%s", spec.Metadata.Protocol, packageRef)

	// Generate the container image tag
	imageTag := customTag
	if imageTag == "" {
		imageTag = generateImageTag(spec)
	}

	// Create image manager
	imageManager := images.NewImageManager(ctx)

	// Generate Dockerfile using toolhive's BuildFromProtocolSchemeWithName function with dryRun=true
	dockerfile, err := runner.BuildFromProtocolSchemeWithName(
		ctx,
		imageManager,
		protocolScheme,
		"", // caCertPath - empty for now
		imageTag,
		spec.Spec.Args, // Pass args from spec if present
		nil,            // runtimeOverride - use defaults
		true,           // always dryRun to generate Dockerfile
	)
	if err != nil {
		return "", fmt.Errorf("failed to generate Dockerfile for protocol scheme %s: %w", protocolScheme, err)
	}

	// Post-process the generated Dockerfile to inject any dependency overrides.
	// toolhive returns the Dockerfile as a string, which is our injection seam; toolhive
	// itself needs no changes.
	dockerfile, err = injectDependencyOverrides(dockerfile, spec)
	if err != nil {
		return "", fmt.Errorf("failed to inject dependency overrides: %w", err)
	}

	return dockerfile, nil
}

// injectDependencyOverrides rewrites the generated Dockerfile to force pinned versions
// of transitive dependencies. For npx it injects an npm "overrides" block; for uvx it
// adds a uv overrides requirements file to the "uv tool install" step. It matches the
// relevant install step by content (not line number) so it stays robust to changes in
// toolhive's template formatting.
func injectDependencyOverrides(dockerfile string, spec *MCPServerSpec) (string, error) {
	switch spec.Metadata.Protocol {
	case protocolNpx:
		if len(spec.Spec.Overrides) == 0 {
			return dockerfile, nil
		}
		return injectNpmOverrides(dockerfile, spec.Spec.Overrides)
	case protocolUvx:
		if len(spec.Spec.Constraints) == 0 {
			return dockerfile, nil
		}
		return injectUvOverrides(dockerfile, spec.Spec.Constraints)
	default:
		return dockerfile, nil
	}
}

// injectNpmOverrides rewrites the package.json creation step so the generated package.json
// carries an "overrides" block. npm honors "overrides" only when present in the package.json
// it installs into, so this is injected before the "npm install" step. The toolhive template
// creates the package.json with a line of the form:
//
//	RUN echo '{"name":"mcp-container","version":"1.0.0"}' > package.json
//
// We locate that line by content (the "> package.json" redirect) and replace the JSON payload
// with one that includes the overrides.
func injectNpmOverrides(dockerfile string, overrides []OverrideEntry) (string, error) {
	overrideMap := make(map[string]string, len(overrides))
	for _, o := range overrides {
		overrideMap[o.Package] = o.Version
	}

	// Mirror the package.json name/version that toolhive's npx template emits, adding the
	// overrides block.
	pkgJSON := map[string]any{
		"name":      "mcp-container",
		"version":   mcpContainerVersion,
		"overrides": overrideMap,
	}
	pkgJSONBytes, err := json.Marshal(pkgJSON)
	if err != nil {
		return "", fmt.Errorf("failed to marshal package.json with overrides: %w", err)
	}

	lines := strings.Split(dockerfile, "\n")
	injected := false
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		// Match the package.json creation step regardless of the exact JSON payload.
		if strings.HasPrefix(trimmed, "RUN echo '") && strings.Contains(trimmed, "> package.json") {
			lines[i] = fmt.Sprintf("RUN echo '%s' > package.json", string(pkgJSONBytes))
			injected = true
			break
		}
	}

	if !injected {
		return "", fmt.Errorf("could not find the 'package.json' creation step in the generated Dockerfile to inject npm overrides")
	}

	return strings.Join(lines, "\n"), nil
}

// injectUvOverrides rewrites the "uv tool install" step so it passes a uv overrides
// requirements file. uv honors override requirements via "--overrides <file>", forcing the
// resolved version of a transitive dependency even when upstream caps it. The toolhive
// template installs with a line of the form:
//
//	uv tool install "$package_spec" && \
//
// We write the override specs to a file (created via a heredoc RUN injected before the
// install step) and add "--overrides" to the install invocation, matching the install line
// by content rather than line number.
func injectUvOverrides(dockerfile string, constraints []ConstraintEntry) (string, error) {
	const overridesFile = "/tmp/uv-overrides.txt"

	// Build a RUN step that writes the overrides requirements file. Each constraint is a
	// PEP 508 requirement on its own line.
	// Emit a single logical RUN that writes each spec (one per line) to the overrides file.
	// Every printed line ends with a backslash continuation so the trailing redirect stays
	// part of the same shell command and is not parsed as a new Dockerfile instruction.
	var fileBuilder strings.Builder
	fileBuilder.WriteString("# Write uv override requirements (forces pinned transitive dependency versions)\n")
	fileBuilder.WriteString("RUN printf '%s\\n' \\\n")
	for _, c := range constraints {
		// Single-quote each spec for shell safety.
		fmt.Fprintf(&fileBuilder, "    '%s' \\\n", c.Spec)
	}
	fmt.Fprintf(&fileBuilder, "    > %s", overridesFile)
	overridesRun := fileBuilder.String()

	lines := strings.Split(dockerfile, "\n")
	installIdx := -1
	for i, line := range lines {
		// Match the actual install command, not Dockerfile comments that merely mention it.
		// The toolhive template invokes it as: uv tool install "$package_spec"
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "#") {
			continue
		}
		if strings.Contains(line, "uv tool install \"") {
			installIdx = i
			break
		}
	}
	if installIdx == -1 {
		return "", fmt.Errorf("could not find the 'uv tool install' step in the generated Dockerfile to inject uv overrides")
	}

	// Add the --overrides flag to the install invocation.
	lines[installIdx] = strings.Replace(
		lines[installIdx],
		"uv tool install ",
		fmt.Sprintf("uv tool install --overrides %s ", overridesFile),
		1,
	)

	// Insert the file-writing RUN step before the install step. The install step is often
	// preceded by comment lines and a "RUN package=..." opener; we insert immediately before
	// the line that opens the install RUN (the first line at or above installIdx that begins
	// with "RUN ").
	insertIdx := installIdx
	for j := installIdx; j >= 0; j-- {
		if strings.HasPrefix(strings.TrimSpace(lines[j]), "RUN ") {
			insertIdx = j
			break
		}
	}

	out := make([]string, 0, len(lines)+1)
	out = append(out, lines[:insertIdx]...)
	out = append(out, overridesRun)
	out = append(out, lines[insertIdx:]...)

	return strings.Join(out, "\n"), nil
}

// generateImageTag creates a container image tag based on the repository structure
// Following the pattern: ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}
func generateImageTag(spec *MCPServerSpec) string {
	// Base registry path
	registry := "ghcr.io/stacklok/dockyard"

	// Clean the package name to create a valid image name
	name := cleanPackageName(spec.Metadata.Name)

	// Use version from spec, fallback to "latest"
	version := spec.Spec.Version
	if version == "" {
		version = "latest"
	}

	return fmt.Sprintf("%s/%s/%s:%s", registry, spec.Metadata.Protocol, name, version)
}

// cleanPackageName converts a package name to a valid container image name
func cleanPackageName(packageName string) string {
	// Remove common prefixes and clean up the name
	name := packageName
	name = strings.TrimPrefix(name, "@")
	name = strings.ReplaceAll(name, "/", "-")
	name = strings.ReplaceAll(name, "_", "-")
	name = strings.ToLower(name)

	// Ensure it doesn't start with a dash
	name = strings.TrimPrefix(name, "-")

	if name == "" {
		name = "mcp-server"
	}

	return name
}

// runVerifyProvenance verifies the provenance of a package
func runVerifyProvenance(cmd *cobra.Command, _ []string) error {
	// Load the spec
	spec, err := loadMCPServerSpec(configFile)
	if err != nil {
		return fmt.Errorf("failed to load configuration: %w", err)
	}

	// Create provenance service
	provenanceService, err := createProvenanceService()
	if err != nil {
		return fmt.Errorf("failed to create provenance service: %w", err)
	}

	// Create package identifier
	pkg := domain.PackageIdentifier{
		Protocol: domain.PackageProtocol(spec.Metadata.Protocol),
		Name:     spec.Spec.Package,
		Version:  spec.Spec.Version,
	}

	// Verify provenance
	ctx := context.Background()
	result, err := provenanceService.VerifyProvenance(ctx, pkg)
	if err != nil {
		return fmt.Errorf("provenance verification failed: %w", err)
	}

	// Display results
	printProvenanceResult(cmd, result)

	// If spec has expected provenance info, validate against it
	if spec.Provenance.Attestations != nil && spec.Provenance.Attestations.Available {
		cmd.Println("\n--- Verification Against Spec ---")
		if !result.HasAttestations {
			cmd.Printf("⚠️  MISMATCH: Spec claims attestations are available, but none found in registry\n")
		} else {
			cmd.Printf("✓ Attestations found as expected\n")

			// Validate publisher if specified
			if spec.Provenance.Attestations.Publisher != nil && result.TrustedPublisher != nil {
				expectedRepo := spec.Provenance.Attestations.Publisher.Repository
				actualRepo := result.TrustedPublisher.Repository
				if expectedRepo != "" && expectedRepo != actualRepo {
					cmd.Printf("⚠️  MISMATCH: Expected publisher repository '%s', got '%s'\n", expectedRepo, actualRepo)
				} else if expectedRepo != "" {
					cmd.Printf("✓ Publisher repository matches: %s\n", expectedRepo)
				}
			}
		}
	}

	// Validate repository URI if specified
	if spec.Provenance.RepositoryURI != "" && result.RepositoryURI != "" {
		if !strings.Contains(result.RepositoryURI, spec.Provenance.RepositoryURI) {
			cmd.Printf("\n⚠️  WARNING: Repository mismatch!\n")
			cmd.Printf("   Expected: %s\n", spec.Provenance.RepositoryURI)
			cmd.Printf("   Found: %s\n", result.RepositoryURI)
		}
	}

	return nil
}

// createProvenanceService creates a provenance service with registered verifiers
func createProvenanceService() (*service.Service, error) {
	ctx := context.Background()
	svc := service.New()

	// Register npm verifier with sigstore support
	npmVerifier, err := npm.NewVerifier(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create npm verifier: %w", err)
	}
	if err := svc.RegisterVerifier(domain.ProtocolNPM, npmVerifier); err != nil {
		return nil, fmt.Errorf("failed to register npm verifier: %w", err)
	}

	// Register PyPI verifier with sigstore support
	pypiVerifier, err := pypi.NewVerifier(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create pypi verifier: %w", err)
	}
	if err := svc.RegisterVerifier(domain.ProtocolPyPI, pypiVerifier); err != nil {
		return nil, fmt.Errorf("failed to register pypi verifier: %w", err)
	}

	return svc, nil
}

// printProvenanceResult prints the provenance verification result
func printProvenanceResult(cmd *cobra.Command, result *domain.ProvenanceResult) {
	cmd.Printf("Package: %s@%s (protocol: %s)\n", result.PackageID.Name, result.PackageID.Version, result.PackageID.Protocol)
	cmd.Printf("Status: %s\n", result.Status)

	printStatusDetails(cmd, result)
	printRepositoryInfo(cmd, result)
	printVerboseDetails(cmd, result)
}

func printStatusDetails(cmd *cobra.Command, result *domain.ProvenanceResult) {
	switch result.Status {
	case domain.ProvenanceStatusVerified:
		printVerifiedStatus(cmd, result)
	case domain.ProvenanceStatusAttestations:
		printAttestationsStatus(cmd, result)
	case domain.ProvenanceStatusSignatures:
		cmd.Printf("✓ Package has signatures (older provenance format)\n")
	case domain.ProvenanceStatusTrustedPublisher:
		printTrustedPublisherStatus(cmd, result)
	case domain.ProvenanceStatusNone:
		cmd.Printf("⚠  No provenance information available\n")
		cmd.Printf("   This package may still be secure but lacks cryptographic verification.\n")
	case domain.ProvenanceStatusError:
		cmd.Printf("✗ Error: %s\n", result.ErrorMessage)
	case domain.ProvenanceStatusUnknown:
		cmd.Printf("? Status unknown: %s\n", result.ErrorMessage)
	}
}

func printVerifiedStatus(cmd *cobra.Command, result *domain.ProvenanceResult) {
	cmd.Printf("✓✓ Package provenance VERIFIED cryptographically!\n")
	if result.AttestationCount > 0 {
		cmd.Printf("  Attestations: %d verified\n", result.AttestationCount)
	}
	printPublisherInfo(cmd, result.TrustedPublisher)
}

func printAttestationsStatus(cmd *cobra.Command, result *domain.ProvenanceResult) {
	cmd.Printf("✓ Package has %d attestation(s)\n", result.AttestationCount)
	if result.TrustedPublisher != nil {
		cmd.Printf("  Publisher: %s (%s)\n", result.TrustedPublisher.Kind, result.TrustedPublisher.Repository)
	}
}

func printTrustedPublisherStatus(cmd *cobra.Command, result *domain.ProvenanceResult) {
	cmd.Printf("✓ Package uses Trusted Publisher\n")
	printPublisherInfo(cmd, result.TrustedPublisher)
	if result.AttestationCount > 0 {
		cmd.Printf("  Attestations: %d\n", result.AttestationCount)
	}
}

func printPublisherInfo(cmd *cobra.Command, publisher *domain.TrustedPublisher) {
	if publisher != nil {
		cmd.Printf("  Publisher: %s (%s)\n", publisher.Kind, publisher.Repository)
		if publisher.Workflow != "" {
			cmd.Printf("  Workflow: %s\n", publisher.Workflow)
		}
	}
}

func printRepositoryInfo(cmd *cobra.Command, result *domain.ProvenanceResult) {
	if result.RepositoryURI != "" {
		cmd.Printf("Repository: %s\n", result.RepositoryURI)
	}
}

func printVerboseDetails(cmd *cobra.Command, result *domain.ProvenanceResult) {
	if verbose && len(result.Details) > 0 {
		cmd.Println("\nDetails:")
		for key, value := range result.Details {
			cmd.Printf("  %s: %v\n", key, value)
		}
	}
}

// runBuildSkill builds an OCI skill artifact from a skill spec.yaml.
func runBuildSkill(cmd *cobra.Command, cfgFile, customTag string, push bool) error {
	spec, err := skillpkg.LoadSkillSpec(cfgFile)
	if err != nil {
		return fmt.Errorf("failed to load skill spec: %w", err)
	}

	if customTag != "" {
		// Override the image tag if custom tag is provided
		spec.Spec.Version = "" // will use custom tag instead
	}

	ctx := context.Background()
	result, err := skillpkg.BuildSkill(ctx, spec)
	if err != nil {
		return fmt.Errorf("failed to build skill: %w", err)
	}
	defer result.Cleanup()

	// Override image ref if custom tag was provided
	if customTag != "" {
		result.ImageRef = customTag
	}

	cmd.Printf("Skill: %s\n", result.SkillName)
	cmd.Printf("Commit: %s\n", result.CommitHash)
	cmd.Printf("Digest: %s\n", result.PackageResult.IndexDigest.String())
	cmd.Printf("Reference: %s\n", result.ImageRef)

	if push {
		if err := skillpkg.PushSkill(ctx, result); err != nil {
			return fmt.Errorf("failed to push skill: %w", err)
		}
		cmd.Printf("Pushed: %s\n", result.ImageRef)
	}

	return nil
}

// runValidateSkill validates a skill from a git repository without packaging.
func runValidateSkill(cmd *cobra.Command, cfgFile string) error {
	spec, err := skillpkg.LoadSkillSpec(cfgFile)
	if err != nil {
		return fmt.Errorf("failed to load skill spec: %w", err)
	}

	ctx := context.Background()
	result, err := skillpkg.ValidateSkill(ctx, spec)
	if err != nil {
		return fmt.Errorf("skill validation failed: %w", err)
	}

	cmd.Printf("Skill: %s\n", result.SkillConfig.Name)
	cmd.Printf("Description: %s\n", result.SkillConfig.Description)
	cmd.Printf("Version: %s\n", result.SkillConfig.Version)
	cmd.Printf("Commit: %s\n", result.CommitHash)
	cmd.Printf("Files: %d\n", len(result.Files))
	cmd.Printf("Status: VALID\n")

	return nil
}
