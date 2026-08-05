#!/usr/bin/env python3
"""Generate command/args for Cisco mcp-scanner stdio mode."""

import yaml
import json
import sys

def main():
    if len(sys.argv) != 4:
        print("Usage: generate_mcp_config.py <config_file> <protocol> <server_name>", file=sys.stderr)
        sys.exit(1)

    config_file, protocol, server_name = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)

        if not data or 'spec' not in data:
            print(f"Error: Invalid YAML structure in {config_file}", file=sys.stderr)
            sys.exit(1)

        package = data['spec']['package']
        version = data['spec'].get('version', 'latest')

        # Extract mock_env from security section (for MCP servers requiring env vars)
        mock_env = data.get('security', {}).get('mock_env', [])

        # Extract additional args from spec (e.g., ["start"] for LaunchDarkly)
        spec_args = data['spec'].get('args', [])
        spec_args_str = ' '.join(spec_args) if spec_args else ''

        # Dependency overrides (see docs/adding-servers.md). The scan runs the package
        # directly rather than the built image, so it has to reapply these itself or it
        # would exercise a different dependency set than the one that ships.
        #
        # uvx: passed through as data; run_scan.py writes them to a uv overrides
        # requirements file, since uv needs a file rather than inline specifiers.
        uv_overrides = [c['spec'] for c in data['spec'].get('constraints', []) if c.get('spec')]

        # npx: npm honors "overrides" only from a package.json it installs into, and the
        # scan invokes the package via `npx <pkg>` with no such project directory. These
        # overrides exist to swap a vulnerable-but-working transitive dep for a patched
        # one, which does not change server startup or the tool surface being analyzed,
        # so skipping them here does not affect the scan result. Warn so a future
        # startup-affecting override does not fail confusingly.
        npm_overrides = data['spec'].get('overrides', [])
        if protocol == 'npx' and npm_overrides:
            print(
                f"Note: {server_name} declares spec.overrides, which are not applied to the "
                "security scan (npm overrides require a package.json; npx installs ad hoc). "
                "The built image still gets them.",
                file=sys.stderr,
            )

        if protocol in ['npx', 'uvx']:
            command = protocol
            args = f"{package}@{version}"
            if spec_args_str:
                args = f"{args} {spec_args_str}"
        elif protocol == 'go':
            command = 'go'
            args = f"run {package}"
            if spec_args_str:
                args = f"{args} {spec_args_str}"
        else:
            print(f"Error: Unknown protocol {protocol}", file=sys.stderr)
            sys.exit(1)

        # Output JSON with command info and mock_env for security scanning
        output = {
            "command": command,
            "args": args,
            "server_name": server_name,
            "mock_env": mock_env
        }
        if protocol == 'uvx' and uv_overrides:
            output["uv_overrides"] = uv_overrides
        print(json.dumps(output))

    except FileNotFoundError:
        print(f"Error: File {config_file} not found", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
