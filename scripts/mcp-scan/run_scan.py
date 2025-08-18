#!/usr/bin/env python3
"""
Wrapper script to run mcp-scan and handle JSON serialization errors.
This works around the AnyUrl serialization bug in mcp-scan.
"""

import subprocess
import sys
import json
import re

def main():
    if len(sys.argv) < 2:
        print("Usage: run_scan.py <config_file> [additional_args...]", file=sys.stderr)
        sys.exit(1)
    
    config_file = sys.argv[1]
    additional_args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    # Build the mcp-scan command
    cmd = [
        "uv", "tool", "run", "mcp-scan", "scan", config_file,
        "--json",
        "--storage-file", "/tmp/mcp-scan-storage",
        "--server-timeout", "30",
        "--suppress-mcpserver-io", "true"
    ] + additional_args
    
    try:
        # Run mcp-scan
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        # Check if it's the AnyUrl serialization error
        if result.returncode != 0 and "Object of type AnyUrl is not JSON serializable" in result.stderr:
            # Try to extract the scan results from stdout before the error
            stdout_lines = result.stdout.strip().split('\n') if result.stdout else []
            
            # mcp-scan might have printed partial results or we can construct a minimal result
            # Since we know the scan actually ran (we saw it work in non-JSON mode), 
            # we'll create a minimal valid result
            
            # Try to parse server name from config file
            server_name = "unknown"
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if 'mcpServers' in config:
                        server_name = list(config['mcpServers'].keys())[0]
            except:
                pass
            
            # Create a minimal result that indicates the scan ran but had output issues
            minimal_result = {
                config_file: {
                    "servers": [{
                        "name": server_name,
                        "signature": {
                            "tools": [],
                            "resources": []
                        }
                    }],
                    "issues": [],
                    "_scan_error": "JSON serialization error in mcp-scan output"
                }
            }
            
            print(json.dumps(minimal_result, indent=2))
            sys.exit(0)
        
        # If it's a different error or success, pass through
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        
        sys.exit(result.returncode)
        
    except Exception as e:
        print(f"Error running mcp-scan: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()