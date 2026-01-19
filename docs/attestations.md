# Dockyard Container Attestations

This document describes the attestations attached to Dockyard container images for supply chain security.

## Overview

Every container image published to `ghcr.io/stacklok/dockyard` includes multiple attestations:

| Type | Predicate Type | Description |
|------|---------------|-------------|
| SBOM | SPDX | Software Bill of Materials (via Docker buildx) |
| Build Provenance | SLSA | Build provenance attestation (via Docker buildx) |
| **MCP Security Scan** | **SCAI v0.3** | Cisco AI Defense mcp-scanner results |
| Signature | Sigstore | Keyless OIDC signature via Cosign |

## MCP Security Scan Attestation (SCAI)

The MCP security scan attestation uses the [SCAI (Software Supply Chain Attribute Integrity)](https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md) predicate type, an official in-toto attestation format.

### Predicate Type

```
https://in-toto.io/attestation/scai/v0.3
```

### Schema

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{
    "name": "ghcr.io/stacklok/dockyard/npx/context7",
    "digest": { "sha256": "..." }
  }],
  "predicateType": "https://in-toto.io/attestation/scai/v0.3",
  "predicate": {
    "attributes": [{
      "attribute": "MCP_SECURITY_SCAN_PASSED",
      "conditions": {
        "scanner": "cisco-ai-mcp-scanner",
        "analyzers": ["yara"],
        "toolsScanned": 5,
        "blockingIssues": 0,
        "allowedIssues": 1,
        "scanDate": "2026-01-19T12:00:00Z",
        "configFile": "npx/context7/spec.yaml",
        "sourceRepository": "https://github.com/upstash/context7"
      },
      "evidence": {
        "name": "scan-summary.json",
        "digest": { "sha256": "..." },
        "uri": "https://github.com/stacklok/dockyard/actions/runs/...",
        "mediaType": "application/json"
      }
    }],
    "producer": {
      "uri": "https://github.com/stacklok/dockyard",
      "name": "dockyard-ci",
      "digest": { "gitCommit": "..." }
    }
  }
}
```

### Attributes

| Attribute | Description |
|-----------|-------------|
| `MCP_SECURITY_SCAN_PASSED` | Scan completed with no blocking security issues |
| `MCP_SECURITY_SCAN_WARNING` | Scan completed with warnings (insecure_ignore enabled) |
| `MCP_SECURITY_SCAN_FAILED` | Scan found blocking security issues |

### Conditions

| Field | Type | Description |
|-------|------|-------------|
| `scanner` | string | Scanner tool identifier (`cisco-ai-mcp-scanner`) |
| `analyzers` | array | List of analyzers used (`yara`, `llm`) |
| `toolsScanned` | number | Number of MCP tools scanned |
| `blockingIssues` | number | Count of blocking security issues |
| `allowedIssues` | number | Count of allowed (non-blocking) issues |
| `scanDate` | string | ISO 8601 timestamp of scan |
| `configFile` | string | Path to the spec.yaml configuration |
| `sourceRepository` | string | Source repository of the MCP server (from spec.yaml provenance) |

### Evidence

The `evidence` field links to the full scan results artifact:

- `name`: Artifact filename (`scan-summary.json`)
- `digest.sha256`: SHA256 hash of the scan summary for integrity verification
- `uri`: Link to the GitHub Actions run where scan was performed
- `mediaType`: Content type (`application/json`)

## Verification

### Verify Image Signature

```bash
cosign verify ghcr.io/stacklok/dockyard/npx/context7:latest
```

### Verify MCP Security Scan Attestation

```bash
cosign verify-attestation \
  --type https://in-toto.io/attestation/scai/v0.3 \
  ghcr.io/stacklok/dockyard/npx/context7:latest
```

### Download and Inspect Attestation

```bash
# Download all attestations
cosign download attestation ghcr.io/stacklok/dockyard/npx/context7:latest

# Decode and pretty-print SCAI attestation
cosign download attestation ghcr.io/stacklok/dockyard/npx/context7:latest | \
  jq -r 'select(.payloadType == "application/vnd.in-toto+json") | .payload | @base64d | fromjson'
```

### View SBOM

```bash
docker buildx imagetools inspect \
  ghcr.io/stacklok/dockyard/npx/context7:latest \
  --format "{{ json .SBOM }}"
```

## Policy Enforcement

### Kyverno Example

Enforce that only images with passing MCP security scans can be deployed:

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-mcp-security-scan
spec:
  validationFailureAction: Enforce
  rules:
    - name: check-mcp-scan-attestation
      match:
        resources:
          kinds:
            - Pod
      verifyImages:
        - imageReferences:
            - "ghcr.io/stacklok/dockyard/*"
          attestations:
            - type: https://in-toto.io/attestation/scai/v0.3
              attestors:
                - entries:
                    - keyless:
                        issuer: https://token.actions.githubusercontent.com
                        subject: "https://github.com/stacklok/dockyard/.github/workflows/build-containers.yml@*"
              conditions:
                - all:
                    - key: "{{ attributes[0].attribute }}"
                      operator: Equals
                      value: "MCP_SECURITY_SCAN_PASSED"
```

### OPA/Gatekeeper Example

```rego
package dockyard.security

deny[msg] {
  input.predicate.attributes[_].attribute != "MCP_SECURITY_SCAN_PASSED"
  msg := "MCP security scan did not pass"
}

deny[msg] {
  input.predicate.attributes[_].conditions.blockingIssues > 0
  msg := sprintf("Found %d blocking security issues", [input.predicate.attributes[_].conditions.blockingIssues])
}
```

## References

- [SCAI Specification](https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md)
- [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
- [Sigstore Cosign](https://docs.sigstore.dev/cosign/)
- [Cisco AI Defense mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner)
- [Kyverno Image Verification](https://kyverno.io/docs/writing-policies/verify-images/)
