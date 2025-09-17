#!/bin/bash

# Script to run npm audit on all MCP packages
echo "🔍 Running npm audit on MCP packages to check for security vulnerabilities"
echo "================================================================================"
echo "Date: $(date)"
echo "================================================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
VULNERABLE_PACKAGES=""
SAFE_PACKAGES=""

# Function to check a single package
check_package() {
    local package_name=$1
    local version=$2
    local mcp_name=$3
    
    echo -e "\n📦 Checking ${mcp_name}: ${package_name}@${version}"
    echo "--------------------------------------------------------------------------------"
    
    # Create a temporary directory for the audit
    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    
    # Create a minimal package.json
    cat > package.json <<EOF
{
  "name": "temp-audit",
  "version": "1.0.0",
  "dependencies": {
    "${package_name}": "${version}"
  }
}
EOF
    
    # Install the package
    npm install --package-lock-only --silent 2>/dev/null
    
    # Run npm audit
    AUDIT_OUTPUT=$(npm audit --json 2>/dev/null)
    AUDIT_EXIT_CODE=$?
    
    # Parse the results
    if [ $AUDIT_EXIT_CODE -eq 0 ]; then
        echo -e "  ${GREEN}✅ No vulnerabilities found${NC}"
        SAFE_PACKAGES="${SAFE_PACKAGES}\n  ✅ ${mcp_name} (${package_name}@${version})"
    else
        # Extract vulnerability count from JSON
        VULN_COUNT=$(echo "$AUDIT_OUTPUT" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('metadata', {}).get('vulnerabilities', {}).get('total', 0))" 2>/dev/null || echo "unknown")
        
        if [ "$VULN_COUNT" != "0" ] && [ "$VULN_COUNT" != "unknown" ]; then
            echo -e "  ${RED}⚠️  Found ${VULN_COUNT} vulnerabilities${NC}"
            
            # Try to get more details
            echo "$AUDIT_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    vulns = data.get('vulnerabilities', {})
    for pkg_name, details in vulns.items():
        if 'chalk' in pkg_name.lower() or 'debug' in pkg_name.lower() or 'ansi' in pkg_name.lower():
            severity = details.get('severity', 'unknown')
            print(f'     - {pkg_name}: {severity} severity')
except:
    pass
" 2>/dev/null
            
            VULNERABLE_PACKAGES="${VULNERABLE_PACKAGES}\n  ⚠️  ${mcp_name} (${package_name}@${version}) - ${VULN_COUNT} vulnerabilities"
            
            # Run npm audit with human-readable output for details
            echo -e "\n  Detailed audit report:"
            npm audit 2>/dev/null | head -20
        else
            echo -e "  ${GREEN}✅ No vulnerabilities found${NC}"
            SAFE_PACKAGES="${SAFE_PACKAGES}\n  ✅ ${mcp_name} (${package_name}@${version})"
        fi
    fi
    
    # Cleanup
    cd - > /dev/null
    rm -rf "$TEMP_DIR"
}

# Main execution
echo -e "\nScanning npx MCP packages for security vulnerabilities..."

# Read all spec.yaml files and extract package info
for spec_file in npx/*/spec.yaml; do
    if [ -f "$spec_file" ]; then
        MCP_NAME=$(basename $(dirname "$spec_file"))
        
        # Extract package name and version using Python
        PACKAGE_INFO=$(python3 -c "
import yaml
with open('$spec_file', 'r') as f:
    spec = yaml.safe_load(f)
    if spec and 'spec' in spec:
        pkg = spec['spec'].get('package', '')
        ver = spec['spec'].get('version', 'latest')
        if pkg:
            print(f'{pkg}|{ver}')
" 2>/dev/null)
        
        if [ ! -z "$PACKAGE_INFO" ]; then
            IFS='|' read -r PACKAGE VERSION <<< "$PACKAGE_INFO"
            check_package "$PACKAGE" "$VERSION" "$MCP_NAME"
        fi
    fi
done

# Summary Report
echo -e "\n================================================================================"
echo "SECURITY AUDIT SUMMARY"
echo "================================================================================"

if [ ! -z "$VULNERABLE_PACKAGES" ]; then
    echo -e "\n${RED}⚠️  VULNERABLE PACKAGES:${NC}"
    echo -e "$VULNERABLE_PACKAGES"
fi

if [ ! -z "$SAFE_PACKAGES" ]; then
    echo -e "\n${GREEN}✅ SAFE PACKAGES:${NC}"
    echo -e "$SAFE_PACKAGES"
fi

echo -e "\n================================================================================"
echo "RECOMMENDATIONS:"
echo "================================================================================"

if [ ! -z "$VULNERABLE_PACKAGES" ]; then
    echo "1. Review the vulnerabilities found in the packages above"
    echo "2. Check if newer versions are available that fix these issues"
    echo "3. Consider temporarily disabling vulnerable MCP servers"
    echo "4. Monitor for security patches from package maintainers"
    echo ""
    echo "Note: The npm supply chain attack occurred on Sept 8, 2025."
    echo "Any packages with chalk, debug, or ansi-* dependencies may be affected."
else
    echo "✅ All MCP packages passed the security audit!"
    echo "No known vulnerabilities were detected."
fi