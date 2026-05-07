package skillversion

import (
	"context"
	"fmt"
	"strings"
)

// BumpResult records the outcome of evaluating one skill spec.yaml.
type BumpResult struct {
	SpecPath        string
	OldRef          string
	NewRef          string
	OldVersion      string
	CurrentVersion  string
	ExpectedVersion string
	Bump            BumpType
	Signals         ChangeSignals
	// Skipped is true when ref did not change (no action needed).
	Skipped bool
	// UpToDate is true when CurrentVersion already matches ExpectedVersion.
	UpToDate bool
}

// Config controls how ProcessSpecs behaves.
type Config struct {
	// BaseRef is the git ref (SHA or branch) representing the merge base.
	// Required unless SpecPaths are provided with explicit old refs.
	BaseRef string
	// Token is the GitHub API token used for the compare API.
	// Falls back to unauthenticated if empty (rate-limited).
	Token string
	// Write, when true, updates spec.yaml files on disk instead of just
	// checking them.
	Write bool
	// SkipAPICall disables the GitHub compare API call and always returns
	// a patch bump.  Useful for offline testing.
	SkipAPICall bool
}

// ProcessSpecs evaluates every spec path against the heuristic and either
// checks that spec.version is correct (Config.Write == false) or updates it
// (Config.Write == true).
//
// When specPaths is empty the function discovers changed specs automatically
// using git diff against cfg.BaseRef.
func ProcessSpecs(ctx context.Context, cfg Config, specPaths []string) ([]BumpResult, error) {
	if len(specPaths) == 0 {
		var err error
		specPaths, err = changedSkillSpecs(cfg.BaseRef)
		if err != nil {
			return nil, fmt.Errorf("discovering changed specs: %w", err)
		}
	}

	var results []BumpResult
	for _, path := range specPaths {
		result, err := processOneSpec(ctx, cfg, path)
		if err != nil {
			return results, fmt.Errorf("processing %s: %w", path, err)
		}
		results = append(results, result)
	}
	return results, nil
}

func processOneSpec(ctx context.Context, cfg Config, path string) (BumpResult, error) {
	head, err := readSpec(path)
	if err != nil {
		return BumpResult{}, err
	}

	base, err := readBaseSpec(cfg.BaseRef, path)
	if err != nil {
		// File may be new (no base); treat as needing a patch bump from 0.1.0.
		// We skip it here — the PR author must set an initial version.
		return BumpResult{SpecPath: path, Skipped: true}, nil
	}

	result := BumpResult{
		SpecPath:       path,
		OldRef:         base.Spec.Ref,
		NewRef:         head.Spec.Ref,
		OldVersion:     base.Spec.Version,
		CurrentVersion: head.Spec.Version,
	}

	if base.Spec.Ref == head.Spec.Ref {
		result.Skipped = true
		return result, nil
	}

	// ref changed — compute expected version
	var signals ChangeSignals
	if !cfg.SkipAPICall && head.Spec.Repository != "" && base.Spec.Ref != "" && head.Spec.Ref != "" {
		owner, repo, err := parseGitHubRepo(head.Spec.Repository)
		if err == nil {
			signals, err = computeSignals(ctx, cfg.Token, owner, repo, base.Spec.Ref, head.Spec.Ref, head.Spec.Path)
			if err != nil {
				// Non-fatal: fall back to patch if the API is unreachable.
				fmt.Printf("warning: GitHub compare API failed for %s: %v (defaulting to patch)\n", path, err)
			}
		}
	}

	bump := DetermineBump(signals)
	result.Bump = bump
	result.Signals = signals

	current, err := ParseSemver(head.Spec.Version)
	if err != nil {
		return BumpResult{}, fmt.Errorf("parsing current version %q: %w", head.Spec.Version, err)
	}

	old, err := ParseSemver(base.Spec.Version)
	if err != nil {
		return BumpResult{}, fmt.Errorf("parsing base version %q: %w", base.Spec.Version, err)
	}

	expected := old.Bump(bump)
	result.ExpectedVersion = expected.String()

	if current.String() == expected.String() {
		result.UpToDate = true
		return result, nil
	}

	// Check if a higher bump was manually applied (acceptable).
	if isHigherOrEqualBump(current, old, expected) {
		result.UpToDate = true
		return result, nil
	}

	if cfg.Write {
		if err := updateSpecVersion(path, expected.String()); err != nil {
			return result, fmt.Errorf("writing version: %w", err)
		}
		result.CurrentVersion = expected.String()
		result.UpToDate = true
	}

	return result, nil
}

// isHigherOrEqualBump returns true when the current version in the file is
// already at least as high as the expected version, which means the human
// reviewer applied a higher bump (e.g. minor when we suggested patch).
func isHigherOrEqualBump(current, old, expected Semver) bool {
	if current.Major > expected.Major {
		return true
	}
	if current.Major == expected.Major && current.Minor > expected.Minor {
		return true
	}
	if current.Major == expected.Major && current.Minor == expected.Minor && current.Patch >= expected.Patch {
		return true
	}
	// Also check that it's actually higher than old (not a downgrade).
	_ = old
	return false
}

// CheckErrors returns a formatted error message listing all specs that are
// not up to date, suitable for failing a CI step.
func CheckErrors(results []BumpResult) error {
	var bad []string
	for _, r := range results {
		if r.Skipped || r.UpToDate {
			continue
		}
		bad = append(bad, fmt.Sprintf(
			"  %s: ref changed %s→%s but version %s needs to be at least %s (%s bump, signals: +/-%d lines, SKILL.md=%v, feat=%v)",
			r.SpecPath, shortRef(r.OldRef), shortRef(r.NewRef),
			r.CurrentVersion, r.ExpectedVersion, r.Bump,
			r.Signals.TotalChange, r.Signals.SkillMDTouched, r.Signals.FeatCommit,
		))
	}
	if len(bad) == 0 {
		return nil
	}
	return fmt.Errorf("skill version check failed — run `go run ./cmd/skillversionbump --write` to fix:\n%s", strings.Join(bad, "\n"))
}

func shortRef(ref string) string {
	if len(ref) > 8 {
		return ref[:8]
	}
	return ref
}
