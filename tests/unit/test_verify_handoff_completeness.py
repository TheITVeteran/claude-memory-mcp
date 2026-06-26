"""Acceptance tests for verify_handoff_completeness pre-commit hook.

Per process/issues/22f_BUILD_SPEC.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

HOOK_SCRIPT = Path("scripts/hooks/verify_handoff_completeness.py")


def _run_hook(handoff_path: Path) -> tuple[int, str]:
    """Run the hook against the given handoff path; return (exit_code, stderr)."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(HOOK_SCRIPT), str(handoff_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stderr


def _write_handoff(tmp_path: Path, content: str) -> Path:
    """Write a handoff file with the given content; return its path."""
    handoff = tmp_path / "PR_ISSUE_TEST_HANDOFF.md"
    handoff.write_text(content, encoding="utf-8")
    return handoff


# ─── Happy path ──────────────────────────────────────────────────────


def test_happy_complete_handoff_passes(tmp_path: Path) -> None:
    """A complete handoff with all 4 seeds, canonical ruff, no N/A passes."""
    content = dedent("""
        # Test Handoff

        ## Pre-PR baseline
        seed=1 ...
        seed=2 ...
        seed=3 ...
        seed=4 ...

        ## Checklist
        - tox -e contracts: SUCCESS, 13/13
        - ruff check src/claude_memory tests scripts: All checks passed!
        - bandit: only B104
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, _ = _run_hook(handoff)
    assert code == 0


# ─── Evil paths ──────────────────────────────────────────────────────


def test_evil_single_seed_fails(tmp_path: Path) -> None:
    """Pre-PR baseline showing only seed=1 fails."""
    content = dedent("""
        ## Pre-PR baseline
        seed=1 ...

        ## Checklist
        - tox -e contracts: SUCCESS
        - ruff check src/claude_memory tests scripts: All checks passed!
        - bandit: only B104
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, stderr = _run_hook(handoff)
    assert code == 1
    assert "seed=2" in stderr or "seed=3" in stderr or "seed=4" in stderr


def test_evil_exclude_flag_on_ruff_fails(tmp_path: Path) -> None:
    """A ruff command with --exclude fails."""
    content = dedent("""
        seed=1 seed=2 seed=3 seed=4

        ## Checklist
        - tox -e contracts: SUCCESS
        - ruff check src/claude_memory tests scripts --exclude=tests/lint/_*.py: passed
        - bandit: only B104
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, stderr = _run_hook(handoff)
    assert code == 1
    assert "--exclude" in stderr


def test_evil_na_shortcut_on_bandit_fails(tmp_path: Path) -> None:
    """N/A in a bandit section fails."""
    content = dedent("""
        seed=1 seed=2 seed=3 seed=4

        ## Checklist
        - tox -e contracts: SUCCESS
        - ruff check src/claude_memory tests scripts: All checks passed!
        - bandit: N/A — no security checks needed
        - mypy: clean
    """)
    handoff = _write_handoff(tmp_path, content)
    code, stderr = _run_hook(handoff)
    assert code == 1
    assert "N/A" in stderr


# ─── Sad / neutral paths ─────────────────────────────────────────────


def test_sad_non_handoff_file_skipped(tmp_path: Path) -> None:
    """Non-handoff files passed as args are ignored — hook exits 0."""
    other = tmp_path / "some_other.md"
    other.write_text("any content", encoding="utf-8")
    code, _ = _run_hook(other)
    assert code == 0


def test_neutral_no_handoffs_in_commit(tmp_path: Path) -> None:
    """No handoff args at all — hook exits 0."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
