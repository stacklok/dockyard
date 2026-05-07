// Package skillversion provides heuristics and tooling for automatically
// bumping spec.version in skill spec.yaml files when spec.ref changes.
// Dockyard owns semver for vendored skills because upstreams typically do not
// publish per-skill version tags.
package skillversion

import "regexp"

// Line-churn thresholds used by DetermineBump.  Adjust these constants to
// re-tune the heuristic without touching any logic.
const (
	// MinorThresholdLines triggers a minor bump when the total lines added +
	// deleted inside the skill subtree exceeds this value.
	MinorThresholdLines = 120

	// SkillMDMinorThresholdLines triggers a minor bump when SKILL.md itself
	// is touched and total churn in the subtree exceeds this (lower threshold
	// because SKILL.md edits signal user-visible changes).
	SkillMDMinorThresholdLines = 40
)

// featCommitRe matches "feat:" / "feat(scope):" / "feature:" commit prefixes
// (case-insensitive) that indicate user-facing additions.
var featCommitRe = regexp.MustCompile(`(?i)^(feat|feature)[\(:]`)

// BumpType represents the semver component to increment.
type BumpType string

const (
	BumpPatch BumpType = "patch"
	BumpMinor BumpType = "minor"
)

// ChangeSignals holds the raw measurements gathered from the upstream diff
// that are fed into DetermineBump.
type ChangeSignals struct {
	// TotalChange is the sum of additions + deletions across all files in the
	// skill subtree between the old and new ref.
	TotalChange int
	// SkillMDTouched is true when SKILL.md is among the changed files.
	SkillMDTouched bool
	// FeatCommit is true when at least one commit in range has a message that
	// matches the feat/feature conventional-commit prefix.
	FeatCommit bool
}

// DetermineBump returns the appropriate BumpType based on change signals.
// The logic is intentionally simple and transparent:
//   - minor if total churn >= MinorThresholdLines
//   - minor if SKILL.md changed and churn >= SkillMDMinorThresholdLines
//   - minor if any feat-style commit appears in range
//   - patch otherwise
func DetermineBump(signals ChangeSignals) BumpType {
	if signals.TotalChange >= MinorThresholdLines {
		return BumpMinor
	}
	if signals.SkillMDTouched && signals.TotalChange >= SkillMDMinorThresholdLines {
		return BumpMinor
	}
	if signals.FeatCommit {
		return BumpMinor
	}
	return BumpPatch
}

// IsFeatCommitMessage reports whether a raw commit message string matches the
// feat/feature conventional-commit prefix.
func IsFeatCommitMessage(msg string) bool {
	return featCommitRe.MatchString(msg)
}
