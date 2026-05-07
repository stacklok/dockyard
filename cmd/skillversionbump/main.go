// Command skillversionbump checks or updates spec.version in skills/*/spec.yaml
// when spec.ref has changed between the PR base and HEAD.
//
// Usage (check mode — exits non-zero if any version is wrong):
//
//	go run ./cmd/skillversionbump --base origin/main
//
// Usage (write mode — updates spec.yaml files on disk):
//
//	go run ./cmd/skillversionbump --base origin/main --write
//
// In GitHub Actions the base SHA is available as GITHUB_BASE_SHA:
//
//	go run ./cmd/skillversionbump --base "$GITHUB_BASE_SHA"
package main

import (
	"context"
	"os"

	"github.com/spf13/cobra"

	"github.com/stacklok/dockyard/internal/skillversion"
)

func main() {
	if err := newRootCmd().Execute(); err != nil {
		os.Exit(1)
	}
}

func newRootCmd() *cobra.Command {
	var (
		baseRef     string
		write       bool
		skipAPI     bool
		token       string
		specPaths   []string
	)

	cmd := &cobra.Command{
		Use:   "skillversionbump",
		Short: "Check or update spec.version in skill spec.yaml files when spec.ref changes",
		Long: `skillversionbump enforces Dockyard's semver policy for vendored skills.

When spec.ref changes between the PR base and HEAD, spec.version must also be
bumped.  The tool applies a heuristic to decide between a patch and a minor
bump (see internal/skillversion/heuristic.go for thresholds):

  - minor if total line churn in the skill subtree >= 120 lines
  - minor if SKILL.md is touched and churn >= 40 lines
  - minor if any commit in range has a feat/feature conventional-commit prefix
  - patch otherwise

Major version bumps are intentionally left to human judgment.

Run without --write to check (CI mode); run with --write to apply fixes.`,
		Example: `  # Check all changed specs against origin/main (CI usage)
  skillversionbump --base origin/main

  # Fix versions in changed specs automatically
  skillversionbump --base origin/main --write

  # Check a specific spec file
  skillversionbump --base origin/main --spec skills/my-skill/spec.yaml

  # Skip GitHub API (patch-only, offline)
  skillversionbump --base origin/main --skip-api`,
		RunE: func(cmd *cobra.Command, _ []string) error {
			return run(cmd, skillversion.Config{
				BaseRef:     baseRef,
				Token:       token,
				Write:       write,
				SkipAPICall: skipAPI,
			}, specPaths)
		},
	}

	cmd.Flags().StringVarP(&baseRef, "base", "b", envOrDefault("GITHUB_BASE_SHA", "origin/main"),
		"Base git ref (SHA or branch) to compare against. Defaults to $GITHUB_BASE_SHA or origin/main.")
	cmd.Flags().BoolVar(&write, "write", false,
		"Update spec.yaml files on disk instead of just checking them.")
	cmd.Flags().BoolVar(&skipAPI, "skip-api", false,
		"Skip the GitHub compare API and always apply a patch bump (useful offline).")
	cmd.Flags().StringVar(&token, "token", envOrDefault("GITHUB_TOKEN", os.Getenv("GH_TOKEN")),
		"GitHub API token. Defaults to $GITHUB_TOKEN or $GH_TOKEN.")
	cmd.Flags().StringArrayVarP(&specPaths, "spec", "s", nil,
		"Specific spec.yaml path(s) to check. If omitted, all changed skills/*/spec.yaml are discovered via git diff.")

	return cmd
}

func run(cmd *cobra.Command, cfg skillversion.Config, specPaths []string) error {
	ctx := context.Background()

	results, err := skillversion.ProcessSpecs(ctx, cfg, specPaths)
	if err != nil {
		return err
	}

	for _, r := range results {
		switch {
		case r.Skipped:
			cmd.Printf("  skip   %s (ref unchanged or new file)\n", r.SpecPath)
		case r.UpToDate && cfg.Write:
			cmd.Printf("  wrote  %s  %s → %s (%s)\n", r.SpecPath, r.OldVersion, r.CurrentVersion, r.Bump)
		case r.UpToDate:
			cmd.Printf("  ok     %s  version %s is correct\n", r.SpecPath, r.CurrentVersion)
		default:
			cmd.Printf("  FAIL   %s  version %s should be %s (%s bump)\n",
				r.SpecPath, r.CurrentVersion, r.ExpectedVersion, r.Bump)
		}
	}

	if !cfg.Write {
		if checkErr := skillversion.CheckErrors(results); checkErr != nil {
			return checkErr
		}
	}

	checked := 0
	for _, r := range results {
		if !r.Skipped {
			checked++
		}
	}
	cmd.Printf("\n%d spec(s) checked, %d skipped (ref unchanged)\n",
		checked, len(results)-checked)
	return nil
}

func envOrDefault(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
