package skillversion

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestParseGitHubRepo(t *testing.T) {
	t.Parallel()

	const (
		owner = "owner"
		repo  = "repo"
	)

	tests := []struct {
		name      string
		input     string
		wantOwner string
		wantRepo  string
		wantErr   bool
	}{
		{"https url", "https://github.com/huggingface/skills", "huggingface", "skills", false},
		{"https with .git suffix", "https://github.com/owner/repo.git", owner, repo, false},
		{"https with trailing slash", "https://github.com/owner/repo/", owner, repo, false},
		{"http url", "http://github.com/owner/repo", owner, repo, false},
		{"trailing slash with no repo is rejected", "https://github.com/owner/", "", "", true},
		{"missing repo", "https://github.com/owner", "", "", true},
		{"non-github host rejected", "https://gitlab.com/owner/repo", "", "", true},
		{"empty input", "", "", "", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			owner, repo, err := parseGitHubRepo(tt.input)
			if (err != nil) != tt.wantErr {
				t.Fatalf("parseGitHubRepo(%q) err = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if !tt.wantErr && (owner != tt.wantOwner || repo != tt.wantRepo) {
				t.Errorf("parseGitHubRepo(%q) = (%q, %q), want (%q, %q)",
					tt.input, owner, repo, tt.wantOwner, tt.wantRepo)
			}
		})
	}
}

// fakeCompareServer returns an httptest server that serves a canned
// /repos/.../compare/... payload built from the given files and commits.
func fakeCompareServer(t *testing.T, files []compareFile, commits []compareCommit) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.URL.Path, "/compare/") {
			http.Error(w, "unexpected path", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(compareResponse{Files: files, Commits: commits})
	}))
}

// rewriteClient returns an *http.Client that rewrites all outgoing requests
// to hit the test server, regardless of the URL the SUT constructs.
func rewriteClient(targetURL string) *http.Client {
	return &http.Client{Transport: rewriteTransport{target: targetURL}}
}

func TestComputeSignals_PrefixFilterScopesToSubtree(t *testing.T) {
	t.Parallel()

	// Files: one inside spec.path "skills/foo", one in a sibling
	// "skills/foo-extra" that must NOT be counted.
	files := []compareFile{
		{Filename: "skills/foo/SKILL.md", Additions: 30, Deletions: 5},
		{Filename: "skills/foo/scripts/run.sh", Additions: 10, Deletions: 0},
		{Filename: "skills/foo-extra/SKILL.md", Additions: 999, Deletions: 999}, // sibling — must be ignored
		{Filename: "README.md", Additions: 1, Deletions: 0},                     // out of subtree
	}
	srv := fakeCompareServer(t, files, nil)
	defer srv.Close()

	signals, err := computeSignals(
		context.Background(),
		rewriteClient(srv.URL),
		"", "owner", "repo", "old", "new", "skills/foo",
	)
	if err != nil {
		t.Fatalf("computeSignals: %v", err)
	}

	wantTotal := 30 + 5 + 10 + 0
	if signals.TotalChange != wantTotal {
		t.Errorf("TotalChange = %d, want %d (sibling subtree must not be counted)", signals.TotalChange, wantTotal)
	}
	if !signals.SkillMDTouched {
		t.Errorf("SkillMDTouched = false, want true")
	}
	if signals.FeatCommit {
		t.Errorf("FeatCommit = true, want false (no commits in fixture)")
	}
}

func TestComputeSignals_FeatCommitDetected(t *testing.T) {
	t.Parallel()

	commits := []compareCommit{
		{Commit: struct {
			Message string `json:"message"`
		}{Message: "fix: small typo"}},
		{Commit: struct {
			Message string `json:"message"`
		}{Message: "feat(tools): add new tool"}},
	}
	srv := fakeCompareServer(t, nil, commits)
	defer srv.Close()

	signals, err := computeSignals(
		context.Background(),
		rewriteClient(srv.URL),
		"", "owner", "repo", "old", "new", "skills/foo",
	)
	if err != nil {
		t.Fatalf("computeSignals: %v", err)
	}
	if !signals.FeatCommit {
		t.Errorf("FeatCommit = false, want true (one commit has feat: prefix)")
	}
}

// rewriteTransport rewrites every outgoing request to use the host of `target`.
type rewriteTransport struct {
	target string
}

func (rt rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	parsed, err := http.NewRequest(req.Method, rt.target+req.URL.Path, req.Body)
	if err != nil {
		return nil, err
	}
	parsed.Header = req.Header
	return http.DefaultTransport.RoundTrip(parsed)
}
