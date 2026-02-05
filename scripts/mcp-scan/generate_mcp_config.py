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

        if protocol in ['npx', 'uvx']:
            command = protocol
            args = f"{package}@{version}"
        elif protocol == 'go':
            command = 'go'
            args = f"run {package}"
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
