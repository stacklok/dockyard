# Skill Security Scanning Scripts

Wrappers for [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner)
used by the `Build Skill Artifacts` workflow.

## Scripts

### run_scan.py

Invokes `skill-scanner scan <source-dir> --format json` and writes the JSON
report. Exits `0` regardless of findings — allowlist filtering happens in
`process_scan_results.py`.

```bash
python3 scripts/skill-scan/run_scan.py \
  --source /path/to/skill-source \
  --output /tmp/skill-scan.json
```

Optional environment variables:

| Variable | Purpose |
|---|---|
| `SKILL_SCANNER_USE_BEHAVIORAL` | `true` enables `--use-behavioral` (AST taint tracking). |
| `SKILL_SCANNER_USE_LLM` | `true` enables `--use-llm`. Requires `SKILL_SCANNER_LLM_API_KEY`. |
| `SKILL_SCANNER_LLM_API_KEY` | API key for the LLM analyzer. |

### process_scan_results.py

Reads the scanner JSON, applies a two-tier allowlist (global + per-skill
`spec.yaml`), and exits `1` when any unallowlisted finding exists. The
`scan-summary.json` it prints to stdout is consumed by the SCAI attestation
generator and the PR report workflow.

```bash
python3 scripts/skill-scan/process_scan_results.py \
  /tmp/skill-scan.json claude-api skills/claude-api/spec.yaml \
  > scan-summary.json
```

Allowlist entries live under `security.allowed_issues[]` in a skill's
`spec.yaml`. Match by exact `rule_id` (specific) or by `category` (broader):

```yaml
security:
  allowed_issues:
    - rule_id: SOCIAL_ENG_ANTHROPIC_IMPERSONATION
      reason: "claude-api is officially from Anthropic"
    - category: social_engineering
      reason: "trusted first-party skill"
  insecure_ignore: false  # DO NOT use unless the scanner cannot run against this skill
```

Entries from `scripts/skill-scan/global_allowed_issues.yaml` apply to every
skill. Start with per-skill entries first; promote to global only when a
rule is globally a false positive across the catalog.

### generate_scai_attestation.py

Builds an in-toto SCAI predicate
([spec](https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md))
from a scan summary, targeting the OCI artifact digest. The CI workflow signs
the result with `cosign attest --type https://in-toto.io/attestation/scai/v0.3`.

```bash
python3 scripts/skill-scan/generate_scai_attestation.py \
  scan-summary.json \
  ghcr.io/stacklok/dockyard/skills/claude-api \
  sha256:0123... \
  --config-file skills/claude-api/spec.yaml \
  --commit-sha "$GITHUB_SHA" \
  --run-id "$GITHUB_RUN_ID" \
  --run-url "https://github.com/stacklok/dockyard/actions/runs/$GITHUB_RUN_ID" \
  --producer-uri https://github.com/stacklok/dockyard \
  --scanner-version 2.0.9 \
  --validate \
  --output /tmp/skill-scai.json
```

## Testing locally

```bash
# Install the scanner (one-time)
uv tool install cisco-ai-skill-scanner

# Clone the skill source the way CI does
git clone --filter=tree:0 --no-checkout https://github.com/anthropics/skills /tmp/skill-src
git -C /tmp/skill-src checkout "$(yq .spec.ref skills/claude-api/spec.yaml)"

# Scan + process
python3 scripts/skill-scan/run_scan.py \
  --source /tmp/skill-src/skills/claude-api \
  --output /tmp/skill-scan.json
python3 scripts/skill-scan/process_scan_results.py \
  /tmp/skill-scan.json claude-api skills/claude-api/spec.yaml
```

## See also

- [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner)
- Sibling pipeline: [`scripts/mcp-scan/`](../mcp-scan/README.md) — same SCAI
  attestation + allowlist pattern applied to MCP servers.
