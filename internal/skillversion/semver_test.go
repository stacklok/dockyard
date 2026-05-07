package skillversion

import (
	"testing"
)

func TestParseSemver(t *testing.T) {
	t.Parallel()

	tests := []struct {
		input   string
		want    Semver
		wantErr bool
	}{
		{"1.2.3", Semver{1, 2, 3}, false},
		{"0.1.0", Semver{0, 1, 0}, false},
		{"v0.1.0", Semver{0, 1, 0}, false},
		{"10.20.30", Semver{10, 20, 30}, false},
		{"1.2", Semver{}, true},
		{"1.2.3.4", Semver{}, true},
		{"", Semver{}, true},
		{"a.b.c", Semver{}, true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			t.Parallel()

			got, err := ParseSemver(tt.input)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ParseSemver(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if !tt.wantErr && got != tt.want {
				t.Errorf("ParseSemver(%q) = %v, want %v", tt.input, got, tt.want)
			}
		})
	}
}

func TestSemverBump(t *testing.T) {
	t.Parallel()

	base := Semver{0, 1, 0}

	if got := base.BumpPatch(); got != (Semver{0, 1, 1}) {
		t.Errorf("BumpPatch = %v, want 0.1.1", got)
	}
	if got := base.BumpMinor(); got != (Semver{0, 2, 0}) {
		t.Errorf("BumpMinor = %v, want 0.2.0", got)
	}
	if got := base.Bump(BumpPatch); got != (Semver{0, 1, 1}) {
		t.Errorf("Bump(patch) = %v, want 0.1.1", got)
	}
	if got := base.Bump(BumpMinor); got != (Semver{0, 2, 0}) {
		t.Errorf("Bump(minor) = %v, want 0.2.0", got)
	}
}

func TestSemverString(t *testing.T) {
	t.Parallel()

	s := Semver{1, 2, 3}
	if got := s.String(); got != "1.2.3" {
		t.Errorf("String() = %q, want %q", got, "1.2.3")
	}
}
