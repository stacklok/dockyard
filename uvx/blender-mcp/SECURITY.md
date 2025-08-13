# Security Analysis: blender-mcp MCP Server

## Overview
The blender-mcp package has been flagged with two security issues by mcp-scan:
- **TF001**: Data leak toxic flow detected
- **TF002**: Destructive toxic flow detected

## Analysis Results: ⚠️ BOTH ISSUES ARE VALID

### TF001: Data Leak Toxic Flow - VALID CONCERN

**Issue**: The same agent has access to tools that produce untrusted content, access private data, and behave as public sinks.

**Root Cause Analysis**:

1. **Untrusted Content Sources** (6 tools):
   - `search_sketchfab_models()` - Downloads models from public internet
   - `download_sketchfab_model()` - Imports external 3D models  
   - `search_polyhaven_assets()` - Accesses external asset library
   - `download_polyhaven_asset()` - Downloads external textures/models/HDRIs
   - `generate_hyper3d_model_via_text()` - Generates content from AI service
   - `generate_hyper3d_model_via_images()` - Generates content from user images

2. **Private Data Access** (3 tools):
   - `get_scene_info()` - Accesses current Blender scene data
   - `get_object_info()` - Reads object properties and metadata  
   - `get_viewport_screenshot()` - Captures screen content (potentially sensitive)

3. **Public Sink Capabilities** (7 tools):
   - `execute_blender_code()` - **CRITICAL**: Executes arbitrary Python code
   - Various download functions with file system access
   - Network communications to external services

**Attack Vector**: 
An attacker could use `execute_blender_code()` to read sensitive scene data and exfiltrate it through network requests to external services.

### TF002: Destructive Toxic Flow - VALID CONCERN

**Issue**: The same agent has access to tools that produce untrusted content and tools that can behave destructively.

**Root Cause Analysis**:

1. **Untrusted Content** (same 6 tools as above)

2. **Destructive Capabilities** (6 tools):
   - `execute_blender_code()` - **CRITICAL**: Can execute any Python code including:
     - File system modifications
     - Scene destruction/modification  
     - System command execution
     - Network operations
   - Download functions can overwrite local files
   - Scene modification through various asset import tools

**Attack Vector**:
Malicious content from external sources could trigger destructive operations through the code execution tool or file system modifications.

## Risk Assessment

### High Risk Components
1. **`execute_blender_code()`** - Arbitrary Python code execution
2. **External content downloads** - Untrusted data sources
3. **File system operations** - Potential for data corruption/loss

### Legitimate Use Cases
- Creative workflows requiring external asset integration
- Blender automation and scripting
- AI-assisted 3D content creation

## Security Allowlist

The following security issues have been explicitly allowed in the package configuration:

```yaml
security:
  allowed_issues:
    - code: "TF001"
      reason: "Data leak risk acceptable - tool designed for creative workflows where external content integration is essential. Users should be aware of potential data exposure through code execution capabilities."
    - code: "TF002" 
      reason: "Destructive flow risk acceptable - execute_blender_code tool is core functionality for Blender automation. Users should only use with trusted prompts and in isolated environments."
```

## Security Best Practices for Users

### ⚠️ IMPORTANT WARNINGS

1. **Use in isolated environments** (containers, VMs, or dedicated machines)
2. **Only use with trusted prompts** and content sources
3. **Regularly backup Blender projects** before using the MCP server
4. **Monitor network activity** when using external integrations
5. **Review generated code** before execution when possible
6. **Avoid using with sensitive or proprietary 3D models**

### Recommended Usage Patterns

✅ **SAFE**:
- Using in containerized environments
- Working with non-sensitive creative projects
- Using with trusted AI assistants and prompts
- Educational and learning purposes

❌ **RISKY**:
- Using with proprietary or confidential 3D models
- Running on production systems with sensitive data
- Using with untrusted or malicious prompts
- Running without proper backups

## Conclusion

Both TF001 and TF002 are **legitimate security concerns** that accurately identify real risks in the blender-mcp package. The risks have been accepted because:

1. **Core Functionality**: The `execute_blender_code()` tool is essential for Blender automation
2. **Creative Workflows**: External content integration is fundamental to the tool's purpose
3. **User Awareness**: Users can make informed decisions about acceptable risk levels

**Users should understand these risks and take appropriate precautions when using this MCP server.**