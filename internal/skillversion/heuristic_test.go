package skillversion

import (
	"testing"
)

func TestDetermineBump(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		signals ChangeSignals
		want    BumpType
	}{
		{
			name:    "small change is patch",
			signals: ChangeSignals{TotalChange: 10},
			want:    BumpPatch,
		},
		{
			name:    "churn at threshold is minor",
			signals: ChangeSignals{TotalChange: MinorThresholdLines},
			want:    BumpMinor,
		},
		{
			name:    "churn above threshold is minor",
			signals: ChangeSignals{TotalChange: MinorThresholdLines + 50},
			want:    BumpMinor,
		},
		{
			name:    "SKILL.md touched below threshold is patch",
			signals: ChangeSignals{TotalChange: SkillMDMinorThresholdLines - 1, SkillMDTouched: true},
			want:    BumpPatch,
		},
		{
			name:    "SKILL.md touched at threshold is minor",
			signals: ChangeSignals{TotalChange: SkillMDMinorThresholdLines, SkillMDTouched: true},
			want:    BumpMinor,
		},
		{
			name:    "feat commit triggers minor regardless of churn",
			signals: ChangeSignals{TotalChange: 5, FeatCommit: true},
			want:    BumpMinor,
		},
		{
			name:    "no signals defaults to patch",
			signals: ChangeSignals{},
			want:    BumpPatch,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			got := DetermineBump(tt.signals)
			if got != tt.want {
				t.Errorf("DetermineBump(%+v) = %q, want %q", tt.signals, got, tt.want)
			}
		})
	}
}

func TestIsFeatCommitMessage(t *testing.T) {
	t.Parallel()

	tests := []struct {
		msg  string
		want bool
	}{
		{"feat: add new tool", true},
		{"feat(scope): add new tool", true},
		{"feature: something", true},
		{"feature(ui): changes", true},
		{"FEAT: uppercase", true},
		{"fix: bug fix", false},
		{"chore: maintenance", false},
		{"docs: update readme", false},
		{"refactor: clean up", false},
		{"feat without colon or paren", false},
	}

	for _, tt := range tests {
		t.Run(tt.msg, func(t *testing.T) {
			t.Parallel()

			got := IsFeatCommitMessage(tt.msg)
			if got != tt.want {
				t.Errorf("IsFeatCommitMessage(%q) = %v, want %v", tt.msg, got, tt.want)
			}
		})
	}
}
