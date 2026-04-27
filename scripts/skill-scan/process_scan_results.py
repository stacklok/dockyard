#!/usr/bin/env python3
"""Process Cisco AI Defense skill-scanner results and emit a summary.

The skill-scanner report is a single JSON document with a flat
`findings[]` array. Each finding carries `rule_id`, `category`,
`severity`, plus file/line context. This script applies a two-tier
allowlist (global + per-skill spec.yaml) and exits non-zero when any
finding is NOT allowlisted.

Usage:
    process_scan_results.py <scan_output_file> <skill_name> [spec_file]
"""

import json
import os
import sys

import yaml


GLOBAL_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "global_allowed_issues.yaml")

# Higher rank = more severe. Unknown severities are treated as blocking (rank
# = max + 1) so an unrecognized value never silently slips past the gate.
SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
DEFAULT_BLOCK_SEVERITY = "HIGH"


def _block_severity_threshold() -> int:
    raw = os.environ.get("SKILL_SCANNER_BLOCK_SEVERITY", DEFAULT_BLOCK_SEVERITY)
    rank = SEVERITY_RANK.get((raw or "").strip().upper())
    return rank if rank is not None else SEVERITY_RANK[DEFAULT_BLOCK_SEVERITY]


def _is_blocking_severity(severity: str | None, threshold: int) -> bool:
    rank = SEVERITY_RANK.get((severity or "").strip().upper())
    if rank is None:
        return True
    return rank >= threshold


