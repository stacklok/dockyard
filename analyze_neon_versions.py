#!/usr/bin/env python3
"""
Analyze different versions of @neondatabase/mcp-server-neon to find safe versions
"""

import json
import subprocess
from typing import Dict, List, Optional

# Compromised packages to check for
COMPROMISED_PACKAGES = {
    "debug", "chalk", "ansi-styles", "strip-ansi", "supports-color",
    "color-convert", "wrap-ansi", "ansi-regex", "color-name", "is-arrayish",
    "error-ex", "color-string", "simple-swizzle", "has-ansi",
    "supports-hyperlinks", "chalk-template", "backslash", "slice-ansi"
}

def get_package_versions(package_name: str, limit: int = 10) -> List[str]:
    """Get available versions of a package"""
    try:
        cmd = f"npm view {package_name} versions --json"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout:
            versions = json.loads(result.stdout)
            # Return the last N versions (most recent)
            return versions[-limit:] if len(versions) > limit else versions
        return []
    except Exception as e:
        print(f"Error getting versions: {e}")
        return []

def check_version_dependencies(package_name: str, version: str) -> Dict:
    """Check a specific version for compromised dependencies"""
    findings = {
        "version": version,
        "compromised": [],
        "safe": True
    }
    
    try:
        # Get direct dependencies
        cmd = f"npm view {package_name}@{version} dependencies --json"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                deps = json.loads(result.stdout)
                if isinstance(deps, dict):
                    for dep_name, dep_version in deps.items():
                        if dep_name in COMPROMISED_PACKAGES:
                            findings["compromised"].append({
                                "package": dep_name,
                                "version": dep_version
                            })
                            findings["safe"] = False
            except json.JSONDecodeError:
                pass
        
        # Also check peer dependencies
        cmd = f"npm view {package_name}@{version} peerDependencies --json"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                peer_deps = json.loads(result.stdout)
                if isinstance(peer_deps, dict):
                    for dep_name, dep_version in peer_deps.items():
                        if dep_name in COMPROMISED_PACKAGES:
                            findings["compromised"].append({
                                "package": dep_name,
                                "version": dep_version,
                                "type": "peer"
                            })
                            findings["safe"] = False
            except json.JSONDecodeError:
                pass
                
    except Exception as e:
        print(f"  Error checking version {version}: {e}")
    
    return findings

def analyze_package(package_name: str):
    """Analyze multiple versions of a package"""
    print(f"🔍 Analyzing package: {package_name}")
    print("=" * 80)
    
    # Get available versions
    print("\n📦 Fetching available versions...")
    versions = get_package_versions(package_name, limit=15)
    
    if not versions:
        print("❌ Could not fetch package versions")
        return
    
    print(f"Found {len(versions)} recent versions to analyze")
    print("-" * 80)
    
    safe_versions = []
    unsafe_versions = []
    
    # Check each version
    for version in reversed(versions):  # Check from newest to oldest
        print(f"\n🔎 Checking version {version}...")
        findings = check_version_dependencies(package_name, version)
        
        if findings["safe"]:
            print(f"  ✅ SAFE - No compromised dependencies found")
            safe_versions.append(version)
        else:
            print(f"  ⚠️  UNSAFE - Found compromised dependencies:")
            for dep in findings["compromised"]:
                dep_type = f" ({dep.get('type', 'direct')})" if 'type' in dep else ""
                print(f"     - {dep['package']}@{dep['version']}{dep_type}")
            unsafe_versions.append((version, findings["compromised"]))
    
    # Generate recommendations
    print("\n" + "=" * 80)
    print("📊 ANALYSIS SUMMARY")
    print("=" * 80)
    
    print(f"\n📦 Package: {package_name}")
    print(f"📈 Versions analyzed: {len(versions)}")
    print(f"✅ Safe versions: {len(safe_versions)}")
    print(f"⚠️  Unsafe versions: {len(unsafe_versions)}")
    
    if safe_versions:
        print("\n🎯 RECOMMENDED SAFE VERSIONS:")
        for v in safe_versions[-5:]:  # Show last 5 safe versions
            print(f"  ✅ {v}")
        
        print(f"\n💡 RECOMMENDATION:")
        latest_safe = safe_versions[-1]
        print(f"  Use version {latest_safe} - it's the most recent safe version")
        print(f"\n  To update your spec.yaml, change the version to: {latest_safe}")
    else:
        print("\n⚠️  WARNING: No safe versions found in the analyzed range!")
        print("  Consider:")
        print("  1. Waiting for a patched version from the maintainer")
        print("  2. Using an alternative MCP server")
        print("  3. Temporarily disabling this MCP server")
    
    # Show current vs recommended
    print("\n" + "=" * 80)
    print("📝 UPDATE INSTRUCTIONS")
    print("=" * 80)
    
    if safe_versions:
        print(f"\nTo use a safe version, update npx/mcp-server-neon/spec.yaml:")
        print(f"\nCurrent version: 0.6.4 (UNSAFE - contains chalk@5.3.0)")
        print(f"Recommended version: {safe_versions[-1]} (SAFE)")
        print(f"\nChange the 'version' field in both metadata and spec sections to: {safe_versions[-1]}")

if __name__ == "__main__":
    package = "@neondatabase/mcp-server-neon"
    analyze_package(package)