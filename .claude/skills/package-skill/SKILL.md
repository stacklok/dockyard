---
name: package-skill
description: Creates spec.yaml configurations for packaging agent skills as OCI artifacts. Use when adding a new agent skill to Dockyard, creating a skills/*/spec.yaml file, or vendoring a third-party skill repository (e.g. from Anthropic, Datadog, HashiCorp, Hugging Face). Not for writing a brand-new skill's own content, or for MCP server packaging (use package-mcp-server for that).
---

# Package Agent Skill for Dockyard

This skill helps you package agent skills for distribution via Dockyard skill artifacts (OCI artifacts published to `ghcr.io/stacklok/dockyard/skills/{name}`).

Unlike MCP servers — which Dockyard builds into container images from an npm/PyPI/Go package — skills are repackaged directly from a pinned commit in the upstream skill's git repository. There's no build step; `dockhand` clones the repo, validates `SKILL.md`, and repackages that directory as-is.

## When to Use This Skill

Use this skill when:
- Adding a new agent skill to Dockyard
- Creating a `skills/{name}/spec.yaml` configuration file
- Vendoring one or more skills from a third-party repository
- The user mentions "package skill", "add skill", "skills spec.yaml", or asks to package skills from a named GitHub org/repo

## Prerequisites

- The skill's `SKILL.md` must exist in a public git repository, reachable over HTTPS
- `go build -o build/dockhand ./cmd/dockhand` (or `task build-setup`) for local validate/build
- `task scan-skill-setup` (installs `cisco-ai-skill-scanner` via `uv`) for local scanning

## Workflow

### Step 1: Discover the skill(s)

If packaging from a repo the user names, clone it shallow and enumerate candidate `SKILL.md` files:

```bash
git clone --depth 1 https://github.com/{org}/{repo} /tmp/{repo}
find /tmp/{repo} -iname SKILL.md
```

Treat the results as candidates, not an automatic package list: exclude test
fixtures, examples, and templates that are not intended for end users. For each
real skill, read its YAML frontmatter (`name`, `description`, and any
`license`/`version` fields). The upstream description is the source of truth
for `metadata.description`.

#### Verify redistribution rights

Before creating any specs, find an explicit license that covers the skill
content. Check the skill directory and repository root for `LICENSE`/`COPYING`
files and inspect any SPDX-style `license:` value in `SKILL.md` frontmatter.
The license must grant the rights needed to copy, modify, and redistribute the
skill in a public OCI artifact.

Public source is not the same as open source. A repository with no license is
not eligible for packaging unless the copyright holder separately grants the
necessary redistribution rights. Likewise, a link to product, API, developer,
or website terms is not sufficient unless those terms explicitly license the
repository content for redistribution. If the license is missing, ambiguous,
or non-redistributable, stop and surface the issue to the user rather than
creating specs.

Record the license and where it was found in the PR description. If
skill-scanner later reports `MANIFEST_MISSING_LICENSE` because the license is
at the repository root rather than in `SKILL.md`, cite that verified license in
the allowlist reason.

Get the pinned commit SHA once, up front, and reuse it for every skill from that repo:

```bash
git -C /tmp/{repo} rev-parse HEAD
```

### Step 2: Decide names — check for collisions

`skills/` is a single flat namespace shared by 150+ skills from many upstream sources. Before naming anything:

```bash
ls skills/ | grep -x '{candidate-name}'
```

- If the skill's own upstream name is already specific and unlikely to collide (`claude-api`, `gh-stack`), use it as-is.
- If the repo ships **multiple** skills whose names are generic on their own (e.g. `provider-docs`, `windows-builder`, `push-to-registry`), prefix **all** of them with a short vendor tag: `hashicorp-provider-docs`, `dd-apm` (Datadog), `hf-cli` (Hugging Face).
- Prefer a single flat vendor prefix over splitting by upstream sub-project (e.g. `hashicorp-` alone, not separate `hashicorp-terraform-`/`hashicorp-packer-` prefixes) — splitting produces stutter whenever a skill's own name already contains the sub-project name (`hashicorp-terraform-terraform-test` reads worse than `hashicorp-terraform-test`).
- If there's any ambiguity in naming (flat vendor prefix vs. per-subproject, or no prefix at all), **ask the user** before creating two dozen directories — renaming later means re-running the whole scan/allowlist pass.

### Step 3: Create spec.yaml

One directory per skill: `skills/{name}/spec.yaml`.

```yaml
# {Skill Name} Skill
# Source: {source-repository-url}
# Will publish as: ghcr.io/stacklok/dockyard/skills/{name}:0.1.0

metadata:
  name: {name}
  description: "{copy verbatim from upstream SKILL.md frontmatter description}"

spec:
  repository: "{https-git-clone-url}"
  ref: "{commit-sha}"  # {branch} as of {date} — pin an exact commit, never a branch
  path: "{path-to-skill-dir}"  # omit entirely if SKILL.md is at repo root
  version: "0.1.0"  # ALWAYS 0.1.0 for a new skill — see Step 4

provenance:
  repository_uri: "{https-git-clone-url}"
  repository_ref: "refs/heads/{branch}"  # Renovate follows this branch
```

Long `description` values often need YAML block scalars (`>-` or a quoted
multi-line string) — let a YAML dumper handle escaping rather than hand-
wrapping; malformed quoting is the most common review-round-trip bug here.

### Step 4: Version — always start at 0.1.0

Do **not** copy an upstream release tag (e.g. a repo-wide `v1.0.0`) into `spec.version`, even if one exists. Dockyard owns semver for every vendored skill independently of upstream (see `docs/skill-versioning.md`) specifically because:
- Most upstream skill repos don't tag individual skills at all.
- Even when a repo does cut a release, it's typically a whole-repo tag that doesn't map to any single skill's actual changes — and several individual `SKILL.md` frontmatter blocks often carry their own, much lower, per-skill `version` (e.g. `0.0.1`, `0.1.0`) that would contradict a `1.0.0` Dockyard tag anyway.

Every new skill starts at `0.1.0`. If this comes up with the user, it's worth surfacing as a quick recommendation rather than silently picking one — but the answer is almost always 0.1.0.

### Step 5: Validate

```bash
build/dockhand validate-skill --config skills/{name}/spec.yaml
```

Fix any error before moving on — this clones the repo and actually checks `SKILL.md` exists at the given path.

### Step 6: Scan and triage findings

```bash
task scan-skill-setup   # once per machine
task scan-skill -- skills/{name}
```

This is the expensive, judgment-heavy step. Read `scripts/skill-scan/README.md` if you haven't already. What to expect:

- **Warnings** (below the `HIGH` block threshold) don't fail the task — you can leave them, though citing the intentionally-accepted ones (like `MANIFEST_MISSING_LICENSE` when the upstream repo has a root-level `LICENSE` but no per-skill frontmatter field) in the allowlist keeps the scan summary self-documenting.
- **Blocking findings** (`HIGH`+, unallowlisted) fail the task and must be triaged one by one.

For each blocking finding, look at its `file_path`/`line_number`/`message` and decide: genuine issue, or false positive? Skill docs are prose- and example-heavy, so the overwhelming majority are false positives from pattern/keyword rules matching on things like:
- Shell variable expansion (`${TOKEN}`, `$HOME`) in documented setup commands
- Documented, vendor-official install one-liners (`curl -L .../release`, `sudo apt-get install`, an official Chocolatey/PowerShell bootstrap)
- Example IP addresses, placeholder credentials (`CLIENT_SECRET="your-secret"`), or attribute names like `password` in schema/code examples
- Words like "exfil", "override", "skip", "kill", "root" appearing in ordinary explanatory prose, not as an executable instruction

Add each as a `security.allowed_issues` entry, matching by `rule_id` (exact — prefer this) or `category` (broader, only when many distinct rule_ids share one clear rationale). **Every reason must cite the specific matched text and its file:line**, and explain concretely why it isn't a threat — not just "false positive":

```yaml
security:
  allowed_issues:
    - rule_id: ATR_2026_00066
      reason: "FP: matched shell variable expansion (\`${TOKEN}\`) in a
        documented setup command (SKILL.md:45) — standard shell syntax,
        not injected secrets."
```

When packaging many skills from the same repo, findings cluster heavily by `rule_id` — collect all blocking findings across the batch first (group by skill + rule_id), write one templated-but-specific reason per rule_id, then customize per skill using that skill's actual matched text. Don't reuse a reason verbatim across skills without checking the cited location actually matches what's in *that* skill — genuinely different constructs can share a rule_id (e.g. an `iex (...)` PowerShell bootstrap vs. a `sudo apt-get install` line both trip the same "documented install command" rule but need different citations).

Never set `security.insecure_ignore: true` to bypass this — it disables the gate rather than documenting the finding.

Re-run `task scan-skill -- skills/{name}` until it exits clean. Repeat for every skill in the batch.

### Step 7: Build (smoke test)

```bash
build/dockhand build-skill --config skills/{name}/spec.yaml
```

No `--push` needed locally — this just proves the artifact packages successfully end to end. Doing this for at least one representative skill in a batch is enough; running it for all of them is optional but cheap.

### Step 8: Commit

```bash
git add skills/{name}/spec.yaml
git commit -s -m "Add {name} skill

Package {name} from {upstream-repo} at {commit-sha}.
Source: {upstream-repo-url}"
```

Use `git commit -s` — DCO Signed-off-by is required (see `CONTRIBUTING.md`). For a batch of skills from one repo, one commit covering all of them is fine.

## Common Issues

| Issue | Solution |
|-------|----------|
| `validate-skill` fails: SKILL.md not found | Double check `spec.path` — it's relative to the repo root, not to `skills/{name}/` |
| `scan-skill` times out on a large batch | Run it per-skill in a loop rather than one long-running batch command; each clone+scan takes 5-15s |
| Same `rule_id` fires for unrelated reasons across skills | Verify the actual matched text before reusing a reason — don't copy-paste blind |
| Version bump CI failure after editing `spec.ref` later | Run `go run ./cmd/skillversionbump --base origin/main --write` — see `docs/skill-versioning.md` |
| Tempted to set `insecure_ignore: true` | Don't. Triage the finding instead, or ask the user if it's a genuine risk to accept explicitly with a reason |

## See Also

- [docs/adding-skills.md](../../../docs/adding-skills.md) — Complete contribution guide
- [docs/skill-versioning.md](../../../docs/skill-versioning.md) — Why version always starts at 0.1.0
- [docs/security.md](../../../docs/security.md) — Security scanning and attestation model
- `scripts/skill-scan/README.md` — Scanner wrapper scripts and allowlist mechanics
- [internal/skills/spec.go](../../../internal/skills/spec.go) — The actual validated spec.yaml fields
- [references/SPEC-YAML-REFERENCE.md](references/SPEC-YAML-REFERENCE.md) — Full spec.yaml field reference
