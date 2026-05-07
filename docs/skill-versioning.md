# Skill Versioning Policy

Dockyard packages skills from external git repositories into OCI artifacts.
Because most upstream skill repositories do not publish per-skill version tags,
**Dockyard owns the semver for every vendored skill** via the `spec.version`
field in each `skills/*/spec.yaml`.

## Why spec.version matters

The build workflow (`build-skills.yml`) tags OCI images using `spec.version`:

```bash
IMAGE_REF="ghcr.io/stacklok/dockyard/skills/<name>:<spec.version>"
```

Publishing new content under the same tag would silently overwrite a pinned
image.  Every time `spec.ref` changes, `spec.version` must change too so
consumers always get what the tag promises.

## Semver rules

| Change type | What to bump | When |
|-------------|-------------|------|
| New upstream snapshot (small fixes, typos) | **patch** | Default for all `spec.ref` advances |
| New upstream snapshot with substantial changes | **minor** | See heuristic below |
| Incompatible behavior change | **major** | Manual — never auto-bumped |

## The minor-bump heuristic

`cmd/skillversionbump` runs the GitHub compare API between the old and new
`spec.ref` values, filters the diff to files inside `spec.path`, and applies
this logic (constants live in `internal/skillversion/heuristic.go`):

1. **minor** — total lines added + deleted in the skill subtree ≥ **120**
2. **minor** — `SKILL.md` is among the changed files **and** total churn ≥ **40** lines
3. **minor** — any commit in range has a `feat:` / `feat(scope):` / `feature:`
   conventional-commit prefix
4. **patch** — otherwise (default)

To tune these thresholds, edit the constants at the top of
`internal/skillversion/heuristic.go` and commit; no logic changes are needed.

## Major / breaking changes

Major bumps are **never automated**.  Reviewers should apply a major bump when:

- A tool name, argument signature, or SKILL.md frontmatter field is renamed
  or removed.
- The skill's described capabilities change in a backwards-incompatible way.
- Commit messages in the compare range include `BREAKING CHANGE:` or a `!`
  marker (e.g. `feat!: ...`).

After reviewing the diff, simply edit `spec.version` to the next major version
before merging.

## Workflow

### Renovate PRs (automated digest bumps)

1. Renovate opens a PR updating only `spec.ref` in one or more
   `skills/*/spec.yaml` files.
2. The **`skill-version-check`** CI job runs `skillversionbump --check` and
   fails because `spec.version` has not changed.
3. The **`skill-version-autofix`** job (Renovate only) runs
   `skillversionbump --write` and commits the corrected versions back to the
   branch.
4. Once both jobs pass the PR can be merged.

> **Note on workflow re-triggering:** the autofix job commits back to the PR
> branch using the default `GITHUB_TOKEN`. By design, GitHub does **not**
> trigger downstream workflows (including `skill-version-check`) for events
> created by `GITHUB_TOKEN` to prevent recursion. The check job that already
> ran on the previous commit remains the gate; the autofix commit will not
> re-run it. If you need re-triggering (e.g. to surface a new validation
> failure introduced by the auto-bump), use a PAT or GitHub App token in the
> workflow `checkout` step instead of `secrets.GITHUB_TOKEN`.

### Human PRs

If you manually change `spec.ref`, run the tool locally before pushing:

```bash
go run ./cmd/skillversionbump --base origin/main --write
```

Then commit the updated `spec.yaml` files together with your ref changes.

## Overriding the heuristic

If the tool suggests **patch** but you know the update is **minor** (or vice
versa), simply set `spec.version` to the version you want before pushing.  The
check step accepts any version that is strictly higher than the previous one;
it only rejects versions that have not been bumped at all.

```bash
# Manually set a minor bump instead of the suggested patch
# Edit skills/my-skill/spec.yaml and set version: "0.2.0", then:
git add skills/my-skill/spec.yaml
git commit -m "fix: bump my-skill to 0.2.0 (minor — adds new tool)"
```

## Local usage reference

```
Usage:
  skillversionbump [flags]

Flags:
  -b, --base string    Base git ref (SHA or branch). Default: $GITHUB_BASE_SHA or origin/main
      --write          Update spec.yaml files on disk (default: check only)
      --skip-api       Skip GitHub compare API; always apply patch bump (offline use)
      --token string   GitHub API token. Default: $GITHUB_TOKEN or $GH_TOKEN
  -s, --spec string    Specific spec.yaml path(s) to check (repeatable)
```
