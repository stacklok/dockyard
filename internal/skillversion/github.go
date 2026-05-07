package skillversion

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// compareFile represents a single file entry from the GitHub compare API.
type compareFile struct {
	Filename  string `json:"filename"`
	Additions int    `json:"additions"`
	Deletions int    `json:"deletions"`
}

// compareCommit represents a single commit entry from the GitHub compare API.
type compareCommit struct {
	Commit struct {
		Message string `json:"message"`
	} `json:"commit"`
}

// compareResponse is the subset of the GitHub compare API response we use.
type compareResponse struct {
	Files   []compareFile   `json:"files"`
	Commits []compareCommit `json:"commits"`
}

// computeSignals calls the GitHub REST compare API for the given upstream
// repository and ref range, then computes ChangeSignals filtered to the
// skillPath subtree.
//
// owner and repo are the GitHub org/repo components (e.g. "huggingface",
// "skills").  skillPath is the subdirectory prefix to filter files against
// (empty string matches all files in the repo).
//
// apiToken may be empty to make unauthenticated requests (subject to a
// much lower rate limit).
func computeSignals(ctx context.Context, apiToken, owner, repo, oldRef, newRef, skillPath string) (ChangeSignals, error) {
	cr, err := fetchCompare(ctx, apiToken, owner, repo, oldRef, newRef)
	if err != nil {
		return ChangeSignals{}, err
	}

	prefix := strings.TrimPrefix(skillPath, "/")
	if prefix != "" && !strings.HasSuffix(prefix, "/") {
		prefix += "/"
	}

	var signals ChangeSignals
	for _, f := range cr.Files {
		filename := f.Filename
		if prefix != "" && !strings.HasPrefix(filename, prefix) {
			// Check if the file exactly matches the prefix without the trailing slash
			// (e.g. skill path is "skills/foo" and file is "skills/foo/SKILL.md")
			if !strings.HasPrefix(filename, strings.TrimSuffix(prefix, "/")) {
				continue
			}
		}
		signals.TotalChange += f.Additions + f.Deletions
		base := filename
		if idx := strings.LastIndex(filename, "/"); idx >= 0 {
			base = filename[idx+1:]
		}
		if strings.EqualFold(base, "SKILL.md") {
			signals.SkillMDTouched = true
		}
	}

	for _, c := range cr.Commits {
		if IsFeatCommitMessage(c.Commit.Message) {
			signals.FeatCommit = true
			break
		}
	}

	return signals, nil
}

// parseGitHubRepo extracts the "owner" and "repo" components from a GitHub
// HTTPS URL such as "https://github.com/huggingface/skills".
func parseGitHubRepo(repositoryURL string) (owner, repo string, err error) {
	// Normalise: strip scheme and host to get the path
	s := strings.TrimPrefix(repositoryURL, "https://github.com/")
	s = strings.TrimPrefix(s, "http://github.com/")
	s = strings.TrimSuffix(s, ".git")
	parts := strings.SplitN(strings.TrimPrefix(s, "/"), "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", fmt.Errorf("cannot parse github owner/repo from URL %q", repositoryURL)
	}
	return parts[0], parts[1], nil
}

func fetchCompare(ctx context.Context, apiToken, owner, repo, oldRef, newRef string) (*compareResponse, error) {
	url := fmt.Sprintf("https://api.github.com/repos/%s/%s/compare/%s...%s", owner, repo, oldRef, newRef)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("building GitHub compare request: %w", err)
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	if apiToken != "" {
		req.Header.Set("Authorization", "Bearer "+apiToken)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("calling GitHub compare API: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("reading GitHub compare response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub compare API returned %d: %s", resp.StatusCode, body)
	}

	var cr compareResponse
	if err := json.Unmarshal(body, &cr); err != nil {
		return nil, fmt.Errorf("parsing GitHub compare response: %w", err)
	}
	return &cr, nil
}
