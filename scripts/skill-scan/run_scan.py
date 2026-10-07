#!/usr/bin/env python3
"""Wrapper for Cisco AI Defense skill-scanner.

Runs skill-scanner against a skill source directory and writes the JSON
report to a file. Allowlist filtering and exit-code logic live in
process_scan_results.py so the scanner always runs to completion here.
"""

import argparse
import os
import shutil
import subprocess
import sys


def is_scanner_installed() -> bool:
    return shutil.which("skill-scanner") is not None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Cisco AI Defense skill-scanner against a skill source directory"
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the skill source directory containing SKILL.md",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write scanner JSON output",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.source):
        print(f"Error: source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    scanner_args = [
        "scan",
        args.source,
        "--format", "json",
        "--output-json", args.output,
        # Always-on analyzers — free, in-tree, no network, no LLM key.
        # PromptGuard adds Anthropic/OpenAI key detection and markdown
        # exfiltration rules. The ATR pack is deliberately off: its regexes
        # produced ~98% of HIGH+ hits across the catalog, and upstream ATR
        # ships every skill-targeted rule as maturity "test", not for gating.
        "--rule-packs", "promptguard",
        # Upstream's lowest-FPR preset for vetted third-party skills: demotes
        # noisy rules to LOW and caps low-confidence and contextual-risk LLM
        # findings at LOW, so they can't cross the HIGH block threshold. Its
        # measured recall assumes MEDIUM findings get reviewed; the PR scan
        # comment lists them.
        # SKILL_SCANNER_POLICY exists so the eval harness can compare presets;
        # CI does not set it.
        "--policy", os.environ.get("SKILL_SCANNER_POLICY", "").strip() or "quiet",
        # Vague-description / capability-inflation detector (skill discovery abuse).
        "--use-trigger",
        # AST + dataflow analyzer (Python/Bash). No execution, no key.
        "--use-behavioral",
    ]

    if os.environ.get("SKILL_SCANNER_USE_LLM", "").lower() == "true":
        if os.environ.get("SKILL_SCANNER_LLM_API_KEY"):
            scanner_args.extend([
                # No --enable-meta: the meta-analyzer can drop deterministic
                # rule findings, which made the blocking decision flip between
                # runs on identical content. Upstream also measured it costing
                # 16.4 points of recall and turned it off by default.
                "--use-llm",
                # Match the scanner's own default; pin so we can tune from CI.
                "--llm-max-tokens", "8192",
            ])
            consensus = os.environ.get("SKILL_SCANNER_LLM_CONSENSUS_RUNS", "").strip()
            if consensus.isdigit() and int(consensus) > 1:
                # N>1 multiplies LLM cost N× per scan; left off by default.
                scanner_args.extend(["--llm-consensus-runs", consensus])
        else:
            # Fail rather than silently fall back to rules only: the quiet
            # policy assumes the judge, and upstream warns against using it
            # without one.
            print(
                "Error: SKILL_SCANNER_USE_LLM=true but SKILL_SCANNER_LLM_API_KEY not set",
                file=sys.stderr,
            )
            sys.exit(1)

    if is_scanner_installed():
        cmd = ["skill-scanner"] + scanner_args
    else:
        cmd = ["uv", "run", "--with", "cisco-ai-skill-scanner", "skill-scanner"] + scanner_args

    # 600s was too short for large skills (#903); configurable, default 1800.
    scan_timeout = int(os.environ.get("SKILL_SCANNER_TIMEOUT_SECONDS", "1800"))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=scan_timeout)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(
                f"skill-scanner exited with status {result.returncode}; "
                "process_scan_results.py will decide whether findings block the build",
                file=sys.stderr,
            )
        sys.exit(0)
    except subprocess.TimeoutExpired:
        print(f"Error running skill-scanner: scan timed out after {scan_timeout} seconds", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error running skill-scanner: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
