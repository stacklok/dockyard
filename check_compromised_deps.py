#!/usr/bin/env python3
"""
Script to check MCP packages for compromised npm dependencies
"""

import json
import subprocess
import yaml
from pathlib import Path
from typing import Dict, List, Set, Optional

# List of compromised packages from the attack
COMPROMISED_PACKAGES = {
    "debug",
    "chalk",
    "ansi-styles",
    "strip-ansi",
    "supports-color",
    "color-convert",
    "wrap-ansi",
    "ansi-regex",
    "color-name",
    "is-arrayish",
    "error-ex",
    "color-string",
    "simple-swizzle",
    "has-ansi",
    "supports-hyperlinks",
    "chalk-template",
    "backslash",
    "slice-ansi"
}

def get_npm_package_info(package_name: str, version: Optional[str] = None) -> Dict:
    """Get package info from npm registry"""
    try:
        if version:
            cmd = f"npm view {package_name}@{version} dependencies --json"
        else:
            cmd = f"npm view {package_name} dependencies --json"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        return {}
    except Exception as e:
        print(f"Error getting info for {package_name}: {e}")
        return {}

def check_dependencies(package_name: str, version: Optional[str] = None, depth: int = 0, checked: Optional[Set] = None) -> List[Dict]:
    """Recursively check dependencies for compromised packages"""
    if checked is None:
        checked = set()
    
    if depth > 2:  # Limit recursion depth
        return []
    
    package_key = f"{package_name}@{version}" if version else package_name
    if package_key in checked:
        return []
    
    checked.add(package_key)
    findings = []
    
    # Check if this package itself is compromised
    if package_name in COMPROMISED_PACKAGES:
        findings.append({
            "package": package_name,
            "version": version,
            "type": "direct" if depth == 0 else "transitive",
            "depth": depth
        })
    
    # Get and check dependencies
    deps = get_npm_package_info(package_name, version)
    
    # Handle both dict and list responses from npm
    if isinstance(deps, dict):
        dep_items = deps.items()
    elif isinstance(deps, list):
        # Sometimes npm returns a list of package names without versions
        dep_items = [(dep, "latest") if isinstance(dep, str) else (dep, "latest") for dep in deps]
    else:
        dep_items = []
    
    for dep_name, dep_version in dep_items:
        if dep_name in COMPROMISED_PACKAGES:
            findings.append({
                "package": dep_name,
                "version": dep_version,
                "type": "transitive",
                "depth": depth + 1,
                "parent": package_name
            })
        
        # Recursively check sub-dependencies (limit depth to avoid too many API calls)
        if depth < 1:  # Only go 1 level deep for now
            sub_findings = check_dependencies(dep_name, dep_version, depth + 1, checked)
            findings.extend(sub_findings)
    
    return findings

def scan_mcp_packages():
    """Scan all npx MCP packages for compromised npm dependencies"""
    results = {}
    
    # Scan npx packages (Node.js packages only)
    npx_dir = Path("npx")
    if not npx_dir.exists():
        print(f"Error: npx directory not found at {npx_dir}")
        return results
    
    for mcp_dir in npx_dir.iterdir():
        if mcp_dir.is_dir():
            spec_file = mcp_dir / "spec.yaml"
            if spec_file.exists():
                with open(spec_file, 'r') as f:
                    spec = yaml.safe_load(f)
                
                if spec and 'spec' in spec:
                    package_name = spec['spec'].get('package')
                    package_version = spec['spec'].get('version')
                    
                    if package_name:
                        print(f"\nChecking {mcp_dir.name}: {package_name}@{package_version}")
                        findings = check_dependencies(package_name, package_version)
                        
                        if findings:
                            results[mcp_dir.name] = {
                                "package": package_name,
                                "version": package_version,
                                "compromised_deps": findings
                            }
    
    return results

def generate_report(results: Dict):
    """Generate a report of findings"""
    print("\n" + "="*80)
    print("COMPROMISED DEPENDENCY SCAN REPORT")
    print("="*80)
    
    if not results:
        print("\n✅ No compromised dependencies found in any MCP packages!")
    else:
        print(f"\n⚠️  Found compromised dependencies in {len(results)} MCP package(s):\n")
        
        for mcp_name, data in results.items():
            print(f"\n📦 {mcp_name}")
            print(f"   Package: {data['package']}@{data['version']}")
            print(f"   Compromised dependencies found:")
            
            for dep in data['compromised_deps']:
                indent = "   " + "  " * dep['depth']
                dep_type = f"[{dep['type']}]"
                parent_info = f" (via {dep['parent']})" if 'parent' in dep else ""
                print(f"{indent}└─ {dep['package']}@{dep['version']} {dep_type}{parent_info}")
        
        print("\n" + "="*80)
        print("RECOMMENDATIONS:")
        print("="*80)
        print("1. Check if updated versions of these MCP packages are available")
        print("2. Monitor for security patches from the package maintainers")
        print("3. Consider temporarily disabling affected MCPs if critical")
        print("4. Review the specific versions - the attack occurred on Sept 8, 2025")

if __name__ == "__main__":
    print("Starting scan for compromised npm dependencies in npx MCP packages...")
    print(f"Checking for these compromised packages: {', '.join(sorted(COMPROMISED_PACKAGES))}")
    print("-" * 80)
    
    results = scan_mcp_packages()
    generate_report(results)