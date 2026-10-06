# Skill scanner gate evaluation: meta-analyzer + ATR vs `quiet` and `balanced`

Date: 2026-10-06

Tracking issue: [#1047](https://github.com/stacklok/dockyard/issues/1047)

## Decision

Gate on `--policy quiet` with the LLM judge, no meta-analyzer, and no ATR
rule pack. Against the scanner's own labelled test skills, this blocked
every malicious case in every run, where the previous configuration missed
almost a third. `balanced` matched `quiet` on recall here and gave identical
results on a sample of Dockyard skills, so there's no measured reason yet to
prefer it.

## Configuration

- Scanner: `cisco-ai-defense/skill-scanner` 2.2.0
- Model: `openai/gpt-5.6-terra`, consensus off, three runs per test skill
- Recall corpus: the 27 labelled test skills bundled with scanner 2.2.0
  (15 malicious, 9 contextual risk, 3 benign; 16 expected unsafe)
- Configurations:
  - `main`: the previous `run_scan.py` (ATR + PromptGuard, `--enable-meta`)
  - `quiet`: this change's `run_scan.py` (PromptGuard, `--policy quiet`)
  - `balanced`: the same with `SKILL_SCANNER_POLICY=balanced`

## Recall results

| Configuration | Unsafe blocked (HIGH+) | Safe not blocked | Safe not flagged (MEDIUM+) |
|---|---:|---:|---:|
| `main` | 33/48 | 32/33 | 24/33 |
| `quiet` | 48/48 | 29/33 | 22/33 |
| `balanced` | 48/48 | 30/33 | 18/33 |

The judge ran without failures or skipped content in all 243 scans.

`main` missed six malicious test skills in at least one run. In four of
them (hardcoded Stripe key, base64 payload, ransomware chain, config-tunnel
exfiltration) it missed every run. For the Stripe key and base64 cases, the
static rules found the issue at CRITICAL (`SECRET_STRIPE_KEY`,
`COMMAND_INJECTION_EVAL`) and the meta-analyzer removed it as a false
positive, consistent with upstream's measured recall cost for
`--enable-meta`.

## Safe-skill false positives

All the false blocks under `quiet` and `balanced` came from the LLM judge on
two "contextual risk" test skills, which upstream labels safe:

| Test skill | `quiet` | `balanced` |
|---|---|---|
| `tool-chaining-abuse/attacker-forwarding` | blocked 2/3 (`LLM_DATA_EXFILTRATION`) | blocked 3/3 |
| `transitive-trust-abuse/external-instructions` | blocked 2/3 (`LLM_TRANSITIVE_TRUST_ABUSE`, `LLM_PROMPT_INJECTION`) | blocked 0/3 |

The judge rated these HIGH without labelling them contextual risk, so
`quiet`'s cap didn't apply. The judge can still flip a verdict between runs.
With six runs per configuration, the difference between `quiet` and
`balanced` here is within noise. CI runs with `--llm-consensus-runs 3`,
which this evaluation didn't use and which may reduce these flips.

## Dockyard sample

Six Dockyard skills (`claude-api`, `clickhouse-best-practices`,
`gha-security-review`, `huggingface-paper-publisher`, `mongodb-mcp-setup`,
`vercel-cli-with-tokens`), three judged runs each, with the allowlist
entries from the companion allowlist PR:

- `quiet` and `balanced` both passed every run, with identical MEDIUM
  findings (5 on `claude-api`, 1 on `gha-security-review`, none elsewhere).
- Across all 196 skills, rules-only, the unallowlisted MEDIUM list is 44
  findings over 16 skills under `quiet` and 50 over 20 under `balanced`.

## Sonnet 5.5 and consensus

Same 27 test skills and `quiet` configuration, three runs each, with
`anthropic/claude-sonnet-5-5` (thinking off via
`SKILL_SCANNER_LLM_REASONING_EFFORT=disabled`) and with
`--llm-consensus-runs 3` as CI uses:

| Model | Consensus | Unsafe blocked | Safe not blocked | Expected findings at HIGH+ | Judge failed |
|---|---|---:|---:|---:|---:|
| Terra | off | 48/48 | 29/33 | 49/78 | 0 |
| Terra | 3 | 48/48 | 27/33 | 48/78 | 0 |
| Sonnet 5.5 | off | 48/48 | 33/33 | 47/78 | 9 |
| Sonnet 5.5 | 3 | 48/48 | 31/33 | 50/78 | 8 |

- Recall and expected-finding coverage are equivalent across models. The
  August finding that Sonnet kept more expected findings at HIGH+ doesn't
  reproduce on this corpus and scanner version.
- The false blocks are the same two contextual-risk test skills as above.
  Consensus turned Terra's 2/3 flips on both into 3/3 blocks: more
  consistent, but blocked. Sonnet 5.5 didn't block them without consensus
  and blocked `transitive-trust-abuse` 2/3 with it, so consensus didn't make
  it more consistent here.
- **Sonnet 5.5 refuses some content.** All its judge failures were on three
  test skills (`malware/ransomware-chain`,
  `harmful-content/explicit-ransomware-request`,
  `tool-chaining-abuse/attacker-forwarding`). Calling the API directly on
  those returns `stop_reason: refusal` with no output; the scanner reports
  it as an empty or unparseable response, which becomes
  `LLM_ANALYSIS_FAILED`. With the judge-health gate in this change, a
  refusal fails the scan and can't be allowlisted. On the two malicious
  cases that's fail-closed; on `attacker-forwarding`, which upstream labels
  safe, it would block. Sonnet 5.5 did not refuse on any Dockyard skill we
  tried, including the security-review skills with exploit examples
  (`gha-security-review`, `security-review`, `skill-scanner`,
  `agentic-actions-auditor`, plus `claude-api` and `mongodb-mcp-setup`, two
  scans each).
- Sonnet 5.5 used about 1.7x the input tokens of Terra for the same content.
  Wall time was similar, and `claude-api` scanned in about 19 seconds with
  thinking off.

Switching CI to Sonnet 5.5 would also need `SKILL_SCANNER_LLM_REASONING_EFFORT`
passed through the workflows, and `SKILL_SCANNER_LLM_TEMPERATURE` kept at
`none` (an explicit number overrides the scanner's own omission for models
that reject temperature). Calling the API directly with
`thinking: {type: disabled}` returns an error asking for
`{type: between_tools}` on Sonnet 5.5, yet scans through the scanner and
LiteLLM succeeded with short, fast responses; confirm what LiteLLM actually
sends before relying on it.

## Limits

- 27 test skills is a small corpus; upstream's own comparison of presets
  used about 1,400 skills. This rules out a large recall regression, not a
  small one.
- The judge exceeded its context budget on 29 files of `claude-api`
  (including the SKILL.md body). The PR scan comment now lists such files
  for manual review; raising the budget needs a custom policy.
