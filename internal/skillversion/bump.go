package skillversion

import (
	"context"
	"fmt"
	"os"
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
	// APIError is non-empty when the GitHub compare API call failed and the
	// tool fell back to a default (patch) bump.  Reviewers should treat any
	// non-empty APIError as a signal that the heuristic could not run and
	// the suggested bump may be too low.
	APIError string
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
		// File may be new (no base); skip — PR author must set an initial version.
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

	// An empty spec.path would silently widen the heuristic's churn scope to
	// the entire upstream repo, producing misleading minor bumps for unrelated
	// drift.  Refuse rather than guess.
	if strings.TrimSpace(head.Spec.Path) == "" {
		return BumpResult{}, fmt.Errorf("spec.path is empty in %s; cannot scope upstream diff", path)
	}

	signals, apiErr := fetchSignals(ctx, cfg, head, base.Spec.Ref, path)
	result.Signals = signals
	result.Bump = DetermineBump(signals)
	if apiErr != nil {
		result.APIError = apiErr.Error()
	}

	return finalizeVersion(cfg, result, base.Spec.Version, head.Spec.Version)
}

// fetchSignals calls the GitHub compare API and returns ChangeSignals plus an
// optional error.  When err is non-nil the returned ChangeSignals is the
// zero value (which DetermineBump treats as patch) and the error is intended
// to be surfaced via BumpResult.APIError so reviewers know the heuristic
// could not run.  A warning is also printed to stderr for immediate visibility
// in CI logs.
func fetchSignals(ctx context.Context, cfg Config, head skillSpecYAML, oldRef, specPath string) (ChangeSignals, error) {
	if cfg.SkipAPICall || head.Spec.Repository == "" || oldRef == "" || head.Spec.Ref == "" {
		return ChangeSignals{}, nil
	}
	owner, repo, err := parseGitHubRepo(head.Spec.Repository)
	if err != nil {
		fmt.Fprintf(os.Stderr, "warning: cannot parse repository for %s: %v (defaulting to patch)\n", specPath, err)
		return ChangeSignals{}, err
	}
	signals, err := computeSignals(ctx, nil, cfg.Token, owner, repo, oldRef, head.Spec.Ref, head.Spec.Path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "warning: GitHub compare API failed for %s: %v (defaulting to patch)\n", specPath, err)
		return ChangeSignals{}, err
	}
	return signals, nil
}

// finalizeVersion computes the expected version from bump type, compares it to
// the current version on disk, and writes it if cfg.Write is set.
func finalizeVersion(cfg Config, result BumpResult, oldVersion, currentVersion string) (BumpResult, error) {
	current, err := ParseSemver(currentVersion)
	if err != nil {
		return BumpResult{}, fmt.Errorf("parsing current version %q: %w", currentVersion, err)
	}

	old, err := ParseSemver(oldVersion)
	if err != nil {
		return BumpResult{}, fmt.Errorf("parsing base version %q: %w", oldVersion, err)
	}

	expected := old.Bump(result.Bump)
	result.ExpectedVersion = expected.String()

	if current.String() == expected.String() || isHigherOrEqualBump(current, expected) {
		result.UpToDate = true
		return result, nil
	}

	if cfg.Write {
		if err := updateSpecVersion(result.SpecPath, expected.String()); err != nil {
			return result, fmt.Errorf("writing version: %w", err)
		}
		result.CurrentVersion = expected.String()
		result.UpToDate = true
	}

	return result, nil
}

// isHigherOrEqualBump returns true when current is already at or above
// expected, meaning the reviewer applied a higher bump than the heuristic
// suggested (e.g. minor when the tool would have picked patch).
func isHigherOrEqualBump(current, expected Semver) bool {
	if current.Major != expected.Major {
		return current.Major > expected.Major
	}
	if current.Minor != expected.Minor {
		return current.Minor > expected.Minor
	}
	return current.Patch >= expected.Patch
}

// CheckErrors returns a formatted error message listing all specs that are
// not up to date, suitable for failing a CI step.  When the heuristic could
// not run because of a GitHub API failure (BumpResult.APIError set) that is
// included in the message so reviewers know the suggested bump may be too
// conservative.
func CheckErrors(results []BumpResult) error {
	var bad []string
	for _, r := range results {
		if r.Skipped || r.UpToDate {
			continue
		}
		msg := fmt.Sprintf(
			"  %s: ref changed %s→%s but version %s needs to be at least %s "+
				"(%s bump, signals: +/-%d lines, SKILL.md=%v, feat=%v)",
			r.SpecPath, shortRef(r.OldRef), shortRef(r.NewRef),
			r.CurrentVersion, r.ExpectedVersion, r.Bump,
			r.Signals.TotalChange, r.Signals.SkillMDTouched, r.Signals.FeatCommit,
		)
		if r.APIError != "" {
			msg += fmt.Sprintf("\n      ⚠ heuristic ran without GitHub data: %s", r.APIError)
		}
		bad = append(bad, msg)
	}
	if len(bad) == 0 {
		return nil
	}
	return fmt.Errorf(
		"skill version check failed"+
			" — run `go run ./cmd/skillversionbump --write` to fix:\n%s",
		strings.Join(bad, "\n"),
	)
}

func shortRef(ref string) string {
	if len(ref) > 8 {
		return ref[:8]
	}
	return ref
}
