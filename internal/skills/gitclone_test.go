package skills

import "testing"

func TestValidateGitPath(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		path    string
		wantErr bool
	}{
		{name: "empty root", path: ""},
		{name: "nested skill", path: "skills/next-dev-loop"},
		{name: "traversal", path: "skills/../secret", wantErr: true},
		{name: "absolute", path: "/etc/passwd", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			err := validateGitPath(tt.path)
			if tt.wantErr && err == nil {
				t.Fatalf("expected error for path %q", tt.path)
			}
			if !tt.wantErr && err != nil {
				t.Fatalf("unexpected error for path %q: %v", tt.path, err)
			}
		})
	}
}
