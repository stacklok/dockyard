# Adding Skills to Dockyard

This guide walks you through packaging and contributing an agent skill
to Dockyard.

## Overview

Unlike MCP servers (built from an npm/PyPI/Go package into a container),
skills are packaged directly from a git repository: Dockyard clones the
upstream repo at a pinned commit, validates the `SKILL.md` at the given
path, and repackages that directory as an OCI artifact.

Adding a skill is simple:
1. Create a `spec.yaml` configuration file
2. Submit a pull request
3. CI/CD automatically validates, scans, and publishes the skill artifact

## Directory Structure

```
skills/{skill-name}/spec.yaml
```

There is a single `skills/` directory (no protocol subdirectories like
`npx/`/`uvx/`/`go/` — those apply only to MCP servers).

### Naming

Pick `{skill-name}` to be collision-safe in a single flat namespace shared
by 150+ skills from many upstream sources:

- If the upstream skill's own name is already specific (`claude-api`,
  `gh-stack`), use it as-is.
- If the upstream repo ships several skills whose names are generic on
  their own (e.g. `provider-docs`, `windows-builder`), prefix all of them
  with a short vendor tag, e.g. `hashicorp-provider-docs`,
  `dd-apm` (Datadog), `hf-cli` (Hugging Face). Prefer a single flat prefix
  over splitting by upstream sub-project — it avoids awkward stutter when
  a skill's own name already contains the sub-project name (e.g.
  `hashicorp-terraform-test`, not `hashicorp-terraform-terraform-test`).
- Check for an existing name collision before picking one:
  `ls skills/ | grep -x '{candidate-name}'`.

## spec.yaml Reference

```yaml
# {Skill Name} Skill
# Source: {source-repository-url}
# Will publish as: ghcr.io/stacklok/dockyard/skills/{name}:{version}

metadata:
  name: {skill-name}                # Required: must match the directory name
  description: "{brief description}" # Optional but recommended: copy from the
                                       # upstream SKILL.md frontmatter `description`

spec:
  repository: "{https-git-clone-url}" # Required: HTTPS clone URL
  ref: "{commit-sha}"                  # Required: pinned commit (not a moving
                                        # branch/tag — see "Pinning the ref" below)
  path: "{path-to-skill-dir}"          # Optional: subdirectory containing
                                        # SKILL.md; omit if SKILL.md is at repo root
  version: "0.1.0"                     # Required: Dockyard-owned semver —
                                        # see docs/skill-versioning.md

provenance:
  repository_uri: "{https-git-clone-url}"
  repository_ref: "refs/heads/{branch}" # The branch/ref the pinned commit came from

security:
  allowed_issues:
    - rule_id: "{RULE_ID}"              # From the skill-scanner report
      reason: "FP: ..."                 # Why this finding is a false positive
                                         # or an accepted risk — see "Security
                                         # Scanning" below
```

### Pinning the ref

`spec.ref` must be a commit SHA, not a branch or tag — this is what makes
the build reproducible. Get the current HEAD of the branch you want to
track:

```bash
git ls-remote https://github.com/{org}/{repo} HEAD
```

Renovate keeps `spec.ref` current automatically once the skill is added
(see `renovate.json`); you generally only need to pin it once, at
creation time.

### version

Dockyard owns the semver for every vendored skill independently of
upstream — most upstream skill repos don't tag individual skills, and even
when they cut a repo-wide release, it doesn't map cleanly onto one skill's
changes. Start a new skill at `0.1.0` regardless of any upstream version or
release tag. See [Skill Versioning](skill-versioning.md) for the full
policy and the tooling that bumps this automatically as `spec.ref`
advances.

## Local Testing

Build the CLI once:

```bash
task build-setup
```

Then, for a given skill:

```bash
# Validate spec.yaml and SKILL.md (fast, no scan)
task validate-skill -- skills/{skill-name}

# Run skill-scanner and apply the security allowlist
task scan-skill -- skills/{skill-name}

# Build the OCI artifact locally (dry run, no push)
task build-skill -- skills/{skill-name}

# Build and push (requires registry auth — CI does this, not typically local)
PUSH=true task build-skill -- skills/{skill-name}
```

