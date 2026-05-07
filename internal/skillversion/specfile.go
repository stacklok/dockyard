package skillversion

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"

	"gopkg.in/yaml.v3"
)

// skillSpecYAML is a minimal representation of the fields we need from a
// skills/*/spec.yaml file.  It deliberately does not import internal/skills to
// keep this package independent.
type skillSpecYAML struct {
	Spec struct {
		Repository string `yaml:"repository"`
		Ref        string `yaml:"ref"`
		Path       string `yaml:"path"`
		Version    string `yaml:"version"`
	} `yaml:"spec"`
}

// readSpec loads a skill spec.yaml from disk and returns the parsed fields.
func readSpec(path string) (skillSpecYAML, error) {
	data, err := os.ReadFile(path) //#nosec G304 -- path comes from the CLI caller
	if err != nil {
		return skillSpecYAML{}, fmt.Errorf("reading %s: %w", path, err)
	}
	var s skillSpecYAML
	if err := yaml.Unmarshal(data, &s); err != nil {
		return skillSpecYAML{}, fmt.Errorf("parsing %s: %w", path, err)
	}
	return s, nil
}

// readBaseSpec reads a skill spec.yaml at a given git ref using `git show`.
// baseRef is typically a commit SHA or "origin/main".
func readBaseSpec(baseRef, path string) (skillSpecYAML, error) {
	gitArg := fmt.Sprintf("%s:%s", baseRef, path)
	out, err := exec.Command("git", "show", gitArg).Output() //#nosec G204 -- controlled args
	if err != nil {
		return skillSpecYAML{}, fmt.Errorf("git show %s: %w", gitArg, err)
	}
	var s skillSpecYAML
	if err := yaml.Unmarshal(out, &s); err != nil {
		return skillSpecYAML{}, fmt.Errorf("parsing base spec at %s: %w", gitArg, err)
	}
	return s, nil
}

// specBlockStartRe matches the start of the top-level `spec:` block.
var specBlockStartRe = regexp.MustCompile(`(?m)^spec:\s*$`)

// nextTopLevelKeyRe matches the start of any other top-level YAML key (used to
// locate the end of the spec block).
var nextTopLevelKeyRe = regexp.MustCompile(`(?m)^\S`)

// versionLineRe matches a `  version: "X.Y.Z"` line — used only inside the
// already-isolated `spec:` block, so we don't risk rewriting unrelated fields.
var versionLineRe = regexp.MustCompile(`(?m)^(\s+version:\s+)"?(\d+\.\d+\.\d+)"?`)

// updateSpecVersion rewrites the `version:` field inside the top-level `spec:`
// block of path on disk to newVersion, preserving all other content
// (including comments).  Only the first `version:` inside the spec block is
// rewritten; nested or sibling `version:` lines elsewhere in the file are
// untouched.
func updateSpecVersion(path, newVersion string) error {
	if err := validateSpecPath(path); err != nil {
		return err
	}

	cleanPath := filepath.Clean(path)
	data, err := os.ReadFile(cleanPath) //#nosec G304 -- path validated by validateSpecPath
	if err != nil {
		return fmt.Errorf("reading %s: %w", cleanPath, err)
	}

	original := string(data)
	updated, err := replaceVersionInSpecBlock(original, newVersion)
	if err != nil {
		return fmt.Errorf("%s: %w", cleanPath, err)
	}
	if updated == original {
		return fmt.Errorf("version field not found or unchanged in %s", cleanPath)
	}

	return os.WriteFile(cleanPath, []byte(updated), 0600) //#nosec G703 -- path validated above
}

// replaceVersionInSpecBlock locates the top-level `spec:` block in src and
// rewrites the first `version:` line found inside it to newVersion.  Returns
// the rewritten document.  Exposed (lowercase) for unit testing.
func replaceVersionInSpecBlock(src, newVersion string) (string, error) {
	specStart := specBlockStartRe.FindStringIndex(src)
	if specStart == nil {
		return "", fmt.Errorf("no top-level `spec:` block found")
	}
	bodyStart := specStart[1]

	// Find where the spec block ends (next top-level key, or EOF).
	rest := src[bodyStart:]
	end := len(rest)
	if nextKey := nextTopLevelKeyRe.FindStringIndex(rest); nextKey != nil {
		end = nextKey[0]
	}
	specBody := rest[:end]

	// Replace only the first `version:` line in the spec body.
	loc := versionLineRe.FindStringSubmatchIndex(specBody)
	if loc == nil {
		return src, nil
	}
	// prefix = everything before the indentation; keyPart = "  version: ";
	// suffix = everything after the original value.  We rewrite only the value
	// (always quoted) and concatenate the three slices back together.
	prefix := specBody[:loc[2]]
	keyPart := specBody[loc[2]:loc[3]]
	suffix := specBody[loc[1]:]
	newBody := prefix + keyPart + `"` + newVersion + `"` + suffix

	return src[:bodyStart] + newBody + rest[end:], nil
}

// validateSpecPath ensures path refers to a skill spec.yaml and contains no
// directory traversal components.
func validateSpecPath(path string) error {
	clean := filepath.Clean(path)
	if strings.Contains(clean, "..") {
		return fmt.Errorf("refusing to write %q: path traversal detected", path)
	}
	if !strings.HasPrefix(clean, "skills/") || !strings.HasSuffix(clean, "/spec.yaml") {
		return fmt.Errorf("refusing to write %q: must be a skills/*/spec.yaml path", path)
	}
	return nil
}

// changedSkillSpecs returns the paths of skills/*/spec.yaml files that differ
// between baseRef and HEAD using `git diff --name-only baseRef...HEAD`.
//
// The triple-dot form (merge-base) matches what build-skills.yml uses and
// avoids picking up unstaged local edits when the tool is run from a working
// tree with uncommitted changes.
func changedSkillSpecs(baseRef string) ([]string, error) {
	cmd := exec.Command( //#nosec G204 -- baseRef is from the CLI/CI env
		"git", "diff", "--name-only",
		baseRef+"...HEAD",
		"--", "skills/*/spec.yaml",
	)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		// git diff returns exit code 0 on success; any error here is real
		return nil, fmt.Errorf("git diff: %w\nstderr: %s", err, stderr.String())
	}

	var paths []string
	for _, line := range strings.Split(strings.TrimSpace(stdout.String()), "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			paths = append(paths, line)
		}
	}
	return paths, nil
}
