#!/usr/bin/env python3
"""Benchmark skill-scanner LLM models against Dockyard's historical corpus.

Runs the same scan pipeline CI uses (run_scan.py) against a set of skills,
once per model per repetition, and scores each model on:

  - latency: wall-clock scan duration
  - blocking churn: findings that would block CI *today* (i.e. not covered
    by the skill's current allowlist). This measures operational churn, but
    findings still need review: some are legitimate trust boundaries rather
    than scanner noise.
  - noise volume: HIGH+ findings ignoring the allowlist entirely. This is
    what a maintainer would have had to triage from scratch. Lower is better.
  - stability: mean pairwise Jaccard similarity of the LLM-analyzer finding
    sets across repetitions (1.0 = perfectly deterministic). Higher is better.

Recall (does a cheaper model still catch real malware?) cannot be measured
from Dockyard data because the corpus contains no known-malicious skills.
Use the scanner's own ground-truth corpus for that leg — see README.md in
this directory.

Usage:
  python3 scripts/skill-scan/eval/bench_models.py \
    --key-file anthropic=~/keys/anthropic openai=~/keys/openai \
    --runs 3

The default --models matrix is the production baseline (sonnet-4-6) plus
claude-sonnet-5, claude-haiku-4-5, gpt-5.6-terra, and gpt-5.6-luna.

Results land in scripts/skill-scan/eval/results/<timestamp>/ as raw scan
JSON plus summary.json and summary.md.
"""

import argparse
import datetime
import itertools
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
SKILL_SCAN_DIR = EVAL_DIR.parent
REPO_ROOT = SKILL_SCAN_DIR.parent.parent

sys.path.insert(0, str(SKILL_SCAN_DIR))
from process_scan_results import classify_findings, load_security_config  # noqa: E402

# Skills with a history of scan churn or long scan times:
#  - claude-api: 18+ min scans (see run 32855694687)
#  - find-bugs, pulumi-upgrade-provider, provider-upgrade,
#    huggingface-paper-publisher: re-flagged under rotating rule IDs (#904)
#  - codeql, semgrep, supply-chain-risk-auditor, zeroize-audit: multiple
#    allowlist rounds on PR #855
DEFAULT_SKILLS = [
    "claude-api",
    "find-bugs",
    "pulumi-upgrade-provider",
    "provider-upgrade",
    "huggingface-paper-publisher",
    "codeql",
    "semgrep",
    "supply-chain-risk-auditor",
    "zeroize-audit",
]


def read_spec(skill: str) -> dict:
    spec_file = REPO_ROOT / "skills" / skill / "spec.yaml"
    with open(spec_file) as f:
        spec = yaml.safe_load(f)
    return {
        "spec_file": str(spec_file),
        "repository": spec["spec"]["repository"],
        "ref": spec["spec"]["ref"],
        "path": spec["spec"].get("path") or "",
    }


def checkout_source(skill: str, meta: dict, cache_dir: Path) -> Path:
    repo_dir = cache_dir / skill
    if not (repo_dir / ".git").exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=tree:0", "--no-checkout", "--quiet",
             meta["repository"], str(repo_dir)],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(repo_dir), "checkout", "--quiet", meta["ref"]],
        check=True,
    )
    src = repo_dir / meta["path"] if meta["path"] else repo_dir
    if not src.is_dir():
        raise FileNotFoundError(f"skill source not found: {src}")
    return src


