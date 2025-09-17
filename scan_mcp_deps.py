#!/usr/bin/env python3
"""
Simplified script to check MCP packages for compromised npm dependencies
"""

import json
import subprocess
import yaml
from pathlib import Path
from typing import Dict, List, Set, Optional

# List of compromised packages from the Sept 8, 2025 attack
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

def check_npm_package(package_name: str, version: Optional[str] = None) -> Dict:
    """Check a single npm package for compromised dependencies"""
    findings = {
        "direct": [],
        "transitive": []
    }
    
    # Check if the package itself is compromised
    base_name = package_name.split("/")[-1] if "/" in package_name else package_name
    if base_name in COMPROMISED_PACKAGES:
        findings["direct"].append({
            "package": package_name,
            "version": version or "unknown"
        })
    
    # Try to get the package's dependencies using npm ls
    try:
        package_spec = f"{package_name}@{version}" if version else package_name
        cmd = f"npm ls --json --package-lock-only --depth=2 {package_spec}"
        
        # First, try to get package info
        info_cmd = f"npm view {package_spec} dependencies --json"
        result = subprocess.run(info_cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout:
            try:
                deps_data = json.loads(result.stdout)
                
                # Handle different response formats
                if isinstance(deps_data, dict):
                    for dep_name, dep_version in deps_data.items():
                        if dep_name in COMPROMISED_PACKAGES:
                            findings["transitive"].append({
                                "package": dep_name,
                                "version": dep_version,
                                "parent": package_name
                            })
                elif isinstance(deps_data, list):
                    for dep in deps_data:
                        if isinstance(dep, str) and dep in COMPROMISED_PACKAGES:
                            findings["transitive"].append({
                                "package": dep,
                                "version": "unknown",
                                "parent": package_name
                            })
            except json.JSONDecodeError:
                pass
    except subprocess.TimeoutExpired:
        print(f"  ⏱️  Timeout checking {package_name}")
    except Exception as e:
        print(f"  ⚠️  Error checking {package_name}: {e}")
    
    return findings

def scan_npx_packages():
    """Scan all npx MCP packages"""
    results = {}
    npx_dir = Path("npx")
    
    if not npx_dir.exists():
        print(f"Error: npx directory not found")
        return results
    
    # Get all spec files
    spec_files = list(npx_dir.glob("*/spec.yaml"))
    print(f"Found {len(spec_files)} MCP packages to scan\n")
    
    for spec_file in spec_files:
        mcp_name = spec_file.parent.name
        
        try:
            with open(spec_file, 'r') as f:
                spec = yaml.safe_load(f)
            
            if spec and 'spec' in spec:
                package_name = spec['spec'].get('package')
                package_version = spec['spec'].get('version')
                
                if package_name:
                    print(f"📦 Checking {mcp_name}: {package_name}@{package_version}")
                    findings = check_npm_package(package_name, package_version)
                    
                    if findings["direct"] or findings["transitive"]:
                        results[mcp_name] = {
                            "package": package_name,
                            "version": package_version,
                            "findings": findings
                        }
                        print(f"  ⚠️  Found compromised dependencies!")
                    else:
                        print(f"  ✅ No compromised dependencies found")
        except Exception as e:
            print(f"  ❌ Error processing {mcp_name}: {e}")
    
    return results

def generate_report(results: Dict):
    """Generate a detailed report"""
    print("\n" + "="*80)
    print("MCP COMPROMISED DEPENDENCY SCAN REPORT")
    print("="*80)
    print(f"Date: September 8, 2025")
    print(f"Compromised packages checked: {len(COMPROMISED_PACKAGES)}")
    print("="*80)
    
    if not results:
        print("\n✅ GOOD NEWS: No compromised dependencies found in any MCP packages!")
        print("\nAll MCP packages appear to be safe from the npm supply chain attack.")
    else:
        print(f"\n⚠️  WARNING: Found issues in {len(results)} MCP package(s):\n")
        
        for mcp_name, data in results.items():
            print(f"\n📦 {mcp_name}")
            print(f"   Package: {data['package']}@{data['version']}")
            
            findings = data['findings']
            
            if findings['direct']:
                print("   🔴 DIRECT COMPROMISED PACKAGES:")
                for dep in findings['direct']:
                    print(f"      - {dep['package']}@{dep['version']}")
            
            if findings['transitive']:
                print("   🟡 TRANSITIVE COMPROMISED DEPENDENCIES:")
                for dep in findings['transitive']:
                    parent = f" (via {dep['parent']})" if 'parent' in dep else ""
                    print(f"      - {dep['package']}@{dep['version']}{parent}")
        
        print("\n" + "="*80)
        print("IMMEDIATE ACTIONS REQUIRED:")
        print("="*80)
        print("1. ⚠️  DO NOT use these MCP packages until they are updated")
        print("2. 📧 Contact the MCP package maintainers about the issue")
        print("3. 🔍 Check for updated versions that fix these dependencies")
        print("4. 🛡️  Monitor npm security advisories for patches")
        print("\nNote: The attack occurred on Sept 8, 2025. Any versions published")
        print("after this date may have fixes for these vulnerabilities.")

if __name__ == "__main__":
    print("🔍 Starting MCP package security scan...")
    print(f"Checking for compromised npm packages from Sept 8, 2025 attack")
    print("-" * 80)
    
    results = scan_npx_packages()
    generate_report(results)
    
    # Return exit code based on findings
    exit(1 if results else 0)