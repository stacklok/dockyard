// Package skills implements skill packaging from git repositories into OCI artifacts.
package skills

import (
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// SkillSpec defines the structure of a skill spec.yaml configuration file.
type SkillSpec struct {
	// Metadata about the skill
	Metadata SkillMetadata `yaml:"metadata"`
	// Spec defines the git source and version
	Spec SkillSourceSpec `yaml:"spec"`
	// Provenance information for supply chain security
	Provenance SkillProvenance `yaml:"provenance,omitempty"`
}

// SkillMetadata contains basic information about the skill.
type SkillMetadata struct {
	Name        string `yaml:"name"`
	Description string `yaml:"description,omitempty"`
}

// SkillSourceSpec defines the git source for a skill.
type SkillSourceSpec struct {
	Repository string `yaml:"repository"` // HTTPS clone URL (e.g., "https://github.com/org/repo")
	Ref        string `yaml:"ref"`        // Git tag, branch, or commit hash
	Path       string `yaml:"path,omitempty"` // Subdirectory within repo (empty = repo root)
	Version    string `yaml:"version"`    // Version for OCI artifact tag
}

// SkillProvenance contains supply chain provenance information for a skill.
type SkillProvenance struct {
	RepositoryURI string `yaml:"repository_uri,omitempty"`
	RepositoryRef string `yaml:"repository_ref,omitempty"`
}

// LoadSkillSpec loads and validates a skill spec.yaml file.
func LoadSkillSpec(configPath string) (*SkillSpec, error) {
	if err := validateSkillConfigPath(configPath); err != nil {
		return nil, err
	}

	data, err := os.ReadFile(configPath) //#nosec G304 -- path validated above
	if err != nil {
		return nil, fmt.Errorf("reading config file: %w", err)
	}

	var spec SkillSpec
	if err := yaml.Unmarshal(data, &spec); err != nil {
		return nil, fmt.Errorf("parsing config file: %w", err)
	}

	if err := validateSkillSpec(&spec); err != nil {
		return nil, err
	}

	return &spec, nil
}

// validateSkillConfigPath ensures the config path is safe.
func validateSkillConfigPath(configPath string) error {
	cleanPath := filepath.Clean(configPath)
	if strings.Contains(cleanPath, "..") {
		return fmt.Errorf("config path %q contains directory traversal", configPath)
	}
	if !strings.HasPrefix(cleanPath, "skills/") && !strings.HasPrefix(cleanPath, "/") {
		// Allow absolute paths and relative paths starting with skills/
	}
	return nil
}

// validateSkillSpec validates the required fields in a skill spec.
func validateSkillSpec(spec *SkillSpec) error {
	if spec.Metadata.Name == "" {
		return fmt.Errorf("metadata.name is required")
	}
	if spec.Spec.Repository == "" {
		return fmt.Errorf("spec.repository is required")
	}
	if spec.Spec.Version == "" {
		return fmt.Errorf("spec.version is required")
	}

	// Validate repository is an HTTPS URL
	u, err := url.Parse(spec.Spec.Repository)
	if err != nil {
		return fmt.Errorf("spec.repository is not a valid URL: %w", err)
	}
	if u.Scheme != "https" {
		return fmt.Errorf("spec.repository must use HTTPS scheme, got %q", u.Scheme)
	}

	return nil
}

// GitReferenceURI constructs a git:// URI from the spec fields for use with toolhive's gitresolver.
// Format: git://host/owner/repo[@ref][#path]
func (s *SkillSpec) GitReferenceURI() (string, error) {
	u, err := url.Parse(s.Spec.Repository)
	if err != nil {
		return "", fmt.Errorf("parsing repository URL: %w", err)
	}

	// Build git:// URI: git://host/path[@ref][#skill-path]
	uri := "git://" + u.Host + u.Path

	if s.Spec.Ref != "" {
		uri += "@" + s.Spec.Ref
	}

	if s.Spec.Path != "" {
		uri += "#" + s.Spec.Path
	}

	return uri, nil
}

// ImageTag returns the full OCI reference for the skill artifact.
// Format: ghcr.io/stacklok/dockyard/skills/{name}:{version}
func (s *SkillSpec) ImageTag() string {
	registry := "ghcr.io/stacklok/dockyard"
	name := strings.ToLower(s.Metadata.Name)
	version := s.Spec.Version
	if version == "" {
		version = "latest"
	}
	return fmt.Sprintf("%s/skills/%s:%s", registry, name, version)
}
