#!/usr/bin/env python3
"""Mine historical CI skill-scan artifacts as the production-model baseline.

CI already ran hundreds of skill-scanner scans with the production model
(SKILL_SCANNER_LLM_MODEL repo variable), so instead of re-running the
baseline leg of the model eval, this script downloads the retained
skill-scan-<skill> artifacts (30-day retention) and computes the same
metrics bench_models.py computes for candidate models.

Caveats this script handles or surfaces:
- The scan JSON does not record which model produced it. Model attribution
  comes from the repo variable's history; use --since to exclude artifacts
  from before the current model was configured.
- Each artifact scanned the skill at whatever spec.ref was pinned at that
  commit. Results are grouped by (skill, scanned_ref); only groups whose
  ref matches the current spec.yaml are directly comparable to candidate
  runs on today's content (marked "current" in the summary). Other groups
  still contribute stability evidence for the production model.
- The scan-result cache (build-skills.yml) can upload the same scan twice;
  duplicates are dropped by the scan's own timestamp.
- Wall-clock duration in the JSON (scan_duration_seconds) undercounts badly
  (82s recorded vs ~19min of job time for claude-api); llm_usage tokens are
  the more honest latency/cost proxy.

Usage:
  python3 scripts/skill-scan/eval/mine_ci_baseline.py [--skills ...] [--since 2026-08-01]
"""

import argparse
import base64
import datetime
import io
import itertools
import json
import statistics
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))
from process_scan_results import classify_findings, load_security_config  # noqa: E402

from bench_models import DEFAULT_SKILLS, REPO_ROOT, finding_keys, jaccard, read_spec  # noqa: E402

REPO = "stacklok/dockyard"


def gh_api(path: str, binary: bool = False):
    result = subprocess.run(["gh", "api", path], capture_output=True, check=True)
    return result.stdout if binary else json.loads(result.stdout)


def spec_ref_at(skill: str, sha: str, cache: dict) -> str | None:
    """spec.ref of the skill at a given repo commit (None if spec absent)."""
    key = (skill, sha)
    if key not in cache:
        try:
            blob = gh_api(f"repos/{REPO}/contents/skills/{skill}/spec.yaml?ref={sha}")
            spec = yaml.safe_load(base64.b64decode(blob["content"]))
            cache[key] = spec["spec"]["ref"]
        except (subprocess.CalledProcessError, KeyError, TypeError):
            cache[key] = None
    return cache[key]


def fetch_artifacts(skill: str, since: str | None) -> list[dict]:
    data = gh_api(f"repos/{REPO}/actions/artifacts?name=skill-scan-{skill}&per_page=100")
    arts = []
    for a in data.get("artifacts", []):
        if a.get("expired"):
            continue
        if since and a["created_at"] < since:
            continue
        arts.append(a)
    return arts


def download_scan(artifact: dict, skill: str, cache_dir: Path) -> tuple[dict | None, str]:
    """Return (scan_json, scanner_version) from an artifact zip, caching on disk."""
    zip_path = cache_dir / f"{skill}-{artifact['id']}.zip"
    if not zip_path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(
            gh_api(f"repos/{REPO}/actions/artifacts/{artifact['id']}/zip", binary=True))
    scan, version = None, ""
    with zipfile.ZipFile(io.BytesIO(zip_path.read_bytes())) as zf:
        names = zf.namelist()
        scan_name = f"skill-scan-{skill}.json"
        if scan_name in names:
            try:
                scan = json.loads(zf.read(scan_name))
            except json.JSONDecodeError:
                scan = None
        if "scanner-version.txt" in names:
            version = zf.read("scanner-version.txt").decode().strip()
    return scan, version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", nargs="+", default=DEFAULT_SKILLS)
    parser.add_argument("--since", default=None,
                        help="Only use artifacts created on/after this ISO date "
                        "(exclude runs from before the current model was set)")
    parser.add_argument("--out", default=str(EVAL_DIR / "results" / "ci-baseline"))
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_cache = out_dir / "artifact-cache"
    ref_cache: dict = {}

    results: dict[str, dict] = {}
    for skill in args.skills:
        meta = read_spec(skill)
        entries, _ = load_security_config(meta["spec_file"])
        current_ref = meta["ref"]

        groups: dict[str, list[dict]] = {}  # scanned_ref -> scan records
        seen_timestamps: set[str] = set()
        artifacts = fetch_artifacts(skill, args.since)
        print(f"[{skill}] {len(artifacts)} artifacts retained", flush=True)

        for art in artifacts:
            head_sha = (art.get("workflow_run") or {}).get("head_sha")
            if not head_sha:
                continue
            scanned_ref = spec_ref_at(skill, head_sha, ref_cache)
            if scanned_ref is None:
                continue
            scan, version = download_scan(art, skill, zip_cache)
            if not scan:
                continue
            ts = scan.get("timestamp") or ""
            if ts in seen_timestamps:  # cache-hit duplicate upload
                continue
            seen_timestamps.add(ts)

            blocking, _, _ = classify_findings(scan, entries)
            no_allow, _, _ = classify_findings(scan, [])
            usage = scan.get("llm_usage") or {}
            groups.setdefault(scanned_ref, []).append({
                "artifact_created": art["created_at"],
                "scanner_version": version,
                "blocking": len(blocking),
                "noise_high": len(no_allow),
                "llm_keys": sorted(finding_keys(scan, {"llm"})),
                "llm_output_tokens": usage.get("output_tokens"),
                "scan_duration_seconds": scan.get("scan_duration_seconds"),
            })

        results[skill] = {"current_ref": current_ref, "groups": {}}
        for ref, runs in groups.items():
            llm_sets = [set(map(tuple, r["llm_keys"])) for r in runs]
            sims = [jaccard(a, b) for a, b in itertools.combinations(llm_sets, 2)]
            toks = [r["llm_output_tokens"] for r in runs if r.get("llm_output_tokens")]
            results[skill]["groups"][ref] = {
                "is_current_ref": ref == current_ref,
                "n_scans": len(runs),
                "scanner_versions": sorted({r["scanner_version"] for r in runs}),
                "blocking_per_run": [r["blocking"] for r in runs],
                "noise_high_per_run": [r["noise_high"] for r in runs],
                "llm_findings_per_run": [len(s) for s in llm_sets],
                "llm_stability_jaccard": round(statistics.mean(sims), 3) if sims else None,
                "llm_output_tokens_mean": round(statistics.mean(toks)) if toks else None,
                "runs": runs,
            }

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / f"baseline-{stamp}.json").write_text(json.dumps(results, indent=2))

    lines = ["| Skill | Ref | Current? | Scans | Blocking/run | HIGH+ noise/run | LLM stability |",
             "|---|---|---|---|---|---|---|"]
    for skill, data in results.items():
        for ref, g in sorted(data["groups"].items(),
                             key=lambda kv: not kv[1]["is_current_ref"]):
            lines.append(
                f"| {skill} | {ref[:8]} | {'yes' if g['is_current_ref'] else ''} "
                f"| {g['n_scans']} | {g['blocking_per_run']} "
                f"| {g['noise_high_per_run']} | {g['llm_stability_jaccard']} |")
    md = "\n".join(lines) + "\n"
    (out_dir / f"baseline-{stamp}.md").write_text(md)
    print(f"\nWritten to {out_dir}/baseline-{stamp}.{{json,md}}\n\n{md}")


if __name__ == "__main__":
    main()
