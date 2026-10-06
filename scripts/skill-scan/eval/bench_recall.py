#!/usr/bin/env python3
"""Compare LLM models on skill-scanner's malicious and safe eval fixtures.

Unlike skill-scanner 2.0.13's bundled benchmark runner, this script invokes
Dockyard's production run_scan.py wrapper, so every fixture goes through the
same analyzers, rule packs, and policy as CI.

Usage:
  python3 scripts/skill-scan/eval/bench_recall.py \
    --scanner-source /path/to/skill-scanner \
    --models anthropic/claude-sonnet-5-5 openai/gpt-5.6-terra \
    --runs 3

Use --runner to score a different copy of run_scan.py (for example main's,
as a baseline) and --policy to compare scan policy presets.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

from bench_models import EVAL_DIR, run_scan

sys.path.insert(0, str(EVAL_DIR.parent))
from process_scan_results import classify_findings, judge_health  # noqa: E402

BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}
REVIEW_SEVERITIES = {"MEDIUM", "HIGH", "CRITICAL"}


def load_keys(key_files: list[str], env_file: Path) -> dict[str, str]:
    keys: dict[str, str] = {}
    if env_file.is_file():
        providers = {"ANTHROPIC_API_KEY": "anthropic", "OPENAI_API_KEY": "openai"}
        for line in env_file.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            provider = providers.get(name.strip())
            if provider:
                keys[provider] = value.strip().strip("'\"")
    for spec in key_files:
        if "=" in spec:
            provider, _, path = spec.partition("=")
            keys[provider] = Path(path).expanduser().read_text().strip()
        else:
            keys[""] = Path(spec).expanduser().read_text().strip()
    return keys


def key_for(model: str, keys: dict[str, str]) -> str:
    provider = model.split("/", 1)[0] if "/" in model else ""
    key = keys.get(provider) or keys.get("") or os.environ.get(
        "SKILL_SCANNER_LLM_API_KEY", ""
    )
    if not key:
        raise SystemExit(
            f"No API key for {model}: pass --key-file {provider}=<path> "
            "or set SKILL_SCANNER_LLM_API_KEY"
        )
    return key


def discover_fixtures(scanner_source: Path) -> list[tuple[Path, Path]]:
    fixture_root = scanner_source / "evals" / "skills"
    if not fixture_root.is_dir():
        raise SystemExit(f"Fixture directory not found: {fixture_root}")
    fixtures = []
    for expected_file in sorted(fixture_root.rglob("_expected.json")):
        if (expected_file.parent / "SKILL.md").is_file():
            fixtures.append((expected_file.parent, expected_file))
    if not fixtures:
        raise SystemExit(f"No evaluation fixtures found under {fixture_root}")
    return fixtures


def source_revision(scanner_source: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(scanner_source), "describe", "--always", "--tags", "--dirty"],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def expected_unsafe(expected: dict, expected_file: Path) -> bool:
    """Ground-truth label for a fixture.

    Scanner 2.2.0 fixtures (schema_version 2) carry `expected_verdict`
    ("safe"/"unsafe"); older ones carried `expected_safe`. Fail loudly on
    anything else rather than silently scoring the fixture as safe.
    """
    verdict = expected.get("expected_verdict")
    if verdict in ("safe", "unsafe"):
        return verdict == "unsafe"
    if isinstance(expected.get("expected_safe"), bool):
        return not expected["expected_safe"]
    if isinstance(expected.get("is_malicious"), bool):
        return expected["is_malicious"]
    raise SystemExit(f"Cannot determine expected verdict for {expected_file}")


def summarize(runs: list[dict]) -> dict:
    ok = [run for run in runs if run["ok"]]
    unsafe = [run for run in ok if run["expected_unsafe"]]
    safe = [run for run in ok if not run["expected_unsafe"]]
    expected_slots = sum(run["expected_slots"] for run in ok)
    return {
        "runs_ok": len(ok),
        "runs_total": len(runs),
        "unsafe_blocked": sum(run["blocked"] for run in unsafe),
        "unsafe_flagged_medium": sum(run["flagged"] for run in unsafe),
        "unsafe_total": len(unsafe),
        "safe_clean": sum(not run["blocked"] for run in safe),
        "safe_unflagged_medium": sum(not run["flagged"] for run in safe),
        "safe_total": len(safe),
        "expected_slots_covered_any": sum(run["covered_any"] for run in ok),
        "expected_slots_covered_high": sum(run["covered_high"] for run in ok),
        "expected_slots_total": expected_slots,
        "judge_not_run": sum(not run["judge_ran"] for run in ok),
        "judge_failed": sum(run["judge_failed"] for run in ok),
        "judge_budget_exceeded": sum(run["judge_budget_exceeded"] for run in ok),
        "wall_time_seconds": round(sum(run["duration"] for run in runs), 1),
        "input_tokens": sum(run["input_tokens"] for run in ok),
        "output_tokens": sum(run["output_tokens"] for run in ok),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner-source", required=True)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["anthropic/claude-sonnet-5-5", "openai/gpt-5.6-terra"],
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--key-file", nargs="+", default=[])
    parser.add_argument("--env-file", default=str(EVAL_DIR / ".env"))
    parser.add_argument("--temperature", default="0.0")
    parser.add_argument("--consensus-runs", type=int, default=None,
                        help="Optional --llm-consensus-runs N passthrough (CI uses 3)")
    parser.add_argument("--runner", type=Path, default=None,
                        help="Alternate run_scan.py to invoke (e.g. a copy of "
                        "main's, as a baseline). Defaults to the checkout's.")
    parser.add_argument("--policy", default=None,
                        help="Scan policy preset passed via SKILL_SCANNER_POLICY "
                        "(e.g. balanced). Ignored by runners that predate it.")
    parser.add_argument("--label", default=None,
                        help="Name for this configuration in the results dir")
    parser.add_argument("--out", default=str(EVAL_DIR / "results" / "recall"))
    args = parser.parse_args()

    scanner_source = Path(args.scanner_source).expanduser().resolve()
    fixtures = discover_fixtures(scanner_source)
    keys = load_keys(args.key_file, Path(args.env_file).expanduser())
    for model in args.models:
        key_for(model, keys)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / (f"{stamp}-{args.label}" if args.label else stamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_runs: dict[str, list[dict]] = {model: [] for model in args.models}
    for model in args.models:
        model_slug = model.replace("/", "_")
        for fixture, expected_file in fixtures:
            expected = json.loads(expected_file.read_text())
            fixture_slug = "--".join(fixture.relative_to(scanner_source / "evals" / "skills").parts)
            is_unsafe = expected_unsafe(expected, expected_file)
            expected_categories = [
                finding.get("category")
                for finding in expected.get("expected_findings", [])
                if finding.get("category")
            ]
            for index in range(1, args.runs + 1):
                output = out_dir / f"{fixture_slug}--{model_slug}--run{index}.json"
                print(f"[{model}] {fixture_slug} run {index}/{args.runs} ...", flush=True)
                duration, ok = run_scan(
                    fixture,
                    output,
                    model,
                    key_for(model, keys),
                    args.temperature,
                    args.consensus_runs,
                    runner=args.runner,
                    policy=args.policy,
                )
                record = {
                    "fixture": fixture_slug,
                    "package_label": expected.get("package_label"),
                    "expected_unsafe": is_unsafe,
                    "expected_slots": len(expected_categories),
                    "run": index,
                    "duration": duration,
                    "ok": ok,
                    "blocked": False,
                    "flagged": False,
                    "max_severity": None,
                    "covered_any": 0,
                    "covered_high": 0,
                    "judge_ran": False,
                    "judge_failed": False,
                    "judge_budget_exceeded": False,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
                if ok:
                    scan = json.loads(output.read_text())
                    findings = scan.get("findings", [])
                    blocking, _, _ = classify_findings(scan, [])
                    actual_categories = {finding.get("category") for finding in findings}
                    high_categories = {
                        finding.get("category")
                        for finding in findings
                        if finding.get("severity") in BLOCKING_SEVERITIES
                    }
                    health = judge_health(scan)
                    usage = scan.get("llm_usage") or {}
                    record.update(
                        {
                            "blocked": bool(blocking),
                            "flagged": any(
                                finding.get("severity") in REVIEW_SEVERITIES for finding in findings
                            ),
                            "max_severity": scan.get("max_severity"),
                            "covered_any": sum(
                                category in actual_categories for category in expected_categories
                            ),
                            "covered_high": sum(
                                category in high_categories for category in expected_categories
                            ),
                            "judge_ran": health["ran"],
                            "judge_failed": health["failed"],
                            "judge_budget_exceeded": bool(health["budget_exceeded_files"]),
                            "input_tokens": usage.get("input_tokens") or 0,
                            "output_tokens": usage.get("output_tokens") or 0,
                        }
                    )
                all_runs[model].append(record)
                print(
                    f"    {duration:.0f}s ok={ok} blocked={record['blocked']} "
                    f"flagged={record['flagged']} max={record['max_severity']} "
                    f"expected={'unsafe' if is_unsafe else 'safe'}",
                    flush=True,
                )

    summary = {
        "label": args.label,
        "runner": str(args.runner) if args.runner else "run_scan.py (checkout)",
        "policy": args.policy,
        "consensus_runs": args.consensus_runs,
        "scanner_source": str(scanner_source),
        "scanner_revision": source_revision(scanner_source),
        "runs_per_fixture": args.runs,
        "fixtures": len(fixtures),
        "models": {model: summarize(runs) for model, runs in all_runs.items()},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out_dir / "runs.json").write_text(json.dumps(all_runs, indent=2) + "\n")

    lines = [
        "| Model | Unsafe blocked (HIGH+) | Unsafe flagged (MEDIUM+) | Safe clean (HIGH+) "
        "| Safe unflagged (MEDIUM+) | Judge not run / failed / budget | Wall time |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model, data in summary["models"].items():
        lines.append(
            f"| {model} | {data['unsafe_blocked']}/{data['unsafe_total']} "
            f"| {data['unsafe_flagged_medium']}/{data['unsafe_total']} "
            f"| {data['safe_clean']}/{data['safe_total']} "
            f"| {data['safe_unflagged_medium']}/{data['safe_total']} "
            f"| {data['judge_not_run']} / {data['judge_failed']} / {data['judge_budget_exceeded']} "
            f"| {data['wall_time_seconds']}s |"
        )
    lines += ["", "Per-fixture blocked (HIGH+) and flagged (MEDIUM+) counts across runs:", "",
              "| Fixture | Label | Expected | " + " | ".join(args.models) + " |",
              "|---|---|---|" + "---|" * len(args.models)]
    for fixture, expected_file in fixtures:
        slug = "--".join(fixture.relative_to(scanner_source / "evals" / "skills").parts)
        cells = []
        label = expected = ""
        for model in args.models:
            runs = [r for r in all_runs[model] if r["fixture"] == slug and r["ok"]]
            if runs:
                label = runs[0]["package_label"]
                expected = "unsafe" if runs[0]["expected_unsafe"] else "safe"
            cells.append(f"B {sum(r['blocked'] for r in runs)}/{len(runs)}, "
                         f"F {sum(r['flagged'] for r in runs)}/{len(runs)}")
        lines.append(f"| {slug} | {label} | {expected} | " + " | ".join(cells) + " |")
    markdown = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(markdown)
    print(f"\nResults written to {out_dir}\n\n{markdown}")


if __name__ == "__main__":
    main()
