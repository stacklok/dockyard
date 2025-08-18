#!/usr/bin/env python3
"""
Process mcp-scan results and generate a summary.

Usage: process_scan_results.py <scan_output_file> <server_name> [config_file]
"""

import json
import sys
import yaml
import os

def load_security_config(config_file=None):
    """
    Load security configuration from the YAML configuration file.
    
    Returns a tuple of (allowed_issues dict, insecure_ignore bool).
    """
    allowed_issues = {}
    insecure_ignore = False
    
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                
            if config and 'security' in config:
                security_config = config['security']
                
                # Check for insecure_ignore flag
                insecure_ignore = security_config.get('insecure_ignore', False)
                
                # Check for allowed_issues
                if 'allowed_issues' in security_config:
                    for issue in security_config['allowed_issues']:
                        if 'code' in issue:
                            allowed_issues[issue['code']] = issue.get('reason', 'Explicitly allowed')
        except Exception as e:
            print(f"Warning: Could not load security config from {config_file}: {e}", file=sys.stderr)
    
    return allowed_issues, insecure_ignore

def main():
    if len(sys.argv) < 3:
        print("Usage: process_scan_results.py <scan_output_file> <server_name> [config_file]", file=sys.stderr)
        sys.exit(1)
    
    scan_output_file = sys.argv[1]
    server_name = sys.argv[2]
    config_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Load security configuration from config
    allowed_issues, insecure_ignore = load_security_config(config_file)
    
    try:
        with open(scan_output_file, 'r') as f:
            content = f.read()
        
        # Check if file is empty (scan failed to produce output)
        if not content.strip():
            if insecure_ignore:
                summary = {
                    'server': server_name,
                    'status': 'warning',
                    'tools_scanned': 0,
                    'message': 'Scan failed to produce output (insecure_ignore is enabled)'
                }
                print(f"⚠️ Warning: Scan failed for {server_name} but insecure_ignore is enabled - proceeding", file=sys.stderr)
                print(json.dumps(summary, indent=2))
                return
            else:
                summary = {
                    'server': server_name,
                    'status': 'error',
                    'message': 'Scan failed to produce output'
                }
                print(f"❌ Error: Scan failed for {server_name}", file=sys.stderr)
                print(json.dumps(summary, indent=2))
                sys.exit(1)
        
        # Try to find JSON in the output (mcp-scan may include other text)
        json_start = content.find('{')
        if json_start == -1:
            # No JSON found in output
            if insecure_ignore:
                summary = {
                    'server': server_name,
                    'status': 'warning',
                    'tools_scanned': 0,
                    'message': 'No JSON output found in scan results (insecure_ignore is enabled)'
                }
                print(f"⚠️ Warning: No JSON output for {server_name} but insecure_ignore is enabled - proceeding", file=sys.stderr)
                print(json.dumps(summary, indent=2))
                return
            else:
                summary = {
                    'server': server_name,
                    'status': 'error',
                    'message': 'No JSON output found in scan results'
                }
                print(f"❌ Error: No JSON output found for {server_name}", file=sys.stderr)
                print(json.dumps(summary, indent=2))
                sys.exit(1)
        
        # Parse the JSON data
        scan_data = json.loads(content[json_start:])
        
        # Check for vulnerabilities
        has_blocking_issues = False
        blocking_issues = []
        allowed_issues_found = []
        tools_scanned = 0
        
        # The actual mcp-scan output structure has the config path as key
        for config_path, config_data in scan_data.items():
            if isinstance(config_data, dict):
                # Count tools from the servers array
                if 'servers' in config_data and isinstance(config_data['servers'], list):
                    for server in config_data['servers']:
                        if 'signature' in server and server['signature'] and 'tools' in server['signature']:
                            tools_scanned += len(server['signature']['tools'])
                
                # Check for issues/vulnerabilities
                if 'issues' in config_data and isinstance(config_data['issues'], list):
                    for issue in config_data['issues']:
                        issue_code = issue.get('code', 'unknown')
                        issue_detail = {
                            'code': issue_code,
                            'message': issue.get('message', 'Unknown vulnerability'),
                            'reference': issue.get('reference'),
                            'extra_data': issue.get('extra_data')
                        }
                        
                        # Check if this issue is explicitly allowed
                        if issue_code in allowed_issues:
                            issue_detail['allowed_reason'] = allowed_issues[issue_code]
                            allowed_issues_found.append(issue_detail)
                        else:
                            has_blocking_issues = True
                            blocking_issues.append(issue_detail)
        
        # Generate summary
        if has_blocking_issues:
            summary = {
                'server': server_name,
                'status': 'failed',
                'tools_scanned': tools_scanned,
                'blocking_issues': blocking_issues,
                'blocking_count': len(blocking_issues),
                'allowed_issues': allowed_issues_found,
                'allowed_count': len(allowed_issues_found)
            }
            
            # Print human-readable output to stderr for CI logs
            print(f"❌ Security issues found in {server_name} that are not allowlisted:", file=sys.stderr)
            for issue in blocking_issues:
                print(f"  - [{issue['code']}] {issue['message']}", file=sys.stderr)
            
            if allowed_issues_found:
                print(f"ℹ️  Allowed issues (not blocking):", file=sys.stderr)
                for issue in allowed_issues_found:
                    print(f"  - [{issue['code']}] {issue['message']} (Allowed: {issue['allowed_reason']})", file=sys.stderr)
            
            # Exit with error code to fail the CI step
            print(json.dumps(summary, indent=2))
            sys.exit(1)
        else:
            summary = {
                'server': server_name,
                'status': 'passed',
                'tools_scanned': tools_scanned,
                'message': 'No blocking security issues detected'
            }
            
            if allowed_issues_found:
                summary['allowed_issues'] = allowed_issues_found
                summary['allowed_count'] = len(allowed_issues_found)
                
                # Print info about allowed issues
                print(f"ℹ️  Allowed security issues found in {server_name}:", file=sys.stderr)
                for issue in allowed_issues_found:
                    print(f"  - [{issue['code']}] {issue['message']}", file=sys.stderr)
                    print(f"    Reason: {issue['allowed_reason']}", file=sys.stderr)
                print(f"✅ All issues are allowlisted - build can proceed ({tools_scanned} tools scanned)", file=sys.stderr)
            else:
                # Print success message to stderr for CI logs
                print(f"✅ No security issues found in {server_name} ({tools_scanned} tools scanned)", file=sys.stderr)
            
            print(json.dumps(summary, indent=2))
            
    except FileNotFoundError:
        if insecure_ignore:
            summary = {
                'server': server_name,
                'status': 'warning',
                'tools_scanned': 0,
                'message': f'Scan output file not found (insecure_ignore is enabled): {scan_output_file}'
            }
            print(f"⚠️ Warning: {summary['message']}", file=sys.stderr)
            print(json.dumps(summary, indent=2))
        else:
            summary = {
                'server': server_name,
                'status': 'error',
                'message': f'Scan output file not found: {scan_output_file}'
            }
            print(f"❌ Error: {summary['message']}", file=sys.stderr)
            print(json.dumps(summary, indent=2))
            sys.exit(1)
        
    except json.JSONDecodeError as e:
        if insecure_ignore:
            summary = {
                'server': server_name,
                'status': 'warning',
                'tools_scanned': 0,
                'message': f'Could not parse scan results (insecure_ignore is enabled): {str(e)}'
            }
            print(f"⚠️ Warning: {summary['message']}", file=sys.stderr)
            print(json.dumps(summary, indent=2))
        else:
            summary = {
                'server': server_name,
                'status': 'error',
                'message': f'Could not parse scan results: {str(e)}'
            }
            print(f"❌ Error: {summary['message']}", file=sys.stderr)
            print(json.dumps(summary, indent=2))
            sys.exit(1)
        
    except Exception as e:
        if insecure_ignore:
            summary = {
                'server': server_name,
                'status': 'warning',
                'tools_scanned': 0,
                'message': f'Unexpected error (insecure_ignore is enabled): {str(e)}'
            }
            print(f"⚠️ Warning: {summary['message']}", file=sys.stderr)
            print(json.dumps(summary, indent=2))
        else:
            summary = {
                'server': server_name,
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            }
            print(f"❌ Error: {summary['message']}", file=sys.stderr)
            print(json.dumps(summary, indent=2))
            sys.exit(1)

if __name__ == "__main__":
    main()