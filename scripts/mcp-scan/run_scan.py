#!/usr/bin/env python3
"""Wrapper script to run Cisco AI Defense mcp-scanner."""

import argparse
import json
import shutil
import subprocess
import sys
import os
import tempfile


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
            uv_overrides = config.get("uv_overrides", [])
            npm_overrides = config.get("npm_overrides", {})
            npm_package = config.get("npm_package")
            npm_version = config.get("npm_version")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading config file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command and args.package_arg:
        # Legacy mode: positional arguments
        command = args.command
        package_arg = args.package_arg
        mock_env = []
        uv_overrides = []
        npm_overrides, npm_package, npm_version = {}, None, None
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
    # Use 'stdio' subcommand with --stdio-arg (singular, repeatable) for each argument
    # This avoids issues with --stdio-args positional parsing when extra args like "start" are present
    scanner_args = [
        "--analyzers", ",".join(analyzers),
        "--format", "raw",
        "stdio",
        "--stdio-command", command,
    ]
    # npx prompts for confirmation before installing packages, which blocks on
    # stdin (owned by mcp-scanner for the MCP protocol). Pass --yes to auto-accept.
    # Use --stdio-arg=VALUE syntax because --yes looks like a flag to argparse.
    if command == "npx":
        scanner_args.append("--stdio-arg=--yes")

    # Reapply npx dependency overrides (spec.overrides). npm honors "overrides" only from a
    # package.json it installs into, and the scan otherwise invokes `npx <pkg>` ad hoc with no
    # project directory. Stage a throwaway project carrying the dependency plus the overrides,
    # install it, and run the scanner from there so npx resolves that tree. --no-install keeps
    # npx from silently fetching an un-overridden copy instead.
    npm_project = None
    if npm_overrides:
        if command != "npx":
            print(f"Error: npm_overrides is only supported for npx, got {command}", file=sys.stderr)
            sys.exit(1)
        if not npm_package or not npm_version:
            print("Error: npm_overrides requires npm_package and npm_version", file=sys.stderr)
            sys.exit(1)
        if shutil.which("npm") is None:
            print("Error: npm is required to stage npx dependency overrides but was not found on PATH",
                  file=sys.stderr)
            sys.exit(1)

        npm_project = tempfile.mkdtemp(prefix="mcp-scan-npm-")
        # Staging happens before the scanner's own try/finally, so clean up here on any
        # failure rather than leaving the temp project behind.
        try:
            with open(os.path.join(npm_project, "package.json"), "w") as f:
                json.dump({
                    "name": "mcp-scan-overrides",
                    "private": True,
                    "dependencies": {npm_package: npm_version},
                    "overrides": npm_overrides,
                }, f)
            install = subprocess.run(
                ["npm", "install", "--silent", "--no-audit", "--no-fund"],
                cwd=npm_project, capture_output=True, text=True, check=False, timeout=300,
            )
            if install.returncode != 0:
                print(f"Error: npm install failed while staging overrides:\n{install.stderr}",
                      file=sys.stderr)
                sys.exit(1)
        except subprocess.TimeoutExpired:
            print("Error: npm install timed out after 300 seconds while staging overrides",
                  file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            print(f"Error: could not stage npx dependency overrides: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if npm_project and not os.path.isdir(os.path.join(npm_project, "node_modules")):
                shutil.rmtree(npm_project, ignore_errors=True)
                npm_project = None

        scanner_args.append("--stdio-arg=--no-install")

    # Reapply uvx dependency overrides (spec.constraints) so the scanned process resolves
    # the same dependency versions as the built image. uv takes these as a requirements
    # file, so write one; it must outlive this function's setup and be cleaned up after
    # the scan, hence the try/finally around the subprocess call below.
    overrides_file = None
    if uv_overrides:
        if command != "uvx":
            print(f"Error: uv_overrides is only supported for uvx, got {command}", file=sys.stderr)
            sys.exit(1)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="uv-overrides-", delete=False
        ) as f:
            f.write("\n".join(uv_overrides) + "\n")
            overrides_file = f.name
        # The flag must precede the package spec. Use --stdio-arg=VALUE for the flag
        # itself, since a bare "--overrides" would be read as a new argparse flag.
        scanner_args.append("--stdio-arg=--overrides")
        scanner_args.extend(["--stdio-arg", overrides_file])

    for arg in package_arg.split():
        scanner_args.extend(["--stdio-arg", arg])

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
        result = subprocess.run(cmd, cwd=npm_project, capture_output=True, text=True, check=False, timeout=300)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        print("Error running mcp-scanner: scan timed out after 300 seconds", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error running mcp-scanner: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if overrides_file:
            try:
                os.unlink(overrides_file)
            except OSError:
                pass
        if npm_project:
            shutil.rmtree(npm_project, ignore_errors=True)

if __name__ == "__main__":
    main()
