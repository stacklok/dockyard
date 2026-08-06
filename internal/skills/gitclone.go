package skills

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// cloneTimeout bounds how long a sparse skill clone may take.
const cloneTimeout = 5 * time.Minute

// skillCheckout is a sparse checkout of a single skill directory from a git remote.
type skillCheckout struct {
	// RootDir is the temporary directory that owns the clone (removed by Cleanup).
	RootDir string
	// SkillDir is the absolute path to the skill files (SKILL.md lives here).
	SkillDir string
	// CommitHash is the resolved HEAD commit after checkout.
	CommitHash string
}

// Cleanup removes the temporary clone directory.
func (c *skillCheckout) Cleanup() {
	if c != nil && c.RootDir != "" {
		_ = os.RemoveAll(c.RootDir) //#nosec G104 -- best-effort cleanup of temp directory
	}
}

// checkoutSkill clones repository at ref with a blobless/partial clone and
// sparse-checkouts only skillPath (or the repo root when skillPath is empty).
// This avoids go-git's in-memory LimitedFs, which cannot hold large monorepos
// such as vercel/next.js.
func checkoutSkill(ctx context.Context, repository, ref, skillPath string) (*skillCheckout, error) {
	if repository == "" {
		return nil, fmt.Errorf("repository is required")
	}
	if ref == "" {
		return nil, fmt.Errorf("ref is required")
	}
	if err := validateGitPath(skillPath); err != nil {
		return nil, err
	}

	ctx, cancel := context.WithTimeout(ctx, cloneTimeout)
	defer cancel()

	rootDir, err := os.MkdirTemp("", "dockyard-skill-src-*")
	if err != nil {
		return nil, fmt.Errorf("creating temp directory: %w", err)
	}
	cleanupOnError := func() { _ = os.RemoveAll(rootDir) } //#nosec G104 -- best-effort cleanup on error

	repoDir := filepath.Join(rootDir, "repo")

	// Blobless clone + sparse checkout keeps large monorepos tractable.
	if err := runGit(ctx, "", "clone", "--filter=tree:0", "--sparse", "--no-checkout", repository, repoDir); err != nil {
		cleanupOnError()
		return nil, fmt.Errorf("cloning repository: %w", err)
	}

	if skillPath != "" {
		// --no-cone allows checking out a nested path without its parents' other children.
		if err := runGit(ctx, repoDir, "sparse-checkout", "set", "--no-cone", skillPath); err != nil {
			cleanupOnError()
			return nil, fmt.Errorf("configuring sparse-checkout for %q: %w", skillPath, err)
		}
	}

	if err := runGit(ctx, repoDir, "checkout", "--detach", ref); err != nil {
		cleanupOnError()
		return nil, fmt.Errorf("checking out ref %q: %w", ref, err)
	}

	commitHash, err := runGitOutput(ctx, repoDir, "rev-parse", "HEAD")
	if err != nil {
		cleanupOnError()
		return nil, fmt.Errorf("resolving commit hash: %w", err)
	}

	skillDir := repoDir
	if skillPath != "" {
		skillDir = filepath.Join(repoDir, filepath.FromSlash(skillPath))
	}

	if st, err := os.Stat(skillDir); err != nil || !st.IsDir() {
		cleanupOnError()
		return nil, fmt.Errorf("skill path %q not found after checkout", skillPath)
	}

	return &skillCheckout{
		RootDir:    rootDir,
		SkillDir:   skillDir,
		CommitHash: commitHash,
	}, nil
}

func validateGitPath(skillPath string) error {
	if skillPath == "" {
		return nil
	}
	if filepath.IsAbs(skillPath) || strings.Contains(skillPath, "..") || strings.ContainsRune(skillPath, 0) {
		return fmt.Errorf("invalid skill path %q", skillPath)
	}
	return nil
}

func runGit(ctx context.Context, dir string, args ...string) error {
	_, err := runGitOutput(ctx, dir, args...)
	return err
}

func runGitOutput(ctx context.Context, dir string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, "git", args...) //#nosec G204 -- args are constructed internally from validated spec fields
	if dir != "" {
		cmd.Dir = dir
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = err.Error()
		}
		return "", fmt.Errorf("git %s: %s", args[0], msg)
	}
	return strings.TrimSpace(stdout.String()), nil
}
