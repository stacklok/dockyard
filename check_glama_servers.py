#!/usr/bin/env python3
"""
Script to check Glama AI MCP servers for npm vulnerabilities using npm audit

Usage:
    python check_glama_servers.py [--api-key-file PATH] [--api-key KEY]
    
    Or set environment variables:
    GLAMA_API_KEY_FILE=/path/to/key.file
    GLAMA_API_KEY=your-api-key-here
"""

import json
import subprocess
import requests
from pathlib import Path
import tempfile
import shutil
from typing import Dict, List, Optional
import re
import os
import argparse
import sys

def read_api_key(api_key_file: Optional[str] = None, api_key: Optional[str] = None):
    """
    Read the Glama AI API key from various sources
    
    Priority order:
    1. Direct api_key parameter
    2. api_key_file parameter
    3. GLAMA_API_KEY environment variable
    4. GLAMA_API_KEY_FILE environment variable
    5. Default path (for backward compatibility)
    """
    # 1. Direct API key
    if api_key:
        return api_key
    
    # 2. API key file from parameter
    if api_key_file:
        key_path = Path(api_key_file)
        if key_path.exists():
            return key_path.read_text().strip()
        else:
            print(f"Warning: API key file not found: {api_key_file}")
    
    # 3. API key from environment
    env_key = os.environ.get("GLAMA_API_KEY")
    if env_key:
        return env_key
    
    # 4. API key file from environment
    env_key_file = os.environ.get("GLAMA_API_KEY_FILE")
    if env_key_file:
        key_path = Path(env_key_file)
        if key_path.exists():
            return key_path.read_text().strip()
        else:
            print(f"Warning: API key file from env not found: {env_key_file}")
    
    return None

def get_npm_package_from_github(repo_url, server_name=None):
    """Extract npm package name from a GitHub repository"""
    if not repo_url or repo_url == "https://github.com/undefined":
        return None
    
    # Convert GitHub URL to raw content URL for package.json
    if "github.com" in repo_url:
        parts = repo_url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) >= 2:
            user, repo = parts[0], parts[1]
            
            # Try multiple branch names
            for branch in ["main", "master", "develop", "dev"]:
                raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/package.json"
                try:
                    response = requests.get(raw_url, timeout=3)
                    if response.status_code == 200:
                        package_data = response.json()
                        pkg_name = package_data.get("name")
                        if pkg_name:
                            return pkg_name
                except:
                    continue
            
            # If no package.json found, try to guess the package name
            # Many MCP servers follow naming patterns
            if server_name:
                # Try common patterns
                guesses = [
                    repo.lower(),  # Repository name
                    f"@{user.lower()}/{repo.lower()}",  # Scoped package
                    server_name.lower().replace(" ", "-"),  # Server name
                    f"mcp-{repo.lower()}",  # mcp- prefix
                    f"{repo.lower()}-mcp",  # -mcp suffix
                ]
                return guesses  # Return list of guesses
    
    return None

def get_glama_mcp_servers(api_key):
    """Get MCP servers from Glama API"""
    print("🔍 Fetching MCP servers from Glama API...")
    
    # The correct endpoint based on the sample response
    url = "https://glama.ai/api/mcp/v1/servers"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    all_servers = []
    has_next_page = True
    cursor = None
    
    while has_next_page:
        # Add pagination parameters
        params = {}
        if cursor:
            params["after"] = cursor
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract servers
                servers = data.get("servers", [])
                all_servers.extend(servers)
                
                # Check pagination
                page_info = data.get("pageInfo", {})
                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
                
                print(f"  Fetched {len(servers)} servers (total: {len(all_servers)})")
                
            else:
                print(f"  Failed to fetch servers: {response.status_code}")
                if response.text:
                    print(f"  Response: {response.text[:200]}")
                break
                
        except Exception as e:
            print(f"  Error: {e}")
            break
    
    # Extract npm packages from GitHub repos
    print(f"\n📦 Extracting npm packages from {len(all_servers)} servers...")
    npm_packages = []
    
    for server in all_servers:
        name = server.get("name", "Unknown")
        repo = server.get("repository", {})
        repo_url = repo.get("url") if repo else None
        
        if repo_url and repo_url != "https://github.com/undefined":
            print(f"  Checking {name}...")
            result = get_npm_package_from_github(repo_url, name)
            
            if result:
                if isinstance(result, str):
                    # Found actual package name
                    print(f"    ✓ Found npm package: {result}")
                    npm_packages.append({
                        "server_name": name,
                        "npm_package": result,
                        "repo_url": repo_url
                    })
                elif isinstance(result, list):
                    # Got guesses, add them all
                    print(f"    🔍 Trying multiple package names...")
                    for guess in result:
                        npm_packages.append({
                            "server_name": name,
                            "npm_package": guess,
                            "repo_url": repo_url,
                            "is_guess": True
                        })
            else:
                print(f"    ✗ No npm package found")
    
    return npm_packages

