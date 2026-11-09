#!/usr/bin/env python3
"""
Reconcile the active Python environment with requirements.txt one
package at a time.

For every non-comment line in requirements.txt:
  - Parse the package name and the `==` pinned version (if present).
  - If the package is not installed -> `pip install <spec>`.
  - If installed at the pinned version -> skip.
  - If installed at a different version -> `pip install <spec>` to
    upgrade or downgrade to the pinned version.
  - If the spec has no `==` pin and the package is installed, leave it
    alone.

Failed installs do not abort the run; they are collected and reported
at the end so a single broken package does not block the rest.

Run from the project root with the target environment's Python:
    python install_requirements.py
"""

from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import re
import subprocess
import sys

try:
    from packaging.version import InvalidVersion, Version
except ImportError:
    Version = None
    InvalidVersion = Exception

PROJECT_ROOT = Path(__file__).resolve().parent
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"

_NAME_SPLIT_RE = re.compile(r"[=<>!~;\[\s]")
_PINNED_VERSION_RE = re.compile(r"==\s*([^\s,;]+)")


def load_package_specs(requirements_path: Path) -> list[str]:
    specs: list[str] = []
    for raw in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        specs.append(line)
    return specs


def package_name(spec: str) -> str:
    return _NAME_SPLIT_RE.split(spec, 1)[0].strip()


def pinned_version(spec: str) -> str | None:
    match = _PINNED_VERSION_RE.search(spec)
    return match.group(1) if match else None


def installed_version(name: str) -> str | None:
    try:
        return distribution(name).version
    except PackageNotFoundError:
        return None


def versions_equal(a: str, b: str) -> bool:
    if Version is not None:
        try:
            return Version(a) == Version(b)
        except InvalidVersion:
            pass
    return a == b


def compare_direction(current: str, target: str) -> str:
    """Return 'upgrade', 'downgrade', or 'change' for current -> target."""
    if Version is not None:
        try:
            cur, tgt = Version(current), Version(target)
            if tgt > cur:
                return "upgrade"
            if tgt < cur:
                return "downgrade"
        except InvalidVersion:
            pass
    return "change"


def pip_install(spec: str) -> int:
    result = subprocess.run([sys.executable, "-m", "pip", "install", spec], check=False)
    return result.returncode


def main() -> None:
    if not REQUIREMENTS_FILE.exists():
        raise SystemExit(f"requirements.txt not found at {REQUIREMENTS_FILE}")

    specs = load_package_specs(REQUIREMENTS_FILE)
    total = len(specs)
    installed_count = 0
    updated_count = 0
    unchanged_count = 0
    failed: list[str] = []

    print(f"Processing {total} package(s) from {REQUIREMENTS_FILE.name}\n")

    for idx, spec in enumerate(specs, start=1):
        name = package_name(spec)
        target = pinned_version(spec)
        current = installed_version(name)

        if current is None:
            print(f"[{idx}/{total}] {name}: not installed -> pip install {spec}")
            code = pip_install(spec)
            if code == 0:
                installed_count += 1
            else:
                print(f"  -> FAILED (exit code {code})")
                failed.append(spec)
            print()
            continue

        if target is None:
            print(f"[{idx}/{total}] {name}: installed (version {current}), no pinned version in spec, skipping.")
            unchanged_count += 1
            continue

        if versions_equal(current, target):
            print(f"[{idx}/{total}] {name}: already at version {current}, skipping.")
            unchanged_count += 1
            continue

        direction = compare_direction(current, target)
        print(f"[{idx}/{total}] {name}: {direction} {current} -> {target} -> pip install {spec}")
        code = pip_install(spec)
        if code == 0:
            updated_count += 1
        else:
            print(f"  -> FAILED (exit code {code})")
            failed.append(spec)
        print()

    print("=" * 60)
    print(
        f"Done. {installed_count} installed, "
        f"{updated_count} updated, "
        f"{unchanged_count} unchanged, "
        f"{len(failed)} failed."
    )
    if failed:
        print("Failed packages:")
        for spec in failed:
            print(f"  - {spec}")
        sys.exit(1)


if __name__ == "__main__":
    main()
