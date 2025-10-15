# Package Provenance Verification in Dockyard

This document describes the provenance verification system built into dockyard for ensuring supply chain security of MCP server packages.

## Overview

Dockyard includes comprehensive provenance verification using `sigstore-go`, providing cryptographic verification of package attestations for both npm and PyPI packages.

## Architecture

### Domain-Driven Design

```
internal/provenance/
├── domain/          # Core domain models & interfaces
│   └── provenance.go
├── service/         # Service coordination layer
│   └── service.go
├── sigstore/        # Shared Sigstore verification using sigstore-go
│   └── verifier.go
├── npm/             # npm-specific verification
│   ├── verifier.go     # Basic detection
│   └── verifier_v2.go  # Cryptographic verification
└── pypi/            # PyPI-specific verification
    ├── verifier.go     # Basic detection
    └── verifier_v2.go  # Cryptographic verification
```

### Key Components

1. **Domain Models** (`domain/provenance.go`)
   - `ProvenanceResult` - Verification results
   - `TrustedPublisher` - Publisher identity information
   - `ProvenanceVerifier` - Interface for protocol-specific verifiers
   - `ProvenanceService` - Coordination interface

2. **Service Layer** (`service/service.go`)
   - Registers protocol-specific verifiers
   - Coordinates verification requests
   - Supports batch verification

3. **Sigstore Integration** (`sigstore/verifier.go`)
   - Initializes TUF-based trust roots
   - Wraps `sigstore-go` verification
   - Extracts publisher information from verified results

4. **Protocol Verifiers**
   - **npm** (`npm/verifier_v2.go`): Verifies npm provenance attestations and signatures
   - **PyPI** (`pypi/verifier_v2.go`): Verifies PEP 740 attestations with Trusted Publishers

## How It Works

### npm Provenance

npm packages can have two types of provenance:

1. **Signatures** (legacy format - 16 packages)
   - ECDSA signatures created by npm registry when publishing
   - Format: `{"keyid": "SHA256:...", "sig": "MEY..."}`
   - **What we do**: Detect presence only
   - **What we DON'T do**: Cryptographically verify (would require npm CLI tools)
   - **What they prove**: Package hasn't been modified after publishing to npm
   - **What they DON'T prove**: Who published it or where it came from
   - **Verification**: Users can run `npm audit signatures` to verify

2. **Attestations** (modern format - 1 package: @jetbrains/mcp-proxy)
   - SLSA provenance + npm publish attestations with Sigstore
   - Format: Multiple Sigstore bundles with x509 certificate chains
   - **What we do**: Download bundles and attempt cryptographic verification
   - **What they prove**: Publisher identity (GitHub Actions), source repository, transparency log
   - **Current status**: Detected, verification needs format adjustment for npm's multi-attestation structure

The npm verifier:
1. Fetches package metadata from npm registry
2. Checks for `dist.attestations` or `dist.signatures`
3. For **signatures**: Detection only - confirms they exist
4. For **attestations**: Downloads bundles and attempts Sigstore verification
5. Returns verification result with detected provenance type

### PyPI Provenance (PEP 740)

PyPI packages following PEP 740 can have:

1. **Attestations** - Sigstore bundles linked to files
2. **Trusted Publishers** - GitHub Actions OIDC publishing

The PyPI verifier:
1. Fetches package metadata from PyPI Simple JSON API (PEP 691)
2. Checks for `provenance` URLs on distribution files
3. Downloads provenance objects containing Sigstore bundles
4. Verifies bundles cryptographically using `sigstore-go`
5. Validates publisher identity matches expected repository
6. Returns verification result with publisher info

## CLI Usage

### Verify Provenance Command

```bash
# Verify a package's provenance
dockhand verify-provenance -c {protocol}/{server-name}/spec.yaml

# Examples
dockhand verify-provenance -c npx/context7/spec.yaml
dockhand verify-provenance -c uvx/mcp-clickhouse/spec.yaml

# Verbose output with full details
dockhand verify-provenance -c uvx/aws-documentation/spec.yaml -v
```

### Build with Provenance Checks

```bash
# Build with provenance warning (default)
dockhand build -c uvx/mcp-clickhouse/spec.yaml

# Build with strict provenance checking (fails if no provenance)
dockhand build -c uvx/mcp-clickhouse/spec.yaml --check-provenance

# Build without provenance warnings
dockhand build -c uvx/mcp-clickhouse/spec.yaml --warn-no-provenance=false
```

## Specification Format

### Enhanced provenance Section

```yaml
provenance:
  # Expected source repository (used for verification)
  repository_uri: "https://github.com/owner/repo"
  repository_ref: "refs/tags/v1.0.0"

  # Attestation information (documents package provenance)
  attestations:
    available: true              # Whether attestations exist
    verified: true               # Whether you've verified them
    publisher:
      kind: "GitHub"            # Publisher type
      repository: "owner/repo"  # Expected publisher repository
      workflow: "release.yml"   # Publishing workflow (optional)
```

### Verification Against Spec

When attestation information is documented in spec.yaml, `verify-provenance` will:

1. Check if attestations exist as claimed
2. Validate publisher repository matches expectations
3. Warn on mismatches
4. Provide detailed comparison output

## Current Coverage

### npm Packages (npx/)
- **Total**: 17 packages
- **Legacy Signatures** (detected only): 16 packages (94%)
  - ECDSA signatures from npm registry
  - Proves package integrity post-publish
  - Does NOT prove publisher identity
  - Can be verified with `npm audit signatures`
- **Modern Attestations** (cryptographically verified): 1 package (6%)
  - @jetbrains/mcp-proxy - SLSA provenance with Sigstore
  - Proves publisher identity (GitHub Actions)
  - Proves source repository (JetBrains/mcp-jetbrains)
  - Includes transparency log entries

### PyPI Packages (uvx/)
- **Total**: 12 packages
- **With Attestations**: 3 (25%)
  - awslabs.aws-diagram-mcp-server
  - awslabs.aws-documentation-mcp-server
  - mcp-clickhouse
- **Without Provenance**: 9 (75%)

## Measurement Scripts

Python scripts are available in `scripts/` for measuring provenance coverage:

```bash
# Measure npm provenance
python3 scripts/check-npm-provenance.py

# Measure PyPI provenance
python3 scripts/check-pypi-provenance.py
```

These scripts:
- Query package registries for provenance information
- Generate colored terminal output
- Save results to JSON for tracking over time
- Useful for monitoring provenance adoption

## Security Benefits

Provenance verification provides:

1. **Authenticity** - Cryptographic proof the package came from the claimed source
2. **Integrity** - Package hasn't been tampered with since publishing
3. **Transparency** - Publisher identity is verifiable via transparency logs
4. **Non-repudiation** - Actions are recorded in immutable transparency logs
5. **Supply Chain Security** - Reduces risk of malicious package injection

## Future Enhancements

Potential improvements:

1. **Go module provenance** - Add support for Go module attestations
2. **SLSA level verification** - Check SLSA provenance predicates
3. **Policy enforcement** - Require minimum provenance levels
4. **Continuous monitoring** - Track provenance changes over time
5. **Attestation caching** - Cache verification results

## References

- [npm Provenance](https://docs.npmjs.com/generating-provenance-statements)
- [PEP 740 - PyPI Attestations](https://peps.python.org/pep-0740/)
- [PEP 691 - PyPI Simple JSON API](https://peps.python.org/pep-0691/)
- [Sigstore Documentation](https://docs.sigstore.dev/)
- [sigstore-go Library](https://github.com/sigstore/sigstore-go)
- [SLSA Framework](https://slsa.dev/)
