#!/usr/bin/env python3
"""Pre-commit hook: architect_branch_guard.

Refuses commits that include architect-owned files on non-master branches.

Architect-owned files are constitution-grade documents and infrastructure that
should only be modified directly on master. When committed to a builder branch
(e.g. ``b10-5/...``, ``issue-22a/...``), they get coupled to the builder's
work and the architect loses the ability to ship the change cleanly to master.

This hook prevents a recurring trap: the architect (Claude) intends to commit
spec patches / infrastructure fixes to master, but accidentally has a builder
branch checked out (e.g. because they previously verified something on that
branch and forgot to switch back). The commit lands on the wrong branch and
needs a cherry-pick + branch-reset cleanup.

Verbal discipline failed 5 times in the B10.5 arc. Physical enforcement is
the structural fix — mirrors the lesson from `verify_handoff_completeness.py`
(when verbal discipline fails 3+ times, switch to physical enforcement).

Per the architect-on-AG-branch trap; structurally closes the gap.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Architect-owned file patterns. Modifying any of these on a non-master branch
# triggers the guard.
ARCHITECT_OWNED_PATTERNS = (
    re.compile(r"^process/issues/.*_BUILD_SPEC\.md$"),
    re.compile(r"^process/issues/.*_AUDIT_SPEC\.md$"),
    re.compile(r"^process/issues/.*_HARNESS\.toml$"),
    re.compile(r"^process/REMEDIATION_.*\.md$"),
    re.compile(r"^process/SCORCHED_EARTH_.*\.md$"),
    re.compile(r"^process/ARC_.*\.md$"),
    re.compile(r"^\.pre-commit-config\.yaml$"),
    re.compile(r"^scripts/hooks/(?!__).*\.py$"),  # hooks themselves
    re.compile(r"^scripts/trace_contracts_dragon\.py$"),  # the contract scanner
    re.compile(r"^CLAUDE\.md$"),
    re.compile(r"^ARCHITECTURE\.md$"),
)


def is_architect_file(path: str) -> bool:
    """Return True if the given path matches any architect-owned pattern."""
    normalized = path.replace("\\", "/")
    return any(pattern.match(normalized) for pattern in ARCHITECT_OWNED_PATTERNS)


def current_branch() -> str:
    """Return the current git branch name (or empty string on detached HEAD)."""
    try:
        # `git` resolved from PATH is intentional — hook must work cross-platform
        # without hardcoding a binary location.
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def main(argv: list[str]) -> int:
    branch = current_branch()
    if branch in ("master", "main", "HEAD"):
        return 0  # On master (or detached) — allow architect work freely

    architect_files = [path for path in argv if is_architect_file(path)]
    if not architect_files:
        return 0  # No architect files in this commit — allow

    print("=" * 70, file=sys.stderr)
    print("ARCHITECT BRANCH GUARD: refusing commit on non-master branch", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Current branch: {branch}", file=sys.stderr)
    print("  Architect-owned files in commit:", file=sys.stderr)
    for path in architect_files:
        print(f"    • {path}", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(
        "Architect-owned files (specs, hooks, scanner, CLAUDE.md, ARCHITECTURE.md,\n"
        "process docs) should only be modified directly on master so they ship\n"
        "cleanly without coupling to builder branch work.\n"
        "\n"
        "Fix: `git checkout master` then re-stage these files and commit.\n"
        "If you genuinely intended to modify these on this branch (rare —\n"
        "almost always a mistake), bypass with `--no-verify` and document why.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
