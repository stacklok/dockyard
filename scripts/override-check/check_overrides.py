#!/usr/bin/env python3
"""Check whether an npx spec's `overrides` would downgrade anything.

npm `overrides` are tree-global exact pins. If upstream later raises its own
floor above our pin, the pin silently drags that copy back down and nothing
else (Grype included) notices. This resolves the dependency tree WITHOUT the
overrides, collects every version of each overridden package, and reports
which copies the pin raises and which it lowers.

Always exits 0 for a readable spec: findings are reported in the summary JSON,
not as a failure. Grype remains the only hard gate.

Usage: check_overrides.py <spec.yaml> [--output summary.json]
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$")


def semver_key(version):
    """Sort key for a semver string; prereleases sort below their release."""
    m = _SEMVER.match(version)
    if not m:
        raise ValueError(f"not a semver version: {version!r}")
    major, minor, patch, pre = m.groups()
    if pre is None:
        pre_key = (1,)
    else:
        pre_key = (0, *[(0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")])
    return (int(major), int(minor), int(patch), pre_key)


def versions_in_lock(lock, package):
    """Every distinct version of `package` present in a package-lock.json."""
    found = set()
    for key, entry in lock.get("packages", {}).items():
        if not key or entry.get("link"):
            continue
        # "node_modules/a/node_modules/@scope/pkg" -> "@scope/pkg"
        if key.rsplit("node_modules/", 1)[-1] == package and "version" in entry:
            found.add(entry["version"])
    return sorted(found, key=semver_key)


def classify(package, pin, versions):
    """Compare an exact pin against the versions otherwise in the tree."""
    pin_key = semver_key(pin)
    return {
        "package": package,
        "pin": pin,
        "versions": versions,
        "raises": [v for v in versions if semver_key(v) < pin_key],
        "lowers": [v for v in versions if semver_key(v) > pin_key],
        "unchanged": [v for v in versions if semver_key(v) == pin_key],
        # Pin sits below the highest version otherwise present.
        "downgrade": bool(versions) and pin_key < semver_key(versions[-1]),
        # Package is nowhere in the un-overridden tree.
        "absent": not versions,
    }


def resolve_without_overrides(package, version):
    """Resolve the tree for `package@version` with no overrides; return the lock."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "package.json").write_text(
            json.dumps({"name": "override-check", "version": "1.0.0",
                        "dependencies": {package: version}})
        )
        subprocess.run(
            ["npm", "install", "--package-lock-only", "--no-audit", "--no-fund",
             "--ignore-scripts"],
            cwd=tmp, check=True, capture_output=True, text=True, timeout=300,
        )
        return json.loads((Path(tmp) / "package-lock.json").read_text())


def check_spec(spec_path):
    spec = yaml.safe_load(Path(spec_path).read_text())
    name = spec["metadata"]["name"]
    if spec["metadata"].get("protocol") != "npx":
        return None
    overrides = spec["spec"].get("overrides") or []
    if not overrides:
        return None

    summary = {"server": name, "status": "ok", "overrides": []}
    try:
        lock = resolve_without_overrides(spec["spec"]["package"], spec["spec"]["version"])
        for o in overrides:
            summary["overrides"].append(
                classify(o["package"], o["version"], versions_in_lock(lock, o["package"]))
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as e:
        detail = getattr(e, "stderr", None) or str(e)
        summary["status"] = "error"
        summary["message"] = detail.strip()[-500:]
        return summary

    if any(o["downgrade"] for o in summary["overrides"]):
        summary["status"] = "downgrade"
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("spec")
    parser.add_argument("--output", default="override-check-summary.json")
    args = parser.parse_args(argv)

    summary = check_spec(args.spec)
    if summary is None:
        print(f"{args.spec}: no npx overrides, nothing to check")
        return 0
    Path(args.output).write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{summary['server']}: {summary['status']}")
    for o in summary["overrides"]:
        print(f"  {o['package']} pin {o['pin']}: tree has {o['versions'] or 'nothing'}"
              f" (raises {o['raises']}, lowers {o['lowers']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