def run_scan(source: Path, output: Path, model: str, api_key: str,
             temperature: str, consensus_runs: int | None) -> tuple[float, bool]:
    env = os.environ.copy()
    env.update({
        "SKILL_SCANNER_USE_LLM": "true",
        "SKILL_SCANNER_LLM_API_KEY": api_key,
        "SKILL_SCANNER_LLM_MODEL": model,
        "SKILL_SCANNER_LLM_TEMPERATURE": temperature,
    })
    # GPT-5.x reasoning models reject non-default temperature; the scanner's
    # "none" sentinel omits the parameter entirely (llm_request_handler.py,
    # _TEMPERATURE_OMIT_VALUES). The meta-analyzer falls back to this same
    # env var, so one setting covers both analyzers.
    if "gpt-5" in model.lower():
        env["SKILL_SCANNER_LLM_TEMPERATURE"] = "none"
    if consensus_runs and consensus_runs > 1:
        env["SKILL_SCANNER_LLM_CONSENSUS_RUNS"] = str(consensus_runs)
    else:
        env.pop("SKILL_SCANNER_LLM_CONSENSUS_RUNS", None)

    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(SKILL_SCAN_DIR / "run_scan.py"),
         "--source", str(source), "--output", str(output)],
        env=env, capture_output=True, text=True,
    )
    duration = time.monotonic() - start
    if proc.returncode != 0 or not output.exists():
        sys.stderr.write(proc.stderr[-2000:] + "\n")
        return duration, False
    return duration, True


def finding_keys(scan: dict, analyzers: set[str] | None = None) -> set[tuple]:
    keys = set()
    for f in scan.get("findings") or []:
        if not isinstance(f, dict):
            continue
        if analyzers and (f.get("analyzer") or "") not in analyzers:
            continue
        keys.add((f.get("analyzer"), f.get("rule_id"), f.get("file_path")))
    return keys


