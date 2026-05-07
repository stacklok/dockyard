package skillversion

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateSpecPath(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		path    string
		wantErr bool
	}{
		{"valid path", "skills/foo/spec.yaml", false},
		{"valid path nested", "skills/some-name-with-dashes/spec.yaml", false},
		{"path traversal rejected", "skills/../etc/spec.yaml", true},
		{"wrong directory rejected", "npx/foo/spec.yaml", true},
		{"wrong filename rejected", "skills/foo/other.yaml", true},
		{"empty rejected", "", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			err := validateSpecPath(tt.path)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateSpecPath(%q) err = %v, wantErr %v", tt.path, err, tt.wantErr)
			}
		})
	}
}

func TestReplaceVersionInSpecBlock(t *testing.T) {
	t.Parallel()

	const original = `metadata:
  name: foo
  version: "9.9.9"  # this metadata version must NOT be touched
spec:
  repository: "https://github.com/owner/repo"
  ref: "abc123"
  path: "skills/foo"
  version: "0.1.0"
provenance:
  version: "1.0.0"  # also must NOT be touched
`

	updated, err := replaceVersionInSpecBlock(original, "0.2.0")
	if err != nil {
		t.Fatalf("replaceVersionInSpecBlock: %v", err)
	}

	// The spec.version line must be rewritten.
	if !strings.Contains(updated, `version: "0.2.0"`) {
		t.Errorf("updated content missing new spec.version 0.2.0\n%s", updated)
	}
	// The metadata.version and provenance.version must be untouched.
	if !strings.Contains(updated, `version: "9.9.9"`) {
		t.Errorf("metadata.version was rewritten — should be untouched\n%s", updated)
	}
	if !strings.Contains(updated, `version: "1.0.0"`) {
		t.Errorf("provenance.version was rewritten — should be untouched\n%s", updated)
	}
	// Comments must be preserved.
	if !strings.Contains(updated, "must NOT be touched") {
		t.Errorf("comments were stripped from the document\n%s", updated)
	}
}

func TestReplaceVersionInSpecBlock_NoSpecBlock(t *testing.T) {
	t.Parallel()

	_, err := replaceVersionInSpecBlock("metadata:\n  name: foo\n", "0.2.0")
	if err == nil {
		t.Errorf("expected error when no spec: block is present, got nil")
	}
}

func TestReplaceVersionInSpecBlock_NoVersionInSpec(t *testing.T) {
	t.Parallel()

	src := "spec:\n  repository: x\n  ref: y\n"
	updated, err := replaceVersionInSpecBlock(src, "0.2.0")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if updated != src {
		t.Errorf("expected source returned unchanged when no version line\nwant: %q\ngot:  %q", src, updated)
	}
}

func TestUpdateSpecVersion_RoundTrip(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	specDir := filepath.Join(dir, "skills", "test-skill")
	if err := os.MkdirAll(specDir, 0750); err != nil {
		t.Fatal(err)
	}
	specPath := filepath.Join(specDir, "spec.yaml")
	const content = `metadata:
  name: test-skill
spec:
  repository: "https://github.com/owner/repo"
  ref: "abc123"
  path: "skills/test-skill"
  version: "0.1.0"
`
	if err := os.WriteFile(specPath, []byte(content), 0600); err != nil {
		t.Fatal(err)
	}

	// updateSpecVersion uses validateSpecPath which expects "skills/" prefix.
	// We cd into the temp dir so the relative path matches.
	prevWd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = os.Chdir(prevWd) }()

	if err := updateSpecVersion("skills/test-skill/spec.yaml", "0.2.0"); err != nil {
		t.Fatalf("updateSpecVersion: %v", err)
	}

	got, err := os.ReadFile("skills/test-skill/spec.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(got), `version: "0.2.0"`) {
		t.Errorf("file does not contain new version:\n%s", got)
	}
}