`task scan-skill` requires the scanner once per machine:

```bash
task scan-skill-setup   # uv tool install cisco-ai-skill-scanner
```

## Security Scanning

Every skill is scanned with
[Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner)
before packaging. This is **blocking**: any finding at or above `HIGH`
severity that isn't allowlisted fails the build.

Skill documentation is prose-heavy and full of code examples, so
keyword/pattern rules produce a lot of false positives — shell variable
expansion in documented setup commands (`${TOKEN}`, `$HOME`), install
one-liners (`curl -L .../pup`, `sudo apt-get install`, a vendor's official
Chocolatey/PowerShell bootstrap), example IP addresses, and placeholder
credential values in setup docs are the most common triggers, not real
threats.

When `task scan-skill` reports an unallowlisted finding:

1. Read the finding's `file_path`/`line_number` in the skill's actual
   source (clone it at the pinned `ref` if you need full context).
2. Decide if it's a genuine issue or a false positive / accepted risk.
3. If it's a false positive or an accepted risk, add it to
   `security.allowed_issues` in the skill's `spec.yaml`, matching by
   `rule_id` (exact) or `category` (broader). Every entry needs a `reason`
   that cites the specific matched text/location and explains why it's
   safe — see any existing `skills/*/spec.yaml` for the house style, e.g.:

   ```yaml
   security:
     allowed_issues:
       - rule_id: ATR_2026_00066
         reason: "FP: matched shell variable expansion (`${TOKEN}`) in a
           documented setup command (SKILL.md:45) — standard shell syntax,
           not injected secrets."
   ```

4. Re-run `task scan-skill -- skills/{skill-name}` until it passes.

Never set `security.insecure_ignore: true` to work around a scan failure —
it disables the gate entirely rather than documenting why each finding is
safe. See `scripts/skill-scan/README.md` for the scanner wrapper scripts
and `scripts/skill-scan/global_allowed_issues.yaml` for issues allowlisted
across every skill (promote a per-skill entry there only once you've seen
the same false positive recur across unrelated skills).

## What CI Does

On every PR touching `skills/**/*.yaml`, `.github/workflows/build-skills.yml`:

1. **Validates** the spec and `SKILL.md` (`validate-skills` job)
2. **Scans** the pinned source with skill-scanner and applies the
   allowlist (`skill-security-scan` job) — this is the blocking security
   gate
3. **Builds** the OCI artifact as a dry run (no push on PRs)

On merge to `main`, it additionally pushes the artifact to
`ghcr.io/stacklok/dockyard/skills/{name}:{version}`, signs it with
Cosign, and attests SBOM, build provenance, and a SCAI-format security
scan predicate — the same supply-chain guarantees MCP server containers
get. See [Security Overview](security.md) and
[Container Attestations](attestations.md).

A change to `spec.ref` without a corresponding `spec.version` bump fails
the `skill-version-check` CI job — see
[Skill Versioning](skill-versioning.md) for why and how the bump is
computed.

## Commit and PR

```bash
git add skills/{skill-name}/spec.yaml
git commit -s -m "Add {skill-name} skill

Package {skill-name} from {upstream-repo} at {commit-sha}.
Source: {upstream-repo-url}"
```

Include in your PR description what the skill does and a link to its
upstream source, same as an MCP server PR (see
[CONTRIBUTING.md](../CONTRIBUTING.md)).

## See Also

- [Skill Versioning](skill-versioning.md) — semver policy and auto-bump tooling
- [Security Overview](security.md) — scanning and attestation model
- `.claude/skills/package-skill/` (also at `.agents/skills/package-skill/`) —
  a skill that automates this entire workflow (spec.yaml authoring,
  scanning, allowlist triage)
- [Adding MCP Servers](adding-servers.md) — the equivalent guide for MCP
  server containers
