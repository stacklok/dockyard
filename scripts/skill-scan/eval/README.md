# skill-scanner model evaluation

Benchmarks candidate LLM models for the skill-security-scan pipeline
(context: issue #904, PR #855). The current production model is set via the
`SKILL_SCANNER_LLM_MODEL` repo variable (`anthropic/claude-sonnet-4-6`).

## Why

Two problems with the current setup:

1. **Nondeterminism.** The LLM analyzer re-flags already-reviewed content
   under rotating rule IDs, so allowlists are a moving target (#904).
2. **Latency.** Some skills take 18+ minutes to scan (claude-api burned
   ~333k input / ~69k output tokens in one scan). Wall time is dominated by
   serial LLM output generation, so a faster model directly cuts scan time.

Hypothesis: a faster/cheaper model produces similar blocking decisions on
this corpus. The current allowlists capture previously accepted findings,
but a new unallowlisted finding is not automatically noise: finding-level
review is required to distinguish scanner churn from a legitimate trust
boundary. Detection recall is measured separately on malicious fixtures.

## Leg 1: Dockyard corpus (noise / stability / latency)

```bash
python3 scripts/skill-scan/eval/bench_models.py --runs 3
```

API keys come from a `.env` in this directory (gitignored) with
`ANTHROPIC_API_KEY` and `OPENAI_API_KEY`, or from per-provider key files:
`--key-file anthropic=~/keys/anthropic openai=~/keys/openai`.

The default model matrix is the production baseline plus four candidates
(exact identifiers verified against the Anthropic and OpenAI model docs;
LiteLLM strings are provider-prefixed):

| LiteLLM model string | Role |
|---|---|
| `anthropic/claude-sonnet-4-6` | production baseline |
| `anthropic/claude-sonnet-5` | Anthropic, sonnet-tier candidate |
| `anthropic/claude-haiku-4-5` | Anthropic, small/fast candidate |
| `openai/gpt-5.6-terra` | OpenAI, sonnet-equivalent candidate |
| `openai/gpt-5.6-luna` | OpenAI, small/fast candidate |

Note the OpenAI IDs use a period in the version and a dash before the tier
(`gpt-5.6-terra`, not `gpt-5-6-terra`). Override with `--models` to run a
subset.

On prefixes: the scanner passes the model string to LiteLLM unchanged
(`llm_provider_config.py`), so OpenAI models work bare (LiteLLM's default
provider) or with the explicit `openai/` prefix. We use the prefix for
clarity; the scanner's docs showing bare `gpt-*` names are just LiteLLM's
default-provider shorthand. Two scanner behaviors the harness compensates
for: `SKILL_SCANNER_LLM_API_KEY` is the key for *any* provider (there is no
per-provider key var, hence `--key-file provider=path`), and the scanner
sends `temperature` unconditionally, which GPT-5.x models reject, so the
harness sets `SKILL_SCANNER_LLM_TEMPERATURE=none` (the scanner's
omit-the-parameter sentinel) for gpt-5* models.

The default corpus is the nine skills with the worst churn/latency history
(claude-api, find-bugs, pulumi-upgrade-provider, provider-upgrade,
huggingface-paper-publisher, codeql, semgrep, supply-chain-risk-auditor,
zeroize-audit). Each skill is scanned at the exact `spec.ref` pinned in its
spec.yaml, with `SKILL_SCANNER_LLM_TEMPERATURE=0.0`, using the same
`run_scan.py` flags as CI.

Metrics per skill x model (see `summary.md` in the results dir):

- **Blocking/run**: findings not covered by the current allowlist. This is
  the "PR fails CI again" event and measures operational churn. Inspect the
  findings before calling them false positives.
- **HIGH+ noise/run**: blocking findings with the allowlist disabled, i.e.
  total triage burden a maintainer would face from scratch.
- **LLM stability**: mean pairwise Jaccard similarity of the LLM-analyzer
  finding sets across repetitions. 1.0 = deterministic.
- **Mean time / output tokens**: scan latency and its main driver.

## Leg 2: detection recall (scanner's own ground-truth corpus)

Dockyard has no known-malicious skills, so recall must come from the
scanner's eval framework, which ships curated malicious/safe skills with
`_expected.json` ground truth:

```bash
git clone --branch 2.0.13 --depth 1 \
  https://github.com/cisco-ai-defense/skill-scanner \
  scripts/skill-scan/eval/results/recall-source-2.0.13

python3 scripts/skill-scan/eval/bench_recall.py \
  --scanner-source scripts/skill-scan/eval/results/recall-source-2.0.13 \
  --models anthropic/claude-sonnet-4-6 openai/gpt-5.6-terra \
  --runs 3
```

Do not use the scanner's bundled `benchmark_runner.py` for a model
comparison: in scanner 2.0.13 it constructs `SkillScanner()` with the core
analyzers only and does not enable the LLM or meta analyzers. `bench_recall.py`
instead sends every fixture through Dockyard's production `run_scan.py` path.

The recall summary reports fixture-level blocking decisions, safe-fixture
false positives, expected-category coverage at any severity and at HIGH+,
wall time, and token usage. A candidate must preserve fixture-level malicious
and safe decisions; severity/category differences should then be reviewed.

## Decision criteria

Prefer the cheapest/fastest model that, relative to `claude-sonnet-4-6`:

- preserves malicious/safe fixture-level decisions on the recall corpus,
- has acceptable LLM stability and operational blocking churn,
- does not introduce materially worse finding-level false positives,
- and cuts p95 scan latency meaningfully.

Aggregate counts are screening metrics, not a substitute for reviewing the
actual findings. A candidate can report more blockers because it catches a
real execution boundary, or fewer blockers because it misses one.

## Evaluation records

- [`reports/2026-08-26-sonnet-4.6-vs-terra.md`](reports/2026-08-26-sonnet-4.6-vs-terra.md)
  records the initial Sonnet 4.6 versus GPT-5.6 Terra shootout.

Orthogonal knobs worth testing in the same harness (both from #904):

- `--consensus-runs 3` (majority vote inside the LLM analyzer; ~3x cost,
  may let a cheap model match sonnet's stability at lower total cost)
- temperature pinning (already defaulted to 0.0 here)
