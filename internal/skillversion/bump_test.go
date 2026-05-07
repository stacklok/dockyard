package skillversion

import (
	"testing"
)

func TestIsHigherOrEqualBump(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		current  Semver
		expected Semver
		want     bool
	}{
		{"equal versions", Semver{1, 2, 3}, Semver{1, 2, 3}, true},
		{"current major higher", Semver{2, 0, 0}, Semver{1, 9, 9}, true},
		{"current minor higher same major", Semver{1, 3, 0}, Semver{1, 2, 5}, true},
		{"current patch higher same minor", Semver{1, 2, 4}, Semver{1, 2, 3}, true},
		{"current patch lower same minor", Semver{1, 2, 2}, Semver{1, 2, 3}, false},
		{"current minor lower same major", Semver{1, 1, 99}, Semver{1, 2, 0}, false},
		{"current major lower", Semver{0, 9, 9}, Semver{1, 0, 0}, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			if got := isHigherOrEqualBump(tt.current, tt.expected); got != tt.want {
				t.Errorf("isHigherOrEqualBump(%v, %v) = %v, want %v",
					tt.current, tt.expected, got, tt.want)
			}
		})
	}
}
