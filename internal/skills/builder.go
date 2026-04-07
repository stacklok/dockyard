package skills

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	ociskills "github.com/stacklok/toolhive-core/oci/skills"
	"github.com/stacklok/toolhive/pkg/skills/gitresolver"
)

// BuildResult contains the result of building a skill into an OCI artifact.
type BuildResult struct {
	// PackageResult from the OCI packager
	PackageResult *ociskills.PackageResult
	// Store is the local OCI store containing the built artifact
	Store *ociskills.Store
	// CommitHash is the git commit hash that was resolved
	CommitHash string
	// SkillName is the skill name from SKILL.md
	SkillName string
	// ImageRef is the full OCI reference for the artifact
	ImageRef string
	// tmpDir is the temporary directory containing skill files and OCI store
	tmpDir string
}

// Cleanup removes the temporary directory containing the OCI store and skill files.
func (r *BuildResult) Cleanup() {
	if r != nil && r.tmpDir != "" {
		os.RemoveAll(r.tmpDir)
	}
}

// BuildSkill clones a skill from a git repository and packages it as an OCI artifact.
func BuildSkill(ctx context.Context, spec *SkillSpec) (*BuildResult, error) {
	// Construct git reference URI from spec fields
	gitURI, err := spec.GitReferenceURI()
	if err != nil {
		return nil, fmt.Errorf("constructing git reference: %w", err)
	}

	slog.Info("Resolving skill from git", "uri", gitURI)

	// Parse the git reference
	gitRef, err := gitresolver.ParseGitReference(gitURI)
	if err != nil {
		return nil, fmt.Errorf("parsing git reference %q: %w", gitURI, err)
	}

	// Resolve: clone repo, validate SKILL.md, collect files
	resolver := gitresolver.NewResolver()
	resolveResult, err := resolver.Resolve(ctx, gitRef)
	if err != nil {
		return nil, fmt.Errorf("resolving skill from git: %w", err)
	}

	slog.Info("Skill resolved",
		"name", resolveResult.SkillConfig.Name,
		"commit", resolveResult.CommitHash,
		"files", len(resolveResult.Files),
	)

	// Create a temp directory for skill files and OCI store.
	// Caller is responsible for cleanup via CleanupBuild().
	tmpDir, err := os.MkdirTemp("", "dockyard-skill-*")
	if err != nil {
		return nil, fmt.Errorf("creating temp directory: %w", err)
	}

	cleanupOnError := func() { os.RemoveAll(tmpDir) }

	skillDir := filepath.Join(tmpDir, "skill")
	if err := gitresolver.WriteFiles(resolveResult.Files, skillDir, true); err != nil {
		cleanupOnError()
		return nil, fmt.Errorf("writing skill files: %w", err)
	}

	// Create OCI store for packaging
	storeDir := filepath.Join(tmpDir, "oci-store")
	store, err := ociskills.NewStore(storeDir)
	if err != nil {
		cleanupOnError()
		return nil, fmt.Errorf("creating OCI store: %w", err)
	}

	// Package the skill into an OCI artifact
	opts := ociskills.DefaultPackageOptions()
	pkgResult, err := ociskills.NewPackager(store).Package(ctx, skillDir, opts)
	if err != nil {
		cleanupOnError()
		return nil, fmt.Errorf("packaging skill: %w", err)
	}

	slog.Info("Skill packaged",
		"name", pkgResult.Config.Name,
		"index_digest", pkgResult.IndexDigest.String(),
		"platforms", len(pkgResult.Platforms),
	)

	return &BuildResult{
		PackageResult: pkgResult,
		Store:         store,
		CommitHash:    resolveResult.CommitHash,
		SkillName:     resolveResult.SkillConfig.Name,
		ImageRef:      spec.ImageTag(),
		tmpDir:        tmpDir,
	}, nil
}

// ValidateSkill clones a skill from a git repository and validates its SKILL.md.
// Returns the resolved metadata without packaging.
func ValidateSkill(ctx context.Context, spec *SkillSpec) (*gitresolver.ResolveResult, error) {
	gitURI, err := spec.GitReferenceURI()
	if err != nil {
		return nil, fmt.Errorf("constructing git reference: %w", err)
	}

	slog.Info("Validating skill from git", "uri", gitURI)

	gitRef, err := gitresolver.ParseGitReference(gitURI)
	if err != nil {
		return nil, fmt.Errorf("parsing git reference %q: %w", gitURI, err)
	}

	resolver := gitresolver.NewResolver()
	result, err := resolver.Resolve(ctx, gitRef)
	if err != nil {
		return nil, fmt.Errorf("resolving skill from git: %w", err)
	}

	slog.Info("Skill validated",
		"name", result.SkillConfig.Name,
		"commit", result.CommitHash,
		"files", len(result.Files),
	)

	return result, nil
}
