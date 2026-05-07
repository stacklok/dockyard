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

// versionLineRe matches a `  version: "X.Y.Z"` line inside a spec.yaml.
// It handles both quoted ("X.Y.Z") and bare (X.Y.Z) values.
var versionLineRe = regexp.MustCompile(`(?m)^(\s+version:\s+)"?(\d+\.\d+\.\d+)"?`)

// updateSpecVersion rewrites the `version:` field inside the spec block of
// path on disk to newVersion, preserving all other content (including
// comments).
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
	updated := versionLineRe.ReplaceAllStringFunc(original, func(match string) string {
		// Preserve the indentation + key portion, replace only the value.
		sub := versionLineRe.FindStringSubmatch(match)
		if len(sub) < 3 {
			return match
		}
		return sub[1] + `"` + newVersion + `"`
	})

	if updated == original {
		return fmt.Errorf("version field not found or unchanged in %s", cleanPath)
	}

	return os.WriteFile(cleanPath, []byte(updated), 0600) //#nosec G703 -- path validated above
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
// between baseRef and HEAD using `git diff --name-only`.
func changedSkillSpecs(baseRef string) ([]string, error) {
	cmd := exec.Command("git", "diff", "--name-only", baseRef, "--", "skills/*/spec.yaml") //#nosec G204
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
