#!/usr/bin/env python3
"""
Process mcp-scan results and generate a summary.

Usage: process_scan_results.py <scan_output_file> <server_name>
"""

import json
import sys

def main():
    if len(sys.argv) != 3:
        print("Usage: process_scan_results.py <scan_output_file> <server_name>", file=sys.stderr)
        sys.exit(1)
    
    scan_output_file = sys.argv[1]
    server_name = sys.argv[2]
    
    try:
        with open(scan_output_file, 'r') as f:
            content = f.read()
        
        # Try to find JSON in the output (mcp-scan may include other text)
        json_start = content.find('{')
        if json_start == -1:
            # No JSON found in output
            summary = {
                'server': server_name,
                'status': 'warning',
                'message': 'No JSON output found in scan results'
            }
            print(json.dumps(summary, indent=2))
            return
        
        # Parse the JSON data
        scan_data = json.loads(content[json_start:])
        
        # Check for vulnerabilities
        has_vulnerabilities = False
        vulnerability_details = []
        tools_scanned = 0
        
        # The actual mcp-scan output structure has the config path as key
        for config_path, config_data in scan_data.items():
            if isinstance(config_data, dict):
                # Count tools from the servers array
                if 'servers' in config_data and isinstance(config_data['servers'], list):
                    for server in config_data['servers']:
                        if 'signature' in server and 'tools' in server['signature']:
                            tools_scanned += len(server['signature']['tools'])
                
                # Check for issues/vulnerabilities
                if 'issues' in config_data and isinstance(config_data['issues'], list):
                    for issue in config_data['issues']:
                        has_vulnerabilities = True
                        vulnerability_details.append({
                            'code': issue.get('code', 'unknown'),
                            'message': issue.get('message', 'Unknown vulnerability'),
                            'reference': issue.get('reference'),
                            'extra_data': issue.get('extra_data')
                        })
        
        # Generate summary
        if has_vulnerabilities:
            summary = {
                'server': server_name,
                'status': 'failed',
                'tools_scanned': tools_scanned,
                'vulnerabilities': vulnerability_details,
                'vulnerability_count': len(vulnerability_details)
            }
            
            # Print human-readable output to stderr for CI logs
            print(f"❌ Security vulnerabilities found in {server_name}:", file=sys.stderr)
            for vuln in vulnerability_details:
                print(f"  - [{vuln['code']}] {vuln['message']}", file=sys.stderr)
            
            # Exit with error code to fail the CI step
            print(json.dumps(summary, indent=2))
            sys.exit(1)
        else:
            summary = {
                'server': server_name,
                'status': 'passed',
                'tools_scanned': tools_scanned,
                'message': 'No security vulnerabilities detected'
            }
            
            # Print success message to stderr for CI logs
            print(f"✅ No security vulnerabilities found in {server_name} ({tools_scanned} tools scanned)", file=sys.stderr)
            
            print(json.dumps(summary, indent=2))
            
    except FileNotFoundError:
        summary = {
            'server': server_name,
            'status': 'error',
            'message': f'Scan output file not found: {scan_output_file}'
        }
        print(json.dumps(summary, indent=2))
        print(f"⚠️ Error: {summary['message']}", file=sys.stderr)
        sys.exit(1)
        
    except json.JSONDecodeError as e:
        summary = {
            'server': server_name,
            'status': 'warning',
            'message': f'Could not parse scan results: {str(e)}'
        }
        print(json.dumps(summary, indent=2))
        print(f"⚠️ Warning: {summary['message']}", file=sys.stderr)
        
    except Exception as e:
        summary = {
            'server': server_name,
            'status': 'error',
            'message': f'Unexpected error: {str(e)}'
        }
        print(json.dumps(summary, indent=2))
        print(f"⚠️ Error: {summary['message']}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()