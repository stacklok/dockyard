#!/usr/bin/env python3
"""Wrapper script to run Cisco AI Defense mcp-scanner."""

import argparse
import json
import shutil
import subprocess
import sys
import os


def is_scanner_installed():
    """Check if mcp-scanner is available in PATH (installed via uv tool install)."""
    return shutil.which("mcp-scanner") is not None


def main():
    parser = argparse.ArgumentParser(description="Run Cisco AI Defense mcp-scanner")
    parser.add_argument("--config", type=str, help="Path to JSON config file")
    # Legacy positional arguments for backwards compatibility
    parser.add_argument("command", nargs="?", help="Command to run (e.g., 'npx')")
    parser.add_argument("package_arg", nargs="?", help="Package argument (e.g., '@playwright/mcp@0.0.55')")
    args = parser.parse_args()

    # Load config from file or use legacy positional arguments
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
            command = config.get("command")
            package_arg = config.get("args")
            mock_env = config.get("mock_env", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading config file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command and args.package_arg:
        # Legacy mode: positional arguments
        command = args.command
        package_arg = args.package_arg
        mock_env = []
    else:
        print("Usage: run_scan.py --config <config.json>", file=sys.stderr)
        print("   or: run_scan.py <command> <package_arg>", file=sys.stderr)
        sys.exit(1)

    # Determine analyzers based on environment
    analyzers = ["yara"]  # Always use yara (free, offline)
    if os.environ.get("MCP_SCANNER_ENABLE_LLM", "").lower() == "true":
        if os.environ.get("MCP_SCANNER_LLM_API_KEY"):
            analyzers.append("llm")
        else:
            print("Warning: MCP_SCANNER_ENABLE_LLM=true but MCP_SCANNER_LLM_API_KEY not set",
                  file=sys.stderr)

    # Build scanner arguments
    # Use 'stdio' subcommand with --stdio-arg
    # Note: --stdio-arg is deprecated but --stdio-args has different behavior
    # that causes issues with some package names
    scanner_args = [
        "--analyzers", ",".join(analyzers),
        "--format", "raw",
        "stdio",
        "--stdio-command", command,
        "--stdio-arg", package_arg
    ]

    # Add mock environment variables for servers that require them
    # mcp-scanner supports --stdio-env KEY=VALUE (can be repeated)
    for env_var in mock_env:
        name = env_var.get("name")
        value = env_var.get("value")
        if name and value:
            scanner_args.extend(["--stdio-env", f"{name}={value}"])

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