def fetch_glama_servers_from_html():
    """Fetch and parse MCP servers directly from the Glama website HTML"""
    print("\n📝 Fetching MCP servers from Glama website...")
    
    try:
        response = requests.get("https://glama.ai/mcp/servers", timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch servers page: {response.status_code}")
            return []
        
        html_content = response.text
        
        # More sophisticated extraction
        # Look for npm package patterns in various contexts
        patterns = [
            r'"package":\s*"([^"]+)"',  # JSON-like structures
            r'npm install\s+([@\w/-]+)',  # npm install commands
            r'@[\w-]+/[\w-]+(?:-mcp|-server)',  # Scoped packages with mcp/server
            r'(?:^|\s)([\w-]+(?:-mcp|-server)[\w-]*)',  # Standalone MCP packages
        ]
        
        all_packages = set()
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.MULTILINE | re.IGNORECASE)
            all_packages.update(matches)
        
        # Filter out obvious non-packages
        filtered_packages = []
        for pkg in all_packages:
            # Skip if it's just a pattern or too short
            if len(pkg) > 3 and not pkg.startswith('-') and not pkg.endswith('-'):
                # Clean up the package name
                pkg = pkg.strip()
                if pkg and ' ' not in pkg:  # No spaces in package names
                    filtered_packages.append(pkg)
        
        print(f"Found {len(filtered_packages)} potential MCP packages")
        return list(set(filtered_packages))  # Deduplicate
        
    except Exception as e:
        print(f"Error fetching website: {e}")
        return []

