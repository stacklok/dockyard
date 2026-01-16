#!/usr/bin/env python3
"""
Process Cisco AI Defense mcp-scanner results and generate a summary.

Usage: process_scan_results.py <scan_output_file> <server_name> [config_file]
"""

import json
import sys
import yaml
import os

# Global config file location (relative to this script)
GLOBAL_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'global_allowed_issues.yaml')


def load_global_allowed_issues():
    """
    Load globally allowed issues from the global config file.

    Returns a dict of {issue_code: reason}.
    """
    allowed_issues = {}

    if os.path.exists(GLOBAL_CONFIG_FILE):
        try:
            with open(GLOBAL_CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f)

            if config and 'allowed_issues' in config:
                for issue in config['allowed_issues']:
                    if 'code' in issue:
                        allowed_issues[issue['code']] = issue.get('reason', 'Globally allowed')
        except Exception as e:
            print(f"Warning: Could not load global config from {GLOBAL_CONFIG_FILE}: {e}", file=sys.stderr)

    return allowed_issues


def load_security_config(config_file=None):
    """
    Load security configuration from the YAML configuration file.

    Returns a tuple of (allowed_issues dict, insecure_ignore bool).
    Merges global allowed issues with per-server allowed issues.
    """
    # Start with globally allowed issues
    allowed_issues = load_global_allowed_issues()
    insecure_ignore = False

    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            if config and 'security' in config:
                security_config = config['security']

                # Check for insecure_ignore flag
                insecure_ignore = security_config.get('insecure_ignore', False)

                # Check for allowed_issues (merge with global, per-server takes precedence)
                if 'allowed_issues' in security_config:
                    for issue in security_config['allowed_issues']:
                        if 'code' in issue:
                            allowed_issues[issue['code']] = issue.get('reason', 'Explicitly allowed')
        except Exception as e:
            print(f"Warning: Could not load security config from {config_file}: {e}", file=sys.stderr)

    return allowed_issues, insecure_ignore


def is_issue_allowed(aitech, aisubtech, allowed_issues):
    """
    Check if issue is allowed. Supports prefix matching:
    - AITech-1.1 matches allowlist entry "AITech-1.1" (exact)
    - AISubtech-1.1.1 matches allowlist entry "AITech-1.1" (parent)
    - AITech-1.1 matches allowlist entry "AITech-1" (grandparent)

    Args:
        aitech: The AITech code (e.g., "AITech-1.1")
        aisubtech: The AISubtech code (e.g., "AISubtech-1.1.1")
        allowed_issues: Dict of allowed issue codes to reasons
    """
    codes_to_check = []

    # Add the sub-technique code if present
    if aisubtech:
        codes_to_check.append(aisubtech)
        # Also try mapping AISubtech-X.Y.Z to AITech-X.Y
        if aisubtech.startswith('AISubtech-'):
            # AISubtech-1.1.1 -> AITech-1.1
            parts = aisubtech.replace('AISubtech-', '').split('.')
            if len(parts) >= 2:
                codes_to_check.append(f"AITech-{parts[0]}.{parts[1]}")

    # Add the technique code if present
    if aitech:
        codes_to_check.append(aitech)
        # Also check parent (AITech-1.1 -> AITech-1)
        if aitech.startswith('AITech-'):
            parts = aitech.replace('AITech-', '').split('.')
            if len(parts) > 1:
                codes_to_check.append(f"AITech-{parts[0]}")

    for code in codes_to_check:
        if code in allowed_issues:
            return True, allowed_issues[code]
    return False, None