def sort_keys(keys: set[tuple]) -> list[tuple]:
    # Findings can carry None fields (e.g. no file_path on skill-level LLM
    # findings); plain sorted() dies comparing None with str.
    return sorted(keys, key=lambda t: tuple("" if x is None else str(x) for x in t))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def summarize_cell(runs: list[dict]) -> dict:
    ok = [r for r in runs if r["ok"]]
    llm_sets = [set(map(tuple, r["llm_keys"])) for r in ok]
    pair_sims = [jaccard(a, b) for a, b in itertools.combinations(llm_sets, 2)]
    out_toks = [r["llm_output_tokens"] for r in ok if r.get("llm_output_tokens")]
    return {
        "llm_output_tokens_mean": round(statistics.mean(out_toks)) if out_toks else None,
        "runs_ok": len(ok),
        "runs_total": len(runs),
        "duration_mean_s": round(statistics.mean(r["duration"] for r in runs), 1),
        "duration_max_s": round(max(r["duration"] for r in runs), 1),
        "blocking_per_run": [r["blocking"] for r in ok],
        "noise_high_per_run": [r["noise_high"] for r in ok],
        "llm_findings_per_run": [len(s) for s in llm_sets],
        "llm_stability_jaccard": round(statistics.mean(pair_sims), 3) if pair_sims else None,
        "llm_findings_union": [list(k) for k in sort_keys(set().union(*llm_sets))] if llm_sets else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", nargs="+", default=DEFAULT_SKILLS)
    parser.add_argument("--models", nargs="+", default=[
        "anthropic/claude-sonnet-4-6",  # production baseline
        "anthropic/claude-sonnet-5",
        "anthropic/claude-haiku-4-5",
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
    ], help="LiteLLM model strings, e.g. anthropic/claude-haiku-4-5")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--key-file", nargs="+", default=[],
                        help="Key file(s): either a single path used for all "
                        "models, or provider=path pairs, e.g. "
                        "anthropic=~/keys/ant openai=~/keys/oai. Falls back "
                        "to --env-file, then SKILL_SCANNER_LLM_API_KEY.")
    parser.add_argument("--env-file", default=str(EVAL_DIR / ".env"),
                        help="dotenv file with ANTHROPIC_API_KEY / "
                        "OPENAI_API_KEY (default: .env in this directory)")
    parser.add_argument("--temperature", default="0.0")
    parser.add_argument("--consensus-runs", type=int, default=None,
                        help="Optional --llm-consensus-runs N passthrough")
    parser.add_argument("--out", default=str(EVAL_DIR / "results"))
    parser.add_argument("--resume", default=None,
                        help="Existing results dir (a previous run's timestamp "
                        "dir): scans already on disk are scored, not re-run")
    args = parser.parse_args()

    keys: dict[str, str] = {}  # provider prefix -> key ("" = default for all)
    env_file = Path(args.env_file).expanduser()
    if env_file.is_file():
        env_var_to_provider = {"ANTHROPIC_API_KEY": "anthropic",
                               "OPENAI_API_KEY": "openai"}
        for line in env_file.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            provider = env_var_to_provider.get(name.strip())
            if provider:
                keys[provider] = value.strip().strip("'\"")
    # --key-file entries override anything loaded from the env file
    for spec in args.key_file:
        if "=" in spec:
            provider, _, path = spec.partition("=")
            keys[provider] = Path(path).expanduser().read_text().strip()
        else:
            keys[""] = Path(spec).expanduser().read_text().strip()
    env_key = os.environ.get("SKILL_SCANNER_LLM_API_KEY", "")

    def key_for(model: str) -> str:
        provider = model.split("/", 1)[0] if "/" in model else ""
        key = keys.get(provider) or keys.get("") or env_key
        if not key:
            sys.exit(f"No API key for {model}: pass --key-file {provider}=<path> "
                     "or set SKILL_SCANNER_LLM_API_KEY")
        return key

    for model in args.models:
        key_for(model)  # fail fast before any scans run

    if args.resume:
        out_dir = Path(args.resume)
        if not out_dir.is_dir():
            sys.exit(f"--resume dir not found: {out_dir}")
    else:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = Path(args.out) / stamp
        out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir.parent / "source-cache"

    results: dict[str, dict[str, dict]] = {}
    for skill in args.skills:
        meta = read_spec(skill)
        source = checkout_source(skill, meta, cache_dir)
        entries, _ = load_security_config(meta["spec_file"])
        results[skill] = {}
        for model in args.models:
            model_slug = model.replace("/", "_")
            runs = []
            for i in range(args.runs):
                scan_file = out_dir / f"{skill}--{model_slug}--run{i + 1}.json"
                if scan_file.exists() and scan_file.stat().st_size > 0:
                    # Resumed: score the existing scan; wall-clock duration is
                    # lost, fall back to the scanner's (undercounting) figure.
                    print(f"[{skill}] {model} run {i + 1}/{args.runs} (cached)", flush=True)
                    scan_json = json.loads(scan_file.read_text())
                    duration, ok = scan_json.get("scan_duration_seconds") or 0.0, True
                else:
                    print(f"[{skill}] {model} run {i + 1}/{args.runs} ...", flush=True)
                    duration, ok = run_scan(source, scan_file, model, key_for(model),
                                            args.temperature, args.consensus_runs)
                rec = {"duration": duration, "ok": ok,
                       "blocking": None, "noise_high": None, "llm_keys": []}
                if ok:
                    scan = json.loads(scan_file.read_text())
                    blocking, _, _ = classify_findings(scan, entries)
                    no_allow, _, _ = classify_findings(scan, [])
                    usage = scan.get("llm_usage") or {}
                    rec.update({
                        "blocking": len(blocking),
                        "noise_high": len(no_allow),
                        # analyzer field is "llm" or "static" (scanner 2.0.13)
                        "llm_keys": sort_keys(finding_keys(scan, {"llm"})),
                        "llm_input_tokens": usage.get("input_tokens"),
                        "llm_output_tokens": usage.get("output_tokens"),
                    })
                print(f"    {duration:.0f}s ok={ok} blocking={rec['blocking']} "
                      f"noise_high={rec['noise_high']}", flush=True)
                runs.append(rec)
            results[skill][model] = summarize_cell(runs)

    (out_dir / "summary.json").write_text(json.dumps(results, indent=2))

    lines = ["| Skill | Model | Mean time | Blocking/run | HIGH+ noise/run | LLM stability |",
             "|---|---|---|---|---|---|"]
    for skill, models in results.items():
        for model, cell in models.items():
            lines.append(
                f"| {skill} | {model} | {cell['duration_mean_s']}s "
                f"| {cell['blocking_per_run']} | {cell['noise_high_per_run']} "
                f"| {cell['llm_stability_jaccard']} |")
    md = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(md)
    print(f"\nResults written to {out_dir}\n\n{md}")


if __name__ == "__main__":
    main()
