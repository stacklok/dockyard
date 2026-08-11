# spec.yaml Full Reference (Agent Skills)

Complete reference for Dockyard agent skill specification files. Fields are
validated by `internal/skills/spec.go` (`LoadSkillSpec`/`validateSkillSpec`)
— that file is authoritative if this reference and the code ever disagree.

## File Location

```
skills/{skill-name}/spec.yaml
```

There are no protocol subdirectories for skills (unlike MCP servers'
`npx/`/`uvx/`/`go/`) — everything lives directly under `skills/`.

## Full Schema

```yaml
# Comments documenting the skill (optional but conventional)
# Source: https://github.com/{org}/{repo}
# Will publish as: ghcr.io/stacklok/dockyard/skills/{name}:{version}

metadata:
  name: string             # Required: skill identifier — should match the
                            # directory name (lowercase, hyphens)
  description: string      # Optional but conventional: copy from upstream
                            # SKILL.md frontmatter `description`

spec:
  repository: string       # Required: HTTPS git clone URL. Must be https://
                            # — validated, non-HTTPS URLs are rejected.
  ref: string               # Required: commit SHA, tag, or branch. Always
                            # use a commit SHA in practice — a moving
                            # branch/tag breaks reproducibility and confuses
                            # skillversionbump's diff-based heuristic.
  path: string               # Optional: subdirectory within the repo
                            # containing SKILL.md. Omit if SKILL.md is at
                            # the repo root.
  version: string           # Required: Dockyard-owned semver, used as the
                            # OCI tag. New skills always start at "0.1.0"
                            # regardless of any upstream version/tag — see
                            # docs/skill-versioning.md.

provenance:                 # Optional to the parser; required for Renovate
                            # to keep spec.ref current automatically
  repository_uri: string    # Same as spec.repository, restated for clarity
  repository_ref: string    # The branch the pinned commit came from and that
                             # Renovate should follow, e.g. "refs/heads/main"

security:                   # Optional — omit entirely if the scan is clean
  allowed_issues:
    - rule_id: string        # Exact finding identifier from skill-scanner
                              # output (preferred — narrowest match)
      # category: string     # Alternative to rule_id: matches by category
                              # instead, broader — use only when many
                              # distinct rule_ids share one clear rationale
      reason: string          # Required with either rule_id or category.
                               # Must cite the specific matched text/location
                               # and explain concretely why it's not a threat.
  insecure_ignore: boolean    # Default false. NEVER set true to bypass a
                               # scan failure — it disables the security gate
                               # entirely rather than documenting findings.
                               # Reserved for cases the scanner genuinely
                               # cannot run against (rare).
```

## Derived values

- **OCI tag**: `ghcr.io/stacklok/dockyard/skills/{metadata.name}:{spec.version}` (lowercased name)
- **Git reference URI** (used internally by ToolHive's git resolver):
  `git://{host}/{path}[@{ref}][#{path}]`, built from `spec.repository`/`spec.ref`/`spec.path`

## Fields that do NOT exist (common mistakes)

- `protocol` — MCP-server-only field, meaningless for skills
- `package` / `spec.package` — MCP-server-only; skills have no package registry
- `args` / `env` — MCP-server-only (baked into the runtime container); skills
  don't run anything, they're just files
- `metadata.version` — version lives under `spec.version`, not `metadata`

## Minimal valid example

```yaml
metadata:
  name: gh-stack
  description: "Manage stacked branches and pull requests with the gh-stack GitHub CLI extension"

spec:
  repository: "https://github.com/github/gh-stack"
  ref: "14fc42ed9b6c376a53b2f999f138d3bd26dac546"
  path: "skills/gh-stack"
  version: "0.1.0"

provenance:
  repository_uri: "https://github.com/github/gh-stack"
  repository_ref: "refs/heads/main"
```