def process_cisco_scan_results(scan_data, allowed_issues):
    """
    Process Cisco AI Defense mcp-scanner output format.

    Actual output structure (verified via local testing):
    {
      "server_url": "stdio:npx @package@version",
      "scan_results": [
        {
          "status": "completed",
          "is_safe": false,
          "findings": {
            "yara_analyzer": {
              "severity": "HIGH",
              "threat_names": ["PROMPT INJECTION"],
              "threat_summary": "Detected 1 threat: coercive injection",
              "total_findings": 1,
              "mcp_taxonomies": [
                {
                  "scanner_category": "PROMPT INJECTION",
                  "aitech": "AITech-1.1",
                  "aitech_name": "Direct Prompt Injection",
                  "aisubtech": "AISubtech-1.1.1",
                  "aisubtech_name": "Instruction Manipulation",
                  "description": "..."
                }
              ]
            }
          },
          "tool_name": "tool-name",
          "tool_description": "...",
          "item_type": "tool"
        }
      ],
      "requested_analyzers": ["yara"]
    }
    """
    tools_scanned = 0
    blocking_issues = []
    allowed_issues_found = []

    # Handle different possible data structures
    if isinstance(scan_data, list):
        scan_results = scan_data
    elif isinstance(scan_data, dict):
        scan_results = (
            scan_data.get('scan_results') or
            scan_data.get('tools') or
            scan_data.get('results') or
            []
        )
    else:
        scan_results = []

    for item in scan_results:
        if not isinstance(item, dict):
            continue

        # Count tools
        item_type = item.get('item_type', 'tool')
        if item_type == 'tool' or 'tool_name' in item:
            tools_scanned += 1

        tool_name = item.get('tool_name', 'unknown')

        # Check findings from all analyzers
        findings = item.get('findings', {})
        for analyzer_name, analyzer_data in findings.items():
            if not isinstance(analyzer_data, dict):
                continue

            severity = analyzer_data.get('severity', 'UNKNOWN')

            # Parse mcp_taxonomies array (the actual structure from Cisco scanner)
            mcp_taxonomies = analyzer_data.get('mcp_taxonomies', [])

            for taxonomy in mcp_taxonomies:
                if not isinstance(taxonomy, dict):
                    continue

                aitech = taxonomy.get('aitech', '')
                aitech_name = taxonomy.get('aitech_name', '')
                aisubtech = taxonomy.get('aisubtech', '')
                aisubtech_name = taxonomy.get('aisubtech_name', '')
                description = taxonomy.get('description', '')
                scanner_category = taxonomy.get('scanner_category', '')

                # Use AITech code as the primary issue code
                issue_code = aitech
                issue_detail = {
                    'code': issue_code,
                    'aitech': aitech,
                    'aitech_name': aitech_name,
                    'aisubtech': aisubtech,
                    'aisubtech_name': aisubtech_name,
                    'severity': severity,
                    'category': scanner_category,
                    'message': description or f"{aitech_name}: {aisubtech_name}",
                    'tool_name': tool_name,
                    'analyzer': analyzer_name
                }

                # Check if this issue is allowed
                is_allowed, reason = is_issue_allowed(aitech, aisubtech, allowed_issues)
                if is_allowed:
                    issue_detail['allowed_reason'] = reason
                    allowed_issues_found.append(issue_detail)
                else:
                    blocking_issues.append(issue_detail)

    return tools_scanned, blocking_issues, allowed_issues_found


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

        # Try to find JSON in the output
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
        # Use a JSON decoder that stops at the end of the first valid JSON object
        # This handles cases where there might be extra output after the JSON
        json_content = content[json_start:]
        decoder = json.JSONDecoder()
        try:
            scan_data, end_idx = decoder.raw_decode(json_content)
        except json.JSONDecodeError:
            # Fall back to regular parsing for better error messages
            scan_data = json.loads(json_content)

        # Process Cisco scanner results
        tools_scanned, blocking_issues, allowed_issues_found = process_cisco_scan_results(
            scan_data, allowed_issues
        )

        # Generate summary
        has_blocking_issues = len(blocking_issues) > 0

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
                if issue.get('tool_name'):
                    print(f"    Tool: {issue['tool_name']}", file=sys.stderr)

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
