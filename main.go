// Package main implements the Dockyard MCP server containerization tool.
// It reads YAML configuration files and uses ToolHive to build container images
// from protocol schemes (npx://, uvx://, go://).
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/stacklok/toolhive/pkg/container/images"
	"github.com/stacklok/toolhive/pkg/logger"
	"github.com/stacklok/toolhive/pkg/runner"
	"gopkg.in/yaml.v3"
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
	Version     string `yaml:"version,omitempty"`
	Protocol    string `yaml:"protocol"` // npx, uvx, go
}

// MCPServerPackageSpec defines the package to be containerized
type MCPServerPackageSpec struct {
	Package string `yaml:"package"`           // e.g., "@upstash/context7-mcp"
	Version string `yaml:"version,omitempty"` // e.g., "1.0.14"
}

// MCPServerProvenance contains supply chain provenance information
type MCPServerProvenance struct {
	SigstoreURL       string `yaml:"sigstore_url,omitempty"`
	RepositoryURI     string `yaml:"repository_uri,omitempty"`
	RepositoryRef     string `yaml:"repository_ref,omitempty"`
	SignerIdentity    string `yaml:"signer_identity,omitempty"`
	RunnerEnvironment string `yaml:"runner_environment,omitempty"`
	CertIssuer        string `yaml:"cert_issuer,omitempty"`
}

func main() {
	// Initialize the logger
	logger.Initialize()

	var (
		configFile = flag.String("config", "", "Path to the YAML configuration file")
		outputTag  = flag.String("tag", "", "Custom container image tag (optional)")
		output     = flag.String("output", "", "Output file for Dockerfile (optional, defaults to stdout)")
	)
	flag.Parse()

	if *configFile == "" {
		log.Fatal("Please provide a configuration file with -config flag")
	}

	// Read and parse the YAML configuration
	spec, err := loadMCPServerSpec(*configFile)
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Generate Dockerfile
	ctx := context.Background()
	dockerfile, err := generateDockerfile(ctx, spec, *outputTag)
	if err != nil {
		log.Fatalf("Failed to generate Dockerfile: %v", err)
	}

	// Output Dockerfile
	if *output != "" {
		// Write to file
		if err := os.WriteFile(*output, []byte(dockerfile), 0600); err != nil {
			log.Fatalf("Failed to write Dockerfile to %s: %v", *output, err)
		}
		fmt.Printf("Dockerfile written to: %s\n", *output)
	} else {
		// Output to stdout
		fmt.Print(dockerfile)
	}
}

// validateConfigPath ensures the config path is safe and within expected directories
func validateConfigPath(configPath string) error {
	// Clean the path to prevent directory traversal
	cleanPath := filepath.Clean(configPath)

	// Check if it follows the new structure: protocol/name/spec.yaml
	if !strings.HasSuffix(cleanPath, "/spec.yaml") && !strings.HasSuffix(cleanPath, "spec.yaml") {
		return fmt.Errorf("config file must be named 'spec.yaml'")
	}

	// Ensure it's in one of the expected protocol directories
	validPrefixes := []string{"npx/", "uvx/", "go/"}
	for _, prefix := range validPrefixes {
		if strings.HasPrefix(cleanPath, prefix) {
			// Validate the structure: protocol/name/spec.yaml
			parts := strings.Split(cleanPath, "/")
			if len(parts) == 3 && parts[2] == "spec.yaml" {
				return nil
			}
		}
	}

	return fmt.Errorf("config file must follow the structure: {protocol}/{name}/spec.yaml where protocol is npx/, uvx/, or go/")
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
	validProtocols := []string{"npx", "uvx", "go"}
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

	return &spec, nil
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
		true, // always dryRun to generate Dockerfile
	)
	if err != nil {
		return "", fmt.Errorf("failed to generate Dockerfile for protocol scheme %s: %w", protocolScheme, err)
	}

	return dockerfile, nil
}

// generateImageTag creates a container image tag based on the repository structure
// Following the pattern: ghcr.io/stacklok/dockyard/{protocol}/{name}:{version}
func generateImageTag(spec *MCPServerSpec) string {
	// Base registry path
	registry := "ghcr.io/stacklok/dockyard"

	// Clean the package name to create a valid image name
	name := cleanPackageName(spec.Metadata.Name)

	// Use version from spec or metadata, fallback to "latest"
	version := spec.Spec.Version
	if version == "" {
		version = spec.Metadata.Version
	}
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
