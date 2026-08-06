package skills

import (
	"context"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"

	ociskills "github.com/stacklok/toolhive-core/oci/skills"
	thvskills "github.com/stacklok/toolhive/pkg/skills"
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
		_ = os.RemoveAll(r.tmpDir) //#nosec G104 -- best-effort cleanup of temp directory
	}
}

// ValidationResult contains the outcome of validating a skill without packaging.
type ValidationResult struct {
	SkillConfig *thvskills.ParseResult
	CommitHash  string
	FileCount   int
}

// BuildSkill clones a skill from a git repository and packages it as an OCI artifact.
func BuildSkill(ctx context.Context, spec *SkillSpec) (*BuildResult, error) {
	slog.Info("Resolving skill from git",
		"repository", spec.Spec.Repository,
		"ref", spec.Spec.Ref,
		"path", spec.Spec.Path,
	)

	checkout, err := checkoutSkill(ctx, spec.Spec.Repository, spec.Spec.Ref, spec.Spec.Path)
	if err != nil {
		return nil, fmt.Errorf("resolving skill from git: %w", err)
	}
	// Ownership of checkout.RootDir transfers to BuildResult.tmpDir on success.
	cleanupCheckout := true
	defer func() {
		if cleanupCheckout {
			checkout.Cleanup()
		}
	}()

	parsed, err := parseAndValidateSkillMD(checkout.SkillDir)
	if err != nil {
		return nil, err
	}

	slog.Info("Skill resolved",
		"name", parsed.Name,
		"commit", checkout.CommitHash,
	)

	skillDir := filepath.Join(checkout.RootDir, "skill")
	if err := copyDir(checkout.SkillDir, skillDir); err != nil {
		return nil, fmt.Errorf("copying skill files: %w", err)
	}

	storeDir := filepath.Join(checkout.RootDir, "oci-store")
	store, err := ociskills.NewStore(storeDir)
	if err != nil {
		return nil, fmt.Errorf("creating OCI store: %w", err)
	}

	opts := ociskills.DefaultPackageOptions()
	pkgResult, err := ociskills.NewPackager(store).Package(ctx, skillDir, opts)
	if err != nil {
		return nil, fmt.Errorf("packaging skill: %w", err)
	}

	slog.Info("Skill packaged",
		"name", pkgResult.Config.Name,
		"index_digest", pkgResult.IndexDigest.String(),
		"platforms", len(pkgResult.Platforms),
	)

	cleanupCheckout = false
	return &BuildResult{
		PackageResult: pkgResult,
		Store:         store,
		CommitHash:    checkout.CommitHash,
		SkillName:     parsed.Name,
		ImageRef:      spec.ImageTag(),
		tmpDir:        checkout.RootDir,
	}, nil
}

// ValidateSkill clones a skill from a git repository and validates its SKILL.md.
// Returns the resolved metadata without packaging.
func ValidateSkill(ctx context.Context, spec *SkillSpec) (*ValidationResult, error) {
	slog.Info("Validating skill from git",
		"repository", spec.Spec.Repository,
		"ref", spec.Spec.Ref,
		"path", spec.Spec.Path,
	)

	checkout, err := checkoutSkill(ctx, spec.Spec.Repository, spec.Spec.Ref, spec.Spec.Path)
	if err != nil {
		return nil, fmt.Errorf("resolving skill from git: %w", err)
	}
	defer checkout.Cleanup()

	parsed, err := parseAndValidateSkillMD(checkout.SkillDir)
	if err != nil {
		return nil, err
	}

	fileCount, err := countFiles(checkout.SkillDir)
	if err != nil {
		return nil, fmt.Errorf("counting skill files: %w", err)
	}

	slog.Info("Skill validated",
		"name", parsed.Name,
		"commit", checkout.CommitHash,
		"files", fileCount,
	)

	return &ValidationResult{
		SkillConfig: parsed,
		CommitHash:  checkout.CommitHash,
		FileCount:   fileCount,
	}, nil
}

func parseAndValidateSkillMD(skillDir string) (*thvskills.ParseResult, error) {
	skillMDPath := filepath.Join(skillDir, "SKILL.md")
	content, err := os.ReadFile(skillMDPath) //#nosec G304 -- path is under a temp checkout we created
	if err != nil {
		return nil, fmt.Errorf("reading SKILL.md: %w", err)
	}

	parsed, err := thvskills.ParseSkillMD(content)
	if err != nil {
		return nil, fmt.Errorf("parsing SKILL.md: %w", err)
	}

	if err := thvskills.ValidateSkillName(parsed.Name); err != nil {
		return nil, fmt.Errorf("invalid skill name in SKILL.md: %w", err)
	}

	return parsed, nil
}

func countFiles(root string) (int, error) {
	count := 0
	err := filepath.WalkDir(root, func(_ string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.Type().IsRegular() {
			count++
		}
		return nil
	})
	return count, err
}

func copyDir(src, dst string) error {
	return filepath.WalkDir(src, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}

		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)

		if d.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		if !d.Type().IsRegular() {
			return nil
		}

		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}

		in, err := os.Open(path) //#nosec G304 -- path walked from a temp checkout we created
		if err != nil {
			return err
		}
		defer in.Close() //nolint:errcheck

		out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644) //#nosec G302,G304 -- skill files are non-executable content
		if err != nil {
			return err
		}
		defer out.Close() //nolint:errcheck

		_, err = io.Copy(out, in)
		return err
	})
}
