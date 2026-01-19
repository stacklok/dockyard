#!/usr/bin/env python3
"""
Generate SCAI (Software Supply Chain Attribute Integrity) attestation for MCP security scans.

This script creates an in-toto attestation following the SCAI predicate specification:
https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md

Usage:
    generate_scai_attestation.py <scan_summary_file> <image_name> <image_digest> \
        --config-file <config> --commit-sha <sha> --run-id <id> --run-url <url>

Output:
    Writes the SCAI attestation JSON to stdout.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# SCAI predicate type and version
# Reference: https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md
SCAI_PREDICATE_TYPE = "https://in-toto.io/attestation/scai/v0.3"
INTOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"


def compute_file_sha256(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def load_scan_summary(file_path: str) -> dict[str, Any]:
    """Load and parse the scan summary JSON file."""
    with open(file_path) as f:
        return json.load(f)


def load_spec_yaml(file_path: str) -> dict[str, Any]:
    """Load and parse the spec.yaml configuration file."""
    with open(file_path) as f:
        return yaml.safe_load(f)


def determine_attribute(scan_status: str) -> str:
    """Determine the SCAI attribute based on scan status."""
    if scan_status == "passed":
        return "MCP_SECURITY_SCAN_PASSED"
    elif scan_status == "warning":
        return "MCP_SECURITY_SCAN_WARNING"
    else:
        return "MCP_SECURITY_SCAN_FAILED"


def build_scai_attestation(
    scan_summary: dict[str, Any],
    scan_summary_path: str,
    image_name: str,
    image_digest: str,
    config_file: str,
    commit_sha: str,
    run_id: str,
    run_url: str,
    producer_uri: str,
    scanner_version: str | None = None,
    scanner_uri: str | None = None,
    source_repository: str | None = None,
) -> dict[str, Any]:
    """
    Build a SCAI attestation for the MCP security scan.

    Args:
        scan_summary: Parsed scan summary data
        scan_summary_path: Path to the scan summary file (for hash computation)
        image_name: Full image name (e.g., ghcr.io/stacklok/dockyard/npx/context7)
        image_digest: Image digest with sha256: prefix
        config_file: Path to the spec.yaml config file
        commit_sha: Git commit SHA
        run_id: GitHub Actions run ID
        run_url: URL to the GitHub Actions run
        producer_uri: Full URI of the producer (e.g., https://github.com/stacklok/dockyard)
        scanner_version: Version of the scanner (e.g., "4.1.0")
        scanner_uri: URI to the scanner source (e.g., "https://github.com/cisco-ai-defense/mcp-scanner")
        source_repository: Optional URI of the MCP server's source repository

    Returns:
        Complete in-toto Statement with SCAI predicate
    """
    # Extract analyzers from scan summary (from scanner output)
    analyzers = scan_summary.get("analyzers", ["yara"])

    # Extract scan results
    scan_status = scan_summary.get("status", "unknown")
    tools_scanned = scan_summary.get("tools_scanned", 0)
    blocking_count = scan_summary.get("blocking_count", 0)
    allowed_count = scan_summary.get("allowed_count", 0)

    # Compute evidence hash
    evidence_hash = compute_file_sha256(scan_summary_path)

    # Current timestamp
    scan_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine attribute based on status
    attribute = determine_attribute(scan_status)

    # Strip sha256: prefix from digest if present
    digest_value = image_digest
    if digest_value.startswith("sha256:"):
        digest_value = digest_value[7:]

    # Build conditions - include scanner metadata and source repository if available
    conditions: dict[str, Any] = {
        "scanner": "cisco-ai-mcp-scanner",
        "analyzers": analyzers,
        "toolsScanned": tools_scanned,
        "blockingIssues": blocking_count,
        "allowedIssues": allowed_count,
        "scanDate": scan_date,
        "configFile": config_file
    }

    # Add scanner version if provided
    if scanner_version:
        conditions["scannerVersion"] = scanner_version

    # Add scanner URI if provided
    if scanner_uri:
        conditions["scannerUri"] = scanner_uri

    # Add source repository provenance if available
    if source_repository:
        conditions["sourceRepository"] = source_repository

    # Build the SCAI attestation following the spec
    # Reference: https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md
    attestation = {
        "_type": INTOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": image_name,
                "digest": {
                    "sha256": digest_value
                }
            }
        ],
        "predicateType": SCAI_PREDICATE_TYPE,
        "predicate": {
            "attributes": [
                {
                    "attribute": attribute,
                    "conditions": conditions,
                    "evidence": {
                        "name": "scan-summary.json",
                        "digest": {
                            "sha256": evidence_hash
                        },
                        "uri": run_url,
                        "mediaType": "application/json"
                    }
                }
            ],
            "producer": {
                "uri": producer_uri,
                "name": "dockyard-ci",
                "digest": {
                    "gitCommit": commit_sha
                }
            }
        }
    }

    return attestation


def validate_attestation(attestation: dict[str, Any]) -> list[str]:
    """
    Validate the SCAI attestation structure.

    Returns a list of validation errors (empty if valid).
    """
    errors = []

    # Check required top-level fields
    if attestation.get("_type") != INTOTO_STATEMENT_TYPE:
        errors.append(f"Invalid _type: expected {INTOTO_STATEMENT_TYPE}")

    if attestation.get("predicateType") != SCAI_PREDICATE_TYPE:
        errors.append(f"Invalid predicateType: expected {SCAI_PREDICATE_TYPE}")

    # Check subject
    subjects = attestation.get("subject", [])
    if not subjects:
        errors.append("Missing subject")
    for i, subj in enumerate(subjects):
        if not subj.get("name"):
            errors.append(f"Subject {i}: missing name")
        if not subj.get("digest"):
            errors.append(f"Subject {i}: missing digest")

    # Check predicate
    predicate = attestation.get("predicate", {})
    attributes = predicate.get("attributes", [])
    if not attributes:
        errors.append("Missing attributes in predicate")

    for i, attr in enumerate(attributes):
        if not attr.get("attribute"):
            errors.append(f"Attribute {i}: missing attribute field")
        # Evidence should have at least name, URI, or digest per SCAI spec
        evidence = attr.get("evidence", {})
        if evidence and not (evidence.get("name") or evidence.get("uri") or evidence.get("digest")):
            errors.append(f"Attribute {i}: evidence must have name, uri, or digest")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Generate SCAI attestation for MCP security scans"
    )
    parser.add_argument(
        "scan_summary_file",
        help="Path to the scan summary JSON file"
    )
    parser.add_argument(
        "image_name",
        help="Full container image name"
    )
    parser.add_argument(
        "image_digest",
        help="Container image digest (sha256:...)"
    )
    parser.add_argument(
        "--config-file",
        required=True,
        help="Path to the spec.yaml config file"
    )
    parser.add_argument(
        "--commit-sha",
        required=True,
        help="Git commit SHA"
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="GitHub Actions run ID"
    )
    parser.add_argument(
        "--run-url",
        required=True,
        help="URL to the GitHub Actions run"
    )
    parser.add_argument(
        "--producer-uri",
        required=True,
        help="Full URI of the attestation producer (e.g., https://github.com/stacklok/dockyard)"
    )
    parser.add_argument(
        "--scanner-version",
        help="Version of the scanner (e.g., 4.1.0)"
    )
    parser.add_argument(
        "--scanner-uri",
        default="https://github.com/cisco-ai-defense/mcp-scanner",
        help="URI to the scanner source (default: https://github.com/cisco-ai-defense/mcp-scanner)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the attestation structure"
    )

    args = parser.parse_args()

    # Load scan summary
    try:
        scan_summary = load_scan_summary(args.scan_summary_file)
    except FileNotFoundError:
        print(f"Error: Scan summary file not found: {args.scan_summary_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in scan summary: {e}", file=sys.stderr)
        sys.exit(1)

    # Load spec.yaml to extract source repository provenance
    source_repository = None
    try:
        spec = load_spec_yaml(args.config_file)
        provenance = spec.get("provenance", {})
        source_repository = provenance.get("repository_uri")
        if source_repository:
            print(f"Source repository: {source_repository}", file=sys.stderr)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Warning: Could not read spec.yaml for provenance: {e}", file=sys.stderr)

    # Build attestation
    attestation = build_scai_attestation(
        scan_summary=scan_summary,
        scan_summary_path=args.scan_summary_file,
        image_name=args.image_name,
        image_digest=args.image_digest,
        config_file=args.config_file,
        commit_sha=args.commit_sha,
        run_id=args.run_id,
        run_url=args.run_url,
        producer_uri=args.producer_uri,
        scanner_version=args.scanner_version,
        scanner_uri=args.scanner_uri,
        source_repository=source_repository,
    )

    # Validate if requested
    if args.validate:
        errors = validate_attestation(attestation)
        if errors:
            print("Validation errors:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)

    # Output
    output_json = json.dumps(attestation, indent=2)

    if args.output:
        Path(args.output).write_text(output_json)
        print(f"Attestation written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
