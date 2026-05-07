package skillversion

import (
	"fmt"
	"strconv"
	"strings"
)

// Semver holds a parsed X.Y.Z version string.
type Semver struct {
	Major int
	Minor int
	Patch int
}

// ParseSemver parses a version string of the form "X.Y.Z" (leading "v" is
// stripped if present).
func ParseSemver(v string) (Semver, error) {
	v = strings.TrimPrefix(v, "v")
	parts := strings.SplitN(v, ".", 3)
	if len(parts) != 3 {
		return Semver{}, fmt.Errorf("invalid semver %q: expected X.Y.Z", v)
	}
	major, err := strconv.Atoi(parts[0])
	if err != nil {
		return Semver{}, fmt.Errorf("invalid semver major in %q: %w", v, err)
	}
	minor, err := strconv.Atoi(parts[1])
	if err != nil {
		return Semver{}, fmt.Errorf("invalid semver minor in %q: %w", v, err)
	}
	patch, err := strconv.Atoi(parts[2])
	if err != nil {
		return Semver{}, fmt.Errorf("invalid semver patch in %q: %w", v, err)
	}
	return Semver{Major: major, Minor: minor, Patch: patch}, nil
}

// String formats the semver as "X.Y.Z".
func (s Semver) String() string {
	return fmt.Sprintf("%d.%d.%d", s.Major, s.Minor, s.Patch)
}

// BumpPatch returns a new Semver with the patch component incremented.
func (s Semver) BumpPatch() Semver {
	return Semver{Major: s.Major, Minor: s.Minor, Patch: s.Patch + 1}
}

// BumpMinor returns a new Semver with the minor component incremented and
// patch reset to 0.
func (s Semver) BumpMinor() Semver {
	return Semver{Major: s.Major, Minor: s.Minor + 1, Patch: 0}
}

// Bump returns a new Semver incremented according to t.
func (s Semver) Bump(t BumpType) Semver {
	switch t {
	case BumpMinor:
		return s.BumpMinor()
	default:
		return s.BumpPatch()
	}
}