def _load_allowed_entries(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            config = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: could not load {path}: {exc}", file=sys.stderr)
        return []
    entries = config.get("allowed_issues") or []
    return [e for e in entries if isinstance(e, dict)]


def load_security_config(spec_file: str | None) -> tuple[list[dict], bool]:
    """Merge global and per-skill allowlist entries.

    Per-skill entries are appended after global entries; both are
    checked on match. Returns (entries, insecure_ignore).
    """
    entries: list[dict] = _load_allowed_entries(GLOBAL_CONFIG_FILE)
    insecure_ignore = False

    if spec_file and os.path.exists(spec_file):
        try:
            with open(spec_file) as f:
                spec = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: could not load {spec_file}: {exc}", file=sys.stderr)
            spec = {}

        security = spec.get("security") or {}
        insecure_ignore = bool(security.get("insecure_ignore", False))
        per_skill = security.get("allowed_issues") or []
        entries.extend([e for e in per_skill if isinstance(e, dict)])

    return entries, insecure_ignore


def match_allowlist(finding: dict, entries: list[dict]) -> tuple[bool, str | None]:
    """Return (allowed, reason). Match by rule_id (exact) or category (broader)."""
    rule_id = finding.get("rule_id") or ""
    category = finding.get("category") or ""
    for entry in entries:
        if entry.get("rule_id") and entry["rule_id"] == rule_id:
            return True, entry.get("reason", "Explicitly allowed")
        if entry.get("category") and entry["category"] == category:
            return True, entry.get("reason", f"Category '{category}' allowed")
    return False, None


def classify_findings(
    scan: dict, entries: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    blocking: list[dict] = []
    warnings: list[dict] = []
    allowed: list[dict] = []
    threshold = _block_severity_threshold()
    for finding in scan.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        detail = {
            "code": finding.get("rule_id") or finding.get("id") or "unknown",
            "rule_id": finding.get("rule_id"),
            "category": finding.get("category"),
            "severity": finding.get("severity"),
            "analyzer": finding.get("analyzer"),
            "title": finding.get("title"),
            "message": finding.get("description") or finding.get("title") or "",
            "file_path": finding.get("file_path"),
            "line_number": finding.get("line_number"),
        }
        is_allowed, reason = match_allowlist(finding, entries)
        if is_allowed:
            detail["allowed_reason"] = reason
            allowed.append(detail)
        elif _is_blocking_severity(finding.get("severity"), threshold):
            blocking.append(detail)
        else:
            warnings.append(detail)
    return blocking, warnings, allowed


def _warn_summary(skill_name: str, message: str) -> dict:
    return {
        "skill": skill_name,
        "status": "warning",
        "findings_count": 0,
        "message": message,
    }


def _error_summary(skill_name: str, message: str) -> dict:
    return {
        "skill": skill_name,
        "status": "error",
        "message": message,
    }


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: process_scan_results.py <scan_output_file> <skill_name> [spec_file]",
            file=sys.stderr,
        )
        sys.exit(1)

    scan_file = sys.argv[1]
    skill_name = sys.argv[2]
    spec_file = sys.argv[3] if len(sys.argv) > 3 else None

    entries, insecure_ignore = load_security_config(spec_file)

    try:
        with open(scan_file) as f:
            content = f.read()
    except FileNotFoundError:
        summary = (
            _warn_summary(skill_name, f"Scan output not found: {scan_file}")
            if insecure_ignore
            else _error_summary(skill_name, f"Scan output not found: {scan_file}")
        )
        print(json.dumps(summary, indent=2))
        sys.exit(0 if insecure_ignore else 1)

    if not content.strip():
        summary = (
            _warn_summary(skill_name, "Scan produced empty output")
            if insecure_ignore
            else _error_summary(skill_name, "Scan produced empty output")
        )
        print(json.dumps(summary, indent=2))
        sys.exit(0 if insecure_ignore else 1)

    try:
        scan = json.loads(content)
    except json.JSONDecodeError as exc:
        summary = (
            _warn_summary(skill_name, f"Could not parse scan output: {exc}")
            if insecure_ignore
            else _error_summary(skill_name, f"Could not parse scan output: {exc}")
        )
        print(json.dumps(summary, indent=2))
        sys.exit(0 if insecure_ignore else 1)

    blocking, warnings, allowed = classify_findings(scan, entries)
    analyzers = scan.get("analyzers_used") or []
    findings_count = scan.get("findings_count", len(scan.get("findings") or []))

    def _format_loc(issue: dict) -> str:
        if not issue.get("file_path"):
            return ""
        loc = f" ({issue['file_path']}"
        if issue.get("line_number"):
            loc += f":{issue['line_number']}"
        return loc + ")"

    def _print_warnings() -> None:
        if not warnings:
            return
        threshold_name = os.environ.get(
            "SKILL_SCANNER_BLOCK_SEVERITY", DEFAULT_BLOCK_SEVERITY
        ).upper()
        print(
            f"Below-threshold findings (block threshold = {threshold_name}, not blocking):",
            file=sys.stderr,
        )
        for issue in warnings:
            print(
                f"  - [{issue['code']}] ({issue['severity']}) {issue['message']}{_format_loc(issue)}",
                file=sys.stderr,
            )

    def _print_allowed() -> None:
        if not allowed:
            return
        print("Allowlisted (not blocking):", file=sys.stderr)
        for issue in allowed:
            print(
                f"  - [{issue['code']}] {issue['message']} (Allowed: {issue['allowed_reason']})",
                file=sys.stderr,
            )

    if blocking:
        summary = {
            "skill": skill_name,
            "status": "failed",
            "findings_count": findings_count,
            "analyzers": analyzers,
            "blocking_issues": blocking,
            "blocking_count": len(blocking),
            "warning_issues": warnings,
            "warning_count": len(warnings),
            "allowed_issues": allowed,
            "allowed_count": len(allowed),
        }
        print(f"Skill security scan FAILED for {skill_name}:", file=sys.stderr)
        for issue in blocking:
            print(
                f"  - [{issue['code']}] ({issue['severity']}) {issue['message']}{_format_loc(issue)}",
                file=sys.stderr,
            )
        _print_warnings()
        _print_allowed()
        print(json.dumps(summary, indent=2))
        sys.exit(1)

    summary = {
        "skill": skill_name,
        "status": "passed",
        "findings_count": findings_count,
        "analyzers": analyzers,
        "message": "No blocking security issues detected",
    }
    if warnings:
        summary["warning_issues"] = warnings
        summary["warning_count"] = len(warnings)
    if allowed:
        summary["allowed_issues"] = allowed
        summary["allowed_count"] = len(allowed)

    if warnings or allowed:
        print(
            f"Skill security scan passed for {skill_name} with non-blocking findings:",
            file=sys.stderr,
        )
        _print_warnings()
        _print_allowed()
    else:
        print(f"Skill security scan passed for {skill_name} (no findings)", file=sys.stderr)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
