# AGENTS.md

Guidance for AI coding agents working in this repository. Human contributors
should read [CONTRIBUTING.md](CONTRIBUTING.md) instead — this file is a
terser, agent-facing summary of the same conventions plus the exact commands
to run.

## What this repo is

Dockyard packages two different kinds of things into signed OCI artifacts
published to `ghcr.io/stacklok/dockyard`:

- **MCP servers** — built from an npm/PyPI/Go package into a container image.
  Live under `npx/`, `uvx/`, `go/`.
- **Agent skills** — repackaged directly from a pinned commit in an upstream
  git repository (no build step, no code compiled). Live under `skills/`.

Each of the two has its own CLI subcommand set (`cmd/dockhand`), spec
validation/build logic (MCP server spec types live in
`cmd/dockhand/main.go`; skill spec types live in `internal/skills/`),
Taskfile task family, GitHub Actions workflow, and scanner. Don't assume
something true of one applies to the other — check which one you're
touching first.

## Adding something

- New MCP server → [docs/adding-servers.md](docs/adding-servers.md)
- New agent skill → [docs/adding-skills.md](docs/adding-skills.md), or drive
  it with the packaged skill at `.claude/skills/package-skill/SKILL.md`
  (also reachable agent-agnostically at `.agents/skills/package-skill/`,
  a symlink to `.claude/skills/`)

Both are `spec.yaml`-driven: create `{npx,uvx,go}/{name}/spec.yaml` or
`skills/{name}/spec.yaml` and open a PR. Neither requires writing application
code — this repo has almost no runtime logic of its own beyond the `dockhand`
CLI and the CI scripts that drive it.

## Build and test

```bash
go build -o build/dockhand ./cmd/dockhand   # or: task build-setup
go test ./...
```

There is no lint/format task wired into Taskfile beyond what `go build`/
`go vet` catch; run `gofmt -l .` before committing Go changes.

## Local verification commands

MCP servers:

```bash
task scan-setup                                  # once per machine: installs mcp-scanner
task build -- {protocol}/{server-name}          # generate Dockerfile
task scan -- {protocol}/{server-name}            # mcp-scanner
task test-build -- {protocol}/{server-name}      # full build + smoke test
./build/dockhand verify-provenance -c {protocol}/{server-name}/spec.yaml -v
```

Agent skills:

```bash
task scan-skill-setup                            # once per machine: installs skill-scanner
task validate-skill -- skills/{skill-name}       # clone + validate SKILL.md, no scan
task scan-skill -- skills/{skill-name}           # skill-scanner
task build-skill -- skills/{skill-name}          # build OCI artifact (dry run, no push)
```

Both scanners are **blocking**: an unallowlisted finding at or above the
block-severity threshold fails CI. Never work around a failing scan by
setting `security.insecure_ignore: true` — triage the finding and add a
`security.allowed_issues` entry with a specific `reason`, or fix the actual
issue. See [docs/security.md](docs/security.md) for the full model.

## Skill versioning — read before touching `spec.ref`

Dockyard owns semver for vendored skills independently of upstream via
`spec.version`. Bumping `spec.ref` without bumping `spec.version` fails CI
(`skill-version-check`). If you change `spec.ref` by hand, run:

```bash
go run ./cmd/skillversionbump --base origin/main --write
```

Full policy: [docs/skill-versioning.md](docs/skill-versioning.md).

## Conventions

- **Commits**: DCO Signed-off-by trailer required (`git commit -s`). Subject
  line imperative mood, ≤50 chars, capitalized, no trailing period. See
  [CONTRIBUTING.md](CONTRIBUTING.md#commit-message-guidelines).
- **Naming collisions**: `skills/` is a single flat namespace shared by 150+
  vendored skills. If an upstream repo's skill names are generic on their
  own (`provider-docs`, `windows-builder`), prefix all of them with a short
  vendor tag (`hashicorp-provider-docs`) rather than splitting per
  upstream sub-project — that avoids stutter when a skill's own name already
  contains the sub-project name.
- **Don't hand-roll spec.yaml semantics** — read `internal/skills/spec.go`
  (skills) or the spec types in `cmd/dockhand/main.go` (MCP servers) for the
  fields that are actually validated before inventing new ones.
- **CI workflow gotcha**: `build-skills.yml` only rebuilds *changed* skills
  on a normal push/PR, but rebuilds *all* ~160 skills when `cmd/dockhand/`,
  `internal/skills/`, or a `stacklok/toolhive` bump in `go.mod`/`go.sum`
  changes — because those are the inputs that can alter every built
  artifact. Keep that in mind before touching those paths on a whim; it
  fans out into a large CI run.
