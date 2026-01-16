#!/usr/bin/env python3
"""Wrapper script to run Cisco AI Defense mcp-scanner."""

import shutil
import subprocess
import sys
import os


def is_scanner_installed():
    """Check if mcp-scanner is available in PATH (installed via uv tool install)."""
    return shutil.which("mcp-scanner") is not None


def main():
    if len(sys.argv) < 3:
        print("Usage: run_scan.py <command> <package_arg>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]  # e.g., "npx"
    package_arg = sys.argv[2]  # e.g., "@playwright/mcp@0.0.55"

    # Determine analyzers based on environment
    analyzers = ["yara"]  # Always use yara (free, offline)
    if os.environ.get("MCP_SCANNER_ENABLE_LLM", "").lower() == "true":
        if os.environ.get("MCP_SCANNER_LLM_API_KEY"):
            analyzers.append("llm")
        else:
            print("Warning: MCP_SCANNER_ENABLE_LLM=true but MCP_SCANNER_LLM_API_KEY not set",
                  file=sys.stderr)

    # Build scanner arguments
    scanner_args = [
        "--analyzers", ",".join(analyzers),
        "--format", "raw",
        "stdio",
        "--stdio-command", command,
        "--stdio-arg", package_arg
    ]

    # Use installed mcp-scanner if available (faster), otherwise use uv run --with
    # CI installs with: uv tool install cisco-ai-mcp-scanner
    # Local without setup can use: uv run --with cisco-ai-mcp-scanner
    if is_scanner_installed():
        cmd = ["mcp-scanner"] + scanner_args
    else:
        # Fallback: use uv run --with for ad-hoc execution
        # Note: PyPI package is cisco-ai-mcp-scanner, CLI command is mcp-scanner
        cmd = ["uv", "run", "--with", "cisco-ai-mcp-scanner", "mcp-scanner"] + scanner_args

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    except Exception as e:
        print(f"Error running mcp-scanner: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
