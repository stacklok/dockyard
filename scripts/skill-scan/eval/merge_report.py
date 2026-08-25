#!/usr/bin/env python3
"""Merge bench_models candidate summaries + the mined CI baseline into one report.

Usage:
  python3 scripts/skill-scan/eval/merge_report.py \
    --baseline scripts/skill-scan/eval/results/ci-baseline/baseline-*.json \
    --candidates scripts/skill-scan/eval/results/m-*/2*/summary.json
"""

import argparse
import glob
import json
import statistics
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent


def cell_stats(cell: dict) -> dict:
    blocking = cell.get("blocking_per_run") or []
    noise = cell.get("noise_high_per_run") or []
    return {
        "runs": len(blocking),
        "block_rate": round(sum(1 for b in blocking if b) / len(blocking), 2) if blocking else None,
        "blocking_mean": round(statistics.mean(blocking), 1) if blocking else None,
        "noise_mean": round(statistics.mean(noise), 1) if noise else None,
        "stability": cell.get("llm_stability_jaccard"),
        "out_tokens": cell.get("llm_output_tokens_mean"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--candidates", nargs="+", default=None)
    parser.add_argument("--baseline-label", default="sonnet-4-6 (CI)")
    args = parser.parse_args()

    baseline_path = args.baseline or sorted(
        glob.glob(str(EVAL_DIR / "results" / "ci-baseline" / "baseline-*.json")))[-1]
    candidate_paths = args.candidates or sorted(
        glob.glob(str(EVAL_DIR / "results" / "m-*" / "2*" / "summary.json")))

    # skill -> model -> stats
    table: dict[str, dict[str, dict]] = {}
    models: list[str] = [args.baseline_label]

    # Only baseline scans from scanner 2.0.13 are comparable to the candidate
    # runs (2.0.12 shipped different rule packs — e.g. codeql's ~144 HIGH+
    # noise under 2.0.12 vs ~2 under 2.0.13). Artifacts predating the
    # scanner-version.txt upload report "" — classify those by date:
    # the 2.0.13 pin merged 2026-08-11 (commit dfd663b).
    V213_CUTOFF = "2026-08-12"

    def is_v213(run: dict) -> bool:
        v = run.get("scanner_version") or ""
        if v:
            return v == "2.0.13"
        return run.get("artifact_created", "") >= V213_CUTOFF

    baseline = json.loads(Path(baseline_path).read_text())
    for skill, data in baseline.items():
        for ref, group in data["groups"].items():
            if not group["is_current_ref"]:
                continue
            runs = [r for r in group.get("runs", []) if is_v213(r)]
            if not runs:
                continue
            llm_sets = [set(map(tuple, r["llm_keys"])) for r in runs]
            import itertools
            sims = [len(a & b) / len(a | b) if (a or b) else 1.0
                    for a, b in itertools.combinations(llm_sets, 2)]
            toks = [r["llm_output_tokens"] for r in runs if r.get("llm_output_tokens")]
            table.setdefault(skill, {})[args.baseline_label] = cell_stats({
                "blocking_per_run": [r["blocking"] for r in runs],
                "noise_high_per_run": [r["noise_high"] for r in runs],
                "llm_stability_jaccard": round(statistics.mean(sims), 3) if sims else None,
                "llm_output_tokens_mean": round(statistics.mean(toks)) if toks else None,
            })

    for path in candidate_paths:
        summary = json.loads(Path(path).read_text())
        # Label by results directory (m-<label>), not model string — the same
        # model can appear in several configurations (e.g. consensus runs).
        dir_label = Path(path).parent.parent.name.removeprefix("m-")
        for skill, per_model in summary.items():
            for model, cell in per_model.items():
                short = dir_label or model.split("/")[-1]
                if short not in models:
                    models.append(short)
                stats = cell_stats(cell)
                if cell.get("runs_ok", 1) == 0:
                    stats["note"] = "all runs failed/timed out"
                table.setdefault(skill, {})[short] = stats

    # Per-model aggregates across skills
    print("## Aggregate (mean across skills, current-ref content)\n")
    print("| Model | Skills | Block-rate | Blocking/scan | HIGH+ noise/scan | LLM stability | Out-tokens/scan |")
    print("|---|---|---|---|---|---|---|")
    for model in models:
        cells = [table[s][model] for s in table if model in table[s]
                 and table[s][model].get("runs")]
        if not cells:
            continue

        def mean_of(key):
            vals = [c[key] for c in cells if c.get(key) is not None]
            return round(statistics.mean(vals), 2) if vals else None

        print(f"| {model} | {len(cells)} | {mean_of('block_rate')} "
              f"| {mean_of('blocking_mean')} | {mean_of('noise_mean')} "
              f"| {mean_of('stability')} | {mean_of('out_tokens')} |")

    print("\n## Per-skill detail\n")
    print("| Skill | Model | Block-rate | Blocking/scan | HIGH+ noise/scan | LLM stability |")
    print("|---|---|---|---|---|---|")
    for skill in sorted(table):
        for model in models:
            c = table[skill].get(model)
            if not c:
                continue
            note = f" ({c['note']})" if c.get("note") else ""
            print(f"| {skill} | {model}{note} | {c['block_rate']} "
                  f"| {c['blocking_mean']} | {c['noise_mean']} | {c['stability']} |")


if __name__ == "__main__":
    main()
