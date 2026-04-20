#!/usr/bin/env python3
"""Generate a SCAI attestation for a skill security scan.

Follows the in-toto SCAI predicate specification:
https://github.com/in-toto/attestation/blob/main/spec/predicates/scai.md

Usage:
    generate_scai_attestation.py <scan_summary_file> <image_name> <image_digest> \
        --config-file <spec.yaml> --commit-sha <sha> --run-id <id> --run-url <url> \
        --producer-uri <uri> [--scanner-version VERSION]
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SCAI_PREDICATE_TYPE = "https://in-toto.io/attestation/scai/v0.3"
INTOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"


def compute_file_sha256(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_json(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def load_yaml(path: str) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def determine_attribute(status: str) -> str:
    if status == "passed":
        return "SKILL_SECURITY_SCAN_PASSED"
    if status == "warning":
        return "SKILL_SECURITY_SCAN_WARNING"
    return "SKILL_SECURITY_SCAN_FAILED"


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
    analyzers = scan_summary.get("analyzers") or []
    status = scan_summary.get("status", "unknown")
    findings_count = scan_summary.get("findings_count", 0)
    blocking_count = scan_summary.get("blocking_count", 0)
    allowed_count = scan_summary.get("allowed_count", 0)

    evidence_hash = compute_file_sha256(scan_summary_path)
    scan_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    attribute = determine_attribute(status)

    digest_value = image_digest
    if digest_value.startswith("sha256:"):
        digest_value = digest_value[7:]

    conditions: dict[str, Any] = {
        "scanner": "cisco-ai-skill-scanner",
        "analyzers": analyzers,
        "findingsCount": findings_count,
        "blockingIssues": blocking_count,
        "allowedIssues": allowed_count,
        "scanDate": scan_date,
        "configFile": config_file,
    }
    if scanner_version:
        conditions["scannerVersion"] = scanner_version
    if scanner_uri:
        conditions["scannerUri"] = scanner_uri
    if source_repository:
        conditions["sourceRepository"] = source_repository
    # Include run_id in the attribute conditions so the attestation can be
    # traced back to the exact CI run even if run_url format changes.
    if run_id:
        conditions["runId"] = run_id

    return {
        "_type": INTOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": image_name,
                "digest": {"sha256": digest_value},
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
                        "digest": {"sha256": evidence_hash},
                        "uri": run_url,
                        "mediaType": "application/json",
                    },
                }
            ],
            "producer": {
                "uri": producer_uri,
                "name": "dockyard-ci",
                "digest": {"gitCommit": commit_sha},
            },
        },
    }


def validate_attestation(att: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if att.get("_type") != INTOTO_STATEMENT_TYPE:
        errors.append(f"Invalid _type: expected {INTOTO_STATEMENT_TYPE}")
    if att.get("predicateType") != SCAI_PREDICATE_TYPE:
        errors.append(f"Invalid predicateType: expected {SCAI_PREDICATE_TYPE}")
    subjects = att.get("subject") or []
    if not subjects:
        errors.append("Missing subject")
    for i, s in enumerate(subjects):
        if not s.get("name"):
            errors.append(f"Subject {i}: missing name")
        if not s.get("digest"):
            errors.append(f"Subject {i}: missing digest")
    predicate = att.get("predicate") or {}
    attributes = predicate.get("attributes") or []
    if not attributes:
        errors.append("Missing attributes in predicate")
    for i, a in enumerate(attributes):
        if not a.get("attribute"):
            errors.append(f"Attribute {i}: missing attribute field")
        evidence = a.get("evidence") or {}
        if evidence and not (evidence.get("name") or evidence.get("uri") or evidence.get("digest")):
            errors.append(f"Attribute {i}: evidence must have name, uri, or digest")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SCAI attestation for skill security scans"
    )
    parser.add_argument("scan_summary_file", help="Path to the scan summary JSON file")
    parser.add_argument("image_name", help="Full OCI artifact name (no tag)")
    parser.add_argument("image_digest", help="OCI artifact digest (sha256:...)")
    parser.add_argument("--config-file", required=True, help="Path to the skill spec.yaml")
    parser.add_argument("--commit-sha", required=True, help="Git commit SHA")
    parser.add_argument("--run-id", required=True, help="GitHub Actions run ID")
    parser.add_argument("--run-url", required=True, help="URL to the GitHub Actions run")
    parser.add_argument(
        "--producer-uri",
        required=True,
        help="Full URI of the attestation producer (e.g. https://github.com/stacklok/dockyard)",
    )
    parser.add_argument("--scanner-version", help="Version of the scanner (e.g. 2.0.9)")
    parser.add_argument(
        "--scanner-uri",
        default="https://github.com/cisco-ai-defense/skill-scanner",
        help="URI to the scanner source",
    )
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--validate", action="store_true", help="Validate the attestation structure")

    args = parser.parse_args()

    try:
        scan_summary = load_json(args.scan_summary_file)
    except FileNotFoundError:
        print(f"Error: scan summary not found: {args.scan_summary_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in scan summary: {exc}", file=sys.stderr)
        sys.exit(1)

    source_repository: str | None = None
    try:
        spec = load_yaml(args.config_file)
        provenance = spec.get("provenance") or {}
        source_repository = provenance.get("repository_uri") or (spec.get("spec") or {}).get("repository")
        if source_repository:
            print(f"Source repository: {source_repository}", file=sys.stderr)
    except (FileNotFoundError, yaml.YAMLError) as exc:
        print(f"Warning: could not read spec.yaml for provenance: {exc}", file=sys.stderr)

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

    if args.validate:
        errors = validate_attestation(attestation)
        if errors:
            print("Validation errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)

    output_json = json.dumps(attestation, indent=2)
    if args.output:
        Path(args.output).write_text(output_json)
        print(f"Attestation written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