def run_npm_audit(package_name: str, version: str = "latest") -> Optional[Dict]:
    """
    Run npm audit on a specific package
    Returns audit results or None if package doesn't exist
    """
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix="npm_audit_")
        
        # Create package.json
        package_json = {
            "name": "temp-audit",
            "version": "1.0.0",
            "dependencies": {
                package_name: version
            }
        }
        
        package_json_path = Path(temp_dir) / "package.json"
        with open(package_json_path, 'w') as f:
            json.dump(package_json, f)
        
        # Run npm install with package-lock only (faster)
        install_cmd = ["npm", "install", "--package-lock-only", "--silent"]
        install_result = subprocess.run(
            install_cmd,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if install_result.returncode != 0:
            # Package doesn't exist or error
            return None
        
        # Run npm audit
        audit_cmd = ["npm", "audit", "--json"]
        audit_result = subprocess.run(
            audit_cmd,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Parse audit results
        if audit_result.stdout:
            try:
                audit_data = json.loads(audit_result.stdout)
                
                # Extract vulnerability information
                vulnerabilities = audit_data.get('vulnerabilities', {})
                
                # Check specifically for our compromised packages
                compromised_found = []
                for vuln_name, vuln_data in vulnerabilities.items():
                    # Check if it's one of the compromised packages from the attack
                    if any(comp in vuln_name.lower() for comp in [
                        'debug', 'chalk', 'ansi-styles', 'strip-ansi', 
                        'supports-color', 'color-convert', 'wrap-ansi',
                        'ansi-regex', 'color-name', 'is-arrayish', 'error-ex',
                        'color-string', 'simple-swizzle', 'has-ansi',
                        'supports-hyperlinks', 'chalk-template', 'backslash', 'slice-ansi'
                    ]):
                        severity = vuln_data.get('severity', 'unknown')
                        if severity == 'critical':  # The attack packages are marked as critical
                            compromised_found.append({
                                'name': vuln_name,
                                'severity': severity,
                                'via': vuln_data.get('via', [])
                            })
                
                # Get summary
                metadata = audit_data.get('metadata', {})
                total_vulns = metadata.get('vulnerabilities', {}).get('total', 0)
                critical_vulns = metadata.get('vulnerabilities', {}).get('critical', 0)
                
                return {
                    'package': package_name,
                    'version': version,
                    'total_vulnerabilities': total_vulns,
                    'critical_vulnerabilities': critical_vulns,
                    'compromised_packages': compromised_found,
                    'is_affected': len(compromised_found) > 0
                }
                
            except json.JSONDecodeError:
                return None
        
        return None
        
    except subprocess.TimeoutExpired:
        print(f"  ⏱️  Timeout checking {package_name}")
        return None
    except Exception as e:
        print(f"  ❌ Error checking {package_name}: {e}")
        return None
    finally:
        # Clean up temp directory
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)

def check_packages_batch(packages: List, batch_size: int = 5):
    """Check packages in batches to avoid overwhelming the system"""
    results = []
    checked_packages = set()  # Track what we've already checked
    
    # Handle both strings and dicts
    package_list = []
    for item in packages:
        if isinstance(item, str):
            package_list.append({"npm_package": item})
        elif isinstance(item, dict):
            package_list.append(item)
    
    for i in range(0, len(package_list), batch_size):
        batch = package_list[i:i+batch_size]
        print(f"\n📦 Checking batch {i//batch_size + 1} ({len(batch)} packages)...")
        
        for pkg_info in batch:
            package = pkg_info.get("npm_package") if isinstance(pkg_info, dict) else pkg_info
            
            # Skip if already checked
            if package in checked_packages:
                continue
            
            checked_packages.add(package)
            
            is_guess = pkg_info.get("is_guess", False) if isinstance(pkg_info, dict) else False
            prefix = "  🔍 Trying" if is_guess else "  Checking"
            
            print(f"{prefix} {package}...")
            
            # Skip if package is None or empty
            if not package:
                continue
                
            result = run_npm_audit(str(package))
            
            if result:
                # Add server info if available
                if isinstance(pkg_info, dict) and "server_name" in pkg_info:
                    result["server_name"] = pkg_info["server_name"]
                    result["repo_url"] = pkg_info.get("repo_url")
                
                results.append(result)
                if result['is_affected']:
                    print(f"    ⚠️  VULNERABLE - {result['critical_vulnerabilities']} critical vulnerabilities")
                    for comp in result['compromised_packages'][:2]:  # Show first 2
                        print(f"       - {comp['name']} ({comp['severity']})")
                else:
                    print(f"    ✅ Safe - {result['total_vulnerabilities']} vulnerabilities (none from the attack)")
            else:
                if not is_guess:  # Only show skip message for non-guesses
                    print(f"    ⏭️  Skipped - Not an npm package or doesn't exist")
    
    return results

def generate_report(results: List[Dict]):
    """Generate a report of findings"""
    print("\n" + "="*80)
    print("GLAMA AI MCP SERVERS VULNERABILITY REPORT")
    print("="*80)
    print(f"Date: September 8, 2025")
    print(f"Packages successfully audited: {len(results)}")
    
    # Filter affected packages
    affected = [r for r in results if r['is_affected']]
    
    if affected:
        print(f"\n🚨 AFFECTED PACKAGES: {len(affected)} out of {len(results)}")
        print("-"*80)
        
        # Sort by number of vulnerabilities
        affected.sort(key=lambda x: x['critical_vulnerabilities'], reverse=True)
        
        # Show top 10 most affected
        for pkg in affected[:10]:
            print(f"\n📦 {pkg['package']}")
            print(f"   Critical vulnerabilities: {pkg['critical_vulnerabilities']}")
            print(f"   Compromised dependencies:")
            for comp in pkg['compromised_packages'][:3]:  # Show up to 3
                print(f"     - {comp['name']} (severity: {comp['severity']})")
        
        if len(affected) > 10:
            print(f"\n... and {len(affected) - 10} more affected packages")
    else:
        print("\n✅ GOOD NEWS: No packages affected by the npm supply chain attack!")
    
    # Summary
    safe_count = len(results) - len(affected)
    print(f"\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"📊 Total packages audited: {len(results)}")
    print(f"✅ Safe packages: {safe_count}")
    print(f"⚠️  Affected packages: {len(affected)}")
    
    if len(results) > 0:
        compromise_rate = (len(affected) / len(results)) * 100
        print(f"🎯 Compromise rate: {compromise_rate:.1f}%")
    
    if affected:
        print(f"\n⚠️  WARNING: {len(affected)} Glama MCP servers are affected by the npm attack!")
        print("This represents a significant security risk for the MCP ecosystem.")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Check Glama AI MCP servers for npm supply chain attack vulnerabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  GLAMA_API_KEY         Direct API key
  GLAMA_API_KEY_FILE    Path to file containing API key

Examples:
  # Using command line arguments
  python check_glama_servers.py --api-key-file ~/secrets/glama.key
  python check_glama_servers.py --api-key "your-api-key-here"
  
  # Using environment variables
  export GLAMA_API_KEY="your-api-key-here"
  python check_glama_servers.py
  
  # Using file from environment
  export GLAMA_API_KEY_FILE=~/secrets/glama.key
  python check_glama_servers.py
        """
    )
    
    parser.add_argument(
        "--api-key-file",
        help="Path to file containing Glama API key",
        type=str,
        default=None
    )
    
    parser.add_argument(
        "--api-key",
        help="Glama API key (not recommended for security reasons)",
        type=str,
        default=None
    )
    
    parser.add_argument(
        "--output",
        help="Output file for results (default: glama_mcp_audit_results.json)",
        type=str,
        default="glama_mcp_audit_results.json"
    )
    
    parser.add_argument(
        "--batch-size",
        help="Number of packages to check in parallel (default: 5)",
        type=int,
        default=5
    )
    
    args = parser.parse_args()
    
    print("🔍 Checking Glama AI MCP servers for npm supply chain attack vulnerabilities")
    print("Using npm audit for accurate detection")
    print("="*80)
    
    # Get API key
    api_key = read_api_key(args.api_key_file, args.api_key)
    
    if not api_key:
        print("\n❌ No API key found!")
        print("\nPlease provide an API key using one of these methods:")
        print("  1. Command line: --api-key-file /path/to/key.file")
        print("  2. Command line: --api-key 'your-key-here'")
        print("  3. Environment: export GLAMA_API_KEY='your-key-here'")
        print("  4. Environment: export GLAMA_API_KEY_FILE=/path/to/key.file")
        sys.exit(1)
    
    print(f"\n🔑 API key loaded")
    
    # Get servers from Glama API
    server_data = get_glama_mcp_servers(api_key)
    
    if not server_data:
        print("\n❌ No npm packages found in Glama MCP servers")
        return
    
    # Extract just the npm package names
    packages = [item["npm_package"] for item in server_data]
    
    print(f"\n📊 Found {len(packages)} npm packages to check")
    print("Sample packages:", packages[:5] if len(packages) > 5 else packages)
    
    # First, let's try to check ALL packages, even those that might not be published yet
    print("\n🔄 Attempting to check all discovered packages...")
    print(f"Note: Some packages may be private or unpublished\n")
    
    # Check packages for vulnerabilities
    results = check_packages_batch(packages, batch_size=5)  # Reasonable batch size
    
    # Also check packages that failed initially by trying alternative names
    print("\n🔄 Checking alternative package names for failed packages...")
    failed_packages = [p for p in packages if not any(r.get('package') == p for r in results)]
    
    if failed_packages:
        print(f"Retrying {len(failed_packages)} packages with alternative strategies...")
        # Try without scope for scoped packages
        alt_packages = []
        for pkg in failed_packages:
            if pkg.startswith('@'):
                # Try just the package name without scope
                alt_name = pkg.split('/')[-1]
                alt_packages.append(alt_name)
        
        if alt_packages:
            print(f"Trying {len(alt_packages)} alternative names...")
            alt_results = check_packages_batch(alt_packages, batch_size=5)
            results.extend(alt_results)
    
    # Generate report
    generate_report(results)
    
    # Save detailed results with server mapping
    output_file = args.output
    
    # Map results back to server names
    enhanced_results = []
    for result in results:
        npm_package = result.get("package")
        # Find the server name for this package
        server_info = next((s for s in server_data if s["npm_package"] == npm_package), None)
        if server_info:
            result["server_name"] = server_info["server_name"]
            result["repo_url"] = server_info["repo_url"]
        enhanced_results.append(result)
    
    with open(output_file, 'w') as f:
        json.dump({
            "scan_date": "2025-09-08",
            "total_servers_checked": len(server_data),
            "total_npm_packages_found": len(packages),
            "total_vulnerable": len([r for r in results if r.get('is_affected')]),
            "servers": server_data,
            "audit_results": enhanced_results
        }, f, indent=2)
    print(f"\n💾 Detailed results saved to {output_file}")

if __name__ == "__main__":
    main()