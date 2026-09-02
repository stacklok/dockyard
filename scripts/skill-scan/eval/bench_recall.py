#!/usr/bin/env python3
"""Compare LLM models on skill-scanner's malicious and safe eval fixtures.

Unlike skill-scanner 2.0.13's bundled benchmark runner, this script invokes
Dockyard's production run_scan.py wrapper, so the LLM and meta analyzers are
actually enabled.

Usage:
  python3 scripts/skill-scan/eval/bench_recall.py \
    --scanner-source /path/to/skill-scanner \
    --models anthropic/claude-sonnet-4-6 openai/gpt-5.6-terra \
    --runs 3
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
from process_scan_results import classify_findings  # noqa: E402

BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}


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


def summarize(runs: list[dict]) -> dict:
    ok = [run for run in runs if run["ok"]]
    expected_slots = sum(run["expected_slots"] for run in ok)
    return {
        "runs_ok": len(ok),
        "runs_total": len(runs),
        "malicious_blocked": sum(
            1 for run in ok if not run["expected_safe"] and run["blocked"]
        ),
        "malicious_total": sum(1 for run in ok if not run["expected_safe"]),
        "safe_clean": sum(
            1 for run in ok if run["expected_safe"] and not run["blocked"]
        ),
        "safe_total": sum(1 for run in ok if run["expected_safe"]),
        "expected_slots_covered_any": sum(run["covered_any"] for run in ok),
        "expected_slots_covered_high": sum(run["covered_high"] for run in ok),
        "expected_slots_total": expected_slots,
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
        default=["anthropic/claude-sonnet-4-6", "openai/gpt-5.6-terra"],
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--key-file", nargs="+", default=[])
    parser.add_argument("--env-file", default=str(EVAL_DIR / ".env"))
    parser.add_argument("--temperature", default="0.0")
    parser.add_argument("--out", default=str(EVAL_DIR / "results" / "recall"))
    args = parser.parse_args()

    scanner_source = Path(args.scanner_source).expanduser().resolve()
    fixtures = discover_fixtures(scanner_source)
    keys = load_keys(args.key_file, Path(args.env_file).expanduser())
    for model in args.models:
        key_for(model, keys)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    all_runs: dict[str, list[dict]] = {model: [] for model in args.models}
    for model in args.models:
        model_slug = model.replace("/", "_")
        for fixture, expected_file in fixtures:
            expected = json.loads(expected_file.read_text())
            fixture_slug = "--".join(fixture.relative_to(scanner_source / "evals" / "skills").parts)
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
                    None,
                )
                record = {
                    "fixture": fixture_slug,
                    "expected_safe": expected.get("expected_safe", True),
                    "expected_slots": len(expected_categories),
                    "duration": duration,
                    "ok": ok,
                    "blocked": False,
                    "covered_any": 0,
                    "covered_high": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
                if ok:
                    scan = json.loads(output.read_text())
                    blocking, _, _ = classify_findings(scan, [])
                    actual_categories = {
                        finding.get("category") for finding in scan.get("findings", [])
                    }
                    high_categories = {
                        finding.get("category")
                        for finding in scan.get("findings", [])
                        if finding.get("severity") in BLOCKING_SEVERITIES
                    }
                    usage = scan.get("llm_usage") or {}
                    record.update(
                        {
                            "blocked": bool(blocking),
                            "covered_any": sum(
                                category in actual_categories for category in expected_categories
                            ),
                            "covered_high": sum(
                                category in high_categories for category in expected_categories
                            ),
                            "input_tokens": usage.get("input_tokens") or 0,
                            "output_tokens": usage.get("output_tokens") or 0,
                        }
                    )
                all_runs[model].append(record)
                print(
                    f"    {duration:.0f}s ok={ok} blocked={record['blocked']} "
                    f"coverage={record['covered_high']}/{record['expected_slots']} HIGH+",
                    flush=True,
                )

    summary = {
        "scanner_source": str(scanner_source),
        "scanner_revision": source_revision(scanner_source),
        "runs_per_fixture": args.runs,
        "fixtures": len(fixtures),
        "models": {model: summarize(runs) for model, runs in all_runs.items()},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        "| Model | Malicious blocked | Safe clean | Expected coverage (any) "
        "| Expected coverage (HIGH+) | Wall time | Input tokens | Output tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model, data in summary["models"].items():
        lines.append(
            f"| {model} | {data['malicious_blocked']}/{data['malicious_total']} "
            f"| {data['safe_clean']}/{data['safe_total']} "
            f"| {data['expected_slots_covered_any']}/{data['expected_slots_total']} "
            f"| {data['expected_slots_covered_high']}/{data['expected_slots_total']} "
            f"| {data['wall_time_seconds']}s | {data['input_tokens']} "
            f"| {data['output_tokens']} |"
        )
    markdown = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(markdown)
    print(f"\nResults written to {out_dir}\n\n{markdown}")


if __name__ == "__main__":
    main()
