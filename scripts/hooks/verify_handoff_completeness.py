#!/usr/bin/env python3
"""Pre-commit hook: verify_handoff_completeness.

Validates that any process/PR_ISSUE_*_HANDOFF.md file being committed contains:
  1. All 4 seed markers (seed=1, seed=2, seed=3, seed=4) at least once each
     — protects against the single-seed pre-PR baseline drift pattern (22c/22d/22e R1)
  2. The canonical ruff command (no `--exclude` substring)
     — protects against the dirty-worktree ruff hygiene gap (22a/22b R1)
  3. No `N/A` text in checklist items for deterministic gates (contracts/ruff/bandit/mypy)
     — protects against `N/A` shortcuts on required evidence

Exits 1 with a clear error message if any handoff fails validation.
Exits 0 if no handoff files in commit OR all handoffs pass.

Per process/issues/22f_BUILD_SPEC.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SEED_MARKERS = ("seed=1", "seed=2", "seed=3", "seed=4")
FORBIDDEN_RUFF_FLAG = "--exclude"
DETERMINISTIC_GATE_NAMES = ("contracts", "ruff", "bandit", "mypy")
NA_PATTERN = re.compile(r"\bN/A\b", re.IGNORECASE)


def validate_handoff(path: Path) -> list[str]:
    """Validate a single handoff file. Returns list of failure messages (empty if PASS)."""
    failures: list[str] = []
    content = path.read_text(encoding="utf-8")

    # Check 1: all 4 seed markers present
    for marker in REQUIRED_SEED_MARKERS:
        if marker not in content:
            failures.append(
                f"{path}: missing required seed marker '{marker}' — "
                f"multi-seed baseline must show all 4 seed outputs (see 22d/22e R1 lessons)"
            )

    # Check 2: ruff command is canonical (no --exclude substring on a ruff line)
    for lineno, line in enumerate(content.splitlines(), start=1):
        if "ruff check" in line and FORBIDDEN_RUFF_FLAG in line:
            failures.append(
                f"{path}:{lineno}: ruff command uses '{FORBIDDEN_RUFF_FLAG}' flag — "
                f"canonical command is `python -m ruff check src/claude_memory tests scripts` "
                f"with no flags (see 22a/22b R1 lessons)"
            )

    # Check 3: no N/A on deterministic-gate sections
    # Heuristic: find sections referencing each gate name and check for N/A within
    # a small window (next 8 lines after the gate-name mention).
    lines = content.splitlines()
    for lineno, line in enumerate(lines):
        for gate in DETERMINISTIC_GATE_NAMES:
            if gate in line.lower():
                window = "\n".join(lines[lineno : lineno + 8])
                if NA_PATTERN.search(window):
                    failures.append(
                        f"{path}:{lineno + 1}: N/A shortcut on deterministic gate '{gate}' "
                        f"section — gates must have real evidence pasted, not N/A"
                    )
                    break  # one report per (line, gate) is enough

    return failures


def main(argv: list[str]) -> int:
    handoff_files = [Path(p) for p in argv if "PR_ISSUE_" in p and p.endswith("_HANDOFF.md")]
    if not handoff_files:
        return 0  # No handoffs in this commit — nothing to validate

    all_failures: list[str] = []
    for path in handoff_files:
        if not path.exists():
            continue  # File deleted in this commit — skip
        all_failures.extend(validate_handoff(path))

    if all_failures:
        print("=" * 70, file=sys.stderr)
        print("HANDOFF COMPLETENESS CHECK FAILED:", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for msg in all_failures:
            print(f"  • {msg}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(
            "Fix the handoff document(s) and re-commit. The 22a-22e-bis arc had 7 PRs "
            "fail checklist hygiene; this hook prevents an 8th.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
