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
    ]

    if os.environ.get("SKILL_SCANNER_USE_BEHAVIORAL", "").lower() == "true":
        scanner_args.append("--use-behavioral")

    if os.environ.get("SKILL_SCANNER_USE_LLM", "").lower() == "true":
        if os.environ.get("SKILL_SCANNER_LLM_API_KEY"):
            scanner_args.append("--use-llm")
        else:
            print(
                "Warning: SKILL_SCANNER_USE_LLM=true but SKILL_SCANNER_LLM_API_KEY not set",
                file=sys.stderr,
            )

    if is_scanner_installed():
        cmd = ["skill-scanner"] + scanner_args
    else:
        cmd = ["uv", "run", "--with", "cisco-ai-skill-scanner", "skill-scanner"] + scanner_args

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=600)
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
        print("Error running skill-scanner: scan timed out after 600 seconds", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error running skill-scanner: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
