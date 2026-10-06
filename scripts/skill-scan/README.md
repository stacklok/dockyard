# Skill Security Scanning Scripts

Wrappers for [Cisco AI Defense skill-scanner](https://github.com/cisco-ai-defense/skill-scanner)
used by the `Build Skill Artifacts` workflow.

## Scripts

### run_scan.py

Invokes `skill-scanner scan <source-dir> --format json` and writes the JSON
report. Exits `0` regardless of findings — allowlist filtering happens in
`process_scan_results.py`. Exits `1` if the scan can't run, including when
`SKILL_SCANNER_USE_LLM=true` but no API key is set.

The wrapper hard-codes the free/in-tree analyzers and scan policy we always want:

- `--rule-packs promptguard` - Anthropic/OpenAI key detection and markdown
  exfiltration signatures. Like ATR, PromptGuard is an opt-in pack that isn't
  part of upstream's measured setups. We keep it because its findings are
  identical every run. If its PII "credential harvesting" rules keep needing
  allowlist entries, consider a custom policy that lowers just those rules to
  MEDIUM while leaving secret detection and exfiltration rules alone.
  The ATR pack is intentionally not enabled: its regex rules produced almost
  all HIGH+ false positives across the catalog, and upstream ATR marks its
  skill-targeted rules as not ready for gating.
- `--policy quiet` - upstream's lowest-FPR preset for vetted third-party
  skills. Demotes noisy rules to LOW and caps low-confidence and
  contextual-risk LLM findings at LOW. Upstream's recall numbers for it assume
  someone reviews MEDIUM findings, which is why the PR scan comment lists them
  (not blocking).
- `--use-trigger` — vague-description / capability-inflation detector.
- `--use-behavioral` — AST + dataflow taint analysis (Python and Bash).

```bash
python3 scripts/skill-scan/run_scan.py \
  --source /path/to/skill-source \
  --output /tmp/skill-scan.json
```

Optional environment variables:

| Variable | Purpose |
|---|---|
| `SKILL_SCANNER_USE_LLM` | `true` enables `--use-llm`. Requires `SKILL_SCANNER_LLM_API_KEY`. The meta-analyzer (`--enable-meta`) is intentionally off because it made the blocking decision nondeterministic. |
| `SKILL_SCANNER_LLM_API_KEY` | API key for the LLM analyzer (works for OpenAI/Anthropic/Azure/Bedrock/Vertex/Gemini/OpenRouter via LiteLLM). |
| `SKILL_SCANNER_LLM_MODEL` | Model id (e.g. `anthropic/claude-sonnet-4-20250514`, `ollama/llama3`). Defaults to the scanner's built-in model. |
| `SKILL_SCANNER_LLM_CONSENSUS_RUNS` | Integer >1 enables majority-vote consensus across N LLM runs. Multiplies LLM cost; off by default. |
| `SKILL_SCANNER_POLICY` | Overrides the `quiet` policy preset (e.g. `balanced`). For the eval harness; CI doesn't set it. |

### process_scan_results.py

Reads the scanner JSON, applies a two-tier allowlist (global + per-skill
`spec.yaml`), and exits `1` when any unallowlisted finding exists. With
`SKILL_SCANNER_USE_LLM=true` it also exits `1` when the LLM judge didn't run
or failed, since the judge's own failure markers are INFO findings that would
otherwise let a skill pass on rules alone. Files the judge skipped for size
(`LLM_CONTEXT_BUDGET_EXCEEDED`) don't fail the scan; they're recorded under
`judge` in the summary and listed in the PR comment for manual review. The
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
