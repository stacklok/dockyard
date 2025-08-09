#!/usr/bin/env python3
"""
Generate MCP configuration from YAML file for mcp-scan.

Usage: generate_mcp_config.py <config_file> <protocol> <server_name>
"""

import yaml
import json
import sys

def main():
    if len(sys.argv) != 4:
        print("Usage: generate_mcp_config.py <config_file> <protocol> <server_name>", file=sys.stderr)
        sys.exit(1)
    
    config_file = sys.argv[1]
    protocol = sys.argv[2]
    server_name = sys.argv[3]
    
    try:
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        if not data or 'spec' not in data:
            print(f"Error: Invalid YAML structure in {config_file}", file=sys.stderr)
            sys.exit(1)
        
        package = data['spec']['package']
        version = data['spec'].get('version', 'latest')
        
        # Determine command based on protocol
        if protocol in ['npx', 'uvx']:
            command = protocol
            args = [f"{package}@{version}"]
        elif protocol == 'go':
            command = 'go'
            args = ['run', package]
        else:
            print(f"Error: Unknown protocol {protocol}", file=sys.stderr)
            sys.exit(1)
        
        # Create MCP server configuration
        mcp_config = {
            "mcpServers": {
                server_name: {
                    "command": command,
                    "args": args,
                    "env": {}
                }
            }
        }
        
        # Output JSON configuration
        print(json.dumps(mcp_config, indent=2))
        
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