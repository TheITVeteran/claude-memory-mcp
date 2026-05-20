#!/usr/bin/env python3
"""Pre-commit hook: deny write access to specific paths on issue branches.

Implements the Topographical Forcing pattern from the AI Council trifecta
workflow (per Deepthink consult, 2026-05-20). When the current branch matches
an issue pattern (e.g. `issue-14/*`), reads the per-issue denylist from
`process/issues/<N>_HARNESS.toml` and blocks any staged change that touches a
denylisted path.

The point is to **physically prevent** the Builder from reaching for the
shortcut escape routes documented by the Architect for THIS specific PR,
rather than rely on negative-prompt instructions (which are
attention-injection antipatterns per Ironic Process Theory).

Example denylist for issue-14 (warning-suppression masking class):

    # process/issues/14_HARNESS.toml
    [issue-14]
    denied_paths = [
        "tests/unit/conftest.py",
        "tests/conftest.py",
        "pytest.ini",
    ]
    rationale = "Issue #14 requires source-level MagicMock -> AsyncMock fixes. \
        Modifying conftest.py risks adding warning-suppression fixtures \
        instead of fixing the underlying mocks. Modify the test files only."

If a denied path is staged, the hook exits non-zero with the rationale.

If the branch doesn't match an issue pattern, hook is a no-op.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ISSUE_BRANCH_PATTERN = re.compile(r"^issue-(\d+[a-z]?)(?:/|$)")


def get_current_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def load_harness_config(issue_id: str) -> dict[str, object] | None:
    config_path = Path("process/issues") / f"{issue_id}_HARNESS.toml"
    if not config_path.exists():
        return None
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return data.get(f"issue-{issue_id}")


def main() -> int:
    branch = get_current_branch()
    if not branch:
        return 0

    match = ISSUE_BRANCH_PATTERN.match(branch)
    if not match:
        # Not an issue branch — no constraints apply
        return 0

    issue_id = match.group(1)
    config = load_harness_config(issue_id)
    if not config:
        # Branch is an issue branch but no harness config exists for it
        # → no constraints (this is intentional; not all issues need a harness)
        return 0

    denied_paths = config.get("denied_paths", [])
    rationale = config.get("rationale", "(no rationale provided)")
    if not denied_paths:
        return 0

    staged = get_staged_files()
    violations = [f for f in staged if f in denied_paths]
    if not violations:
        return 0

    print(
        f"\nbranch-write-guard: BLOCKED — issue-{issue_id} denies modification "
        f"to the following paths:\n",
        file=sys.stderr,
    )
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    print(f"\nRationale (per process/issues/{issue_id}_HARNESS.toml):", file=sys.stderr)
    print(f"  {rationale}\n", file=sys.stderr)
    print(
        "If you genuinely need to modify a denied path, escalate to the "
        "Architect for a spec revision. Do NOT bypass this guard.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
