#!/usr/bin/env python3
"""Pre-commit hook: inject parent commit hash into PR handoff docs.

When a ``process/PR_*_HANDOFF.md`` or ``process/HOUSEKEEPING_HANDOFF.md`` is staged
with a ``**Commit:** <auto>`` placeholder, replace the placeholder with the
current HEAD hash (the implementation commit being audited) and re-stage the
modified file.

Convention: the handoff doc records the COMMIT BEING AUDITED, which is the
HEAD commit at the moment the handoff is being committed. The handoff's own
commit (which adds the handoff file) is metadata about that prior commit.

If the handoff doesn't contain the placeholder, the hook is a no-op for that
file. Non-handoff markdown files are never touched.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PLACEHOLDER = "**Commit:** <auto>"
HANDOFF_PATTERN = re.compile(r"^process/(PR_.+|HOUSEKEEPING)_HANDOFF\.md$")


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def get_head_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        # No HEAD yet (initial commit) — leave placeholder unchanged
        return None


def inject_into_file(path: Path, head_hash: str) -> bool:
    """Return True if file was modified."""
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if PLACEHOLDER not in content:
        return False
    new_content = content.replace(PLACEHOLDER, f"**Commit:** `{head_hash}`")
    path.write_text(new_content, encoding="utf-8")
    subprocess.run(["git", "add", str(path)], check=True)  # noqa: S607
    return True


def main() -> int:
    staged = get_staged_files()
    handoffs = [f for f in staged if HANDOFF_PATTERN.match(f)]
    if not handoffs:
        return 0

    head_hash = get_head_hash()
    if head_hash is None:
        return 0

    modified_files: list[str] = []
    for handoff in handoffs:
        if inject_into_file(Path(handoff), head_hash):
            modified_files.append(handoff)

    if modified_files:
        print(
            f"inject-handoff-hash: injected HEAD ({head_hash[:7]}) into: "
            f"{', '.join(modified_files)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
