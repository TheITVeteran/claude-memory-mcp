"""Tests for scripts/hooks/inject_handoff_hash.py pre-commit hook.

Each test creates a real mini-git repo (via tmp_path + subprocess) to exercise
the hook script in an isolated environment.  Tests verify placeholder injection,
scoping, idempotency, and no-op behavior.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "hooks" / "inject_handoff_hash.py"
)

# ── Helpers ──────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory."""
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
        },
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create a git repo with one initial commit and return the repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "test@test"], repo)
    _git(["config", "user.name", "test"], repo)
    # Initial commit so HEAD exists
    dummy = repo / "dummy.txt"
    dummy.write_text("init", encoding="utf-8")
    _git(["add", "dummy.txt"], repo)
    _git(["commit", "-m", "initial"], repo)
    return repo


def _run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    """Run the hook script in the given repo."""
    return subprocess.run(  # noqa: S603
        ["python", str(HOOK_SCRIPT)],  # noqa: S607
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def _get_head_hash(repo: Path) -> str:
    """Return the full HEAD hash."""
    return _git(["rev-parse", "HEAD"], repo).stdout.strip()


# ── Evil Tests ───────────────────────────────────────────────────────


def test_evil_placeholder_replaced_in_handoff(tmp_path: Path) -> None:
    """Mini-repo with one commit; stage a handoff with <auto> placeholder; run hook.

    Pre-PR: TEST FAILS — script module doesn't exist (FileNotFoundError/returncode != 0).
    Post-PR: TEST PASSES — placeholder replaced with the commit hash, file re-staged.
    """
    repo = _init_repo(tmp_path)
    head_hash = _get_head_hash(repo)

    # Create and stage a handoff with placeholder
    process_dir = repo / "process"
    process_dir.mkdir()
    handoff = process_dir / "PR_99_HANDOFF.md"
    handoff.write_text(
        textwrap.dedent("""\
        # PR-99 Handoff

        **Commit:** <auto>
        **Branch:** test-branch
        """),
        encoding="utf-8",
    )
    _git(["add", "process/PR_99_HANDOFF.md"], repo)

    # Run hook
    result = _run_hook(repo)
    assert result.returncode == 0, f"Hook failed: {result.stderr}"

    # Verify placeholder was replaced
    content = handoff.read_text(encoding="utf-8")
    assert f"**Commit:** `{head_hash}`" in content, (
        f"Expected HEAD hash {head_hash} in handoff, got:\n{content}"
    )
    assert "<auto>" not in content, "Placeholder <auto> should have been replaced"

    # Verify hook printed injection message
    assert "inject-handoff-hash:" in result.stdout


def test_evil_multiple_handoffs_processed_in_one_commit(tmp_path: Path) -> None:
    """Stage two handoff files with <auto> placeholder; run hook once.

    Pre-PR: TEST FAILS — script module doesn't exist.
    Post-PR: TEST PASSES — both files get the hash injected; both re-staged.
    """
    repo = _init_repo(tmp_path)
    head_hash = _get_head_hash(repo)

    process_dir = repo / "process"
    process_dir.mkdir()

    handoff1 = process_dir / "PR_99_HANDOFF.md"
    handoff1.write_text("**Commit:** <auto>\n", encoding="utf-8")
    handoff2 = process_dir / "HOUSEKEEPING_HANDOFF.md"
    handoff2.write_text("**Commit:** <auto>\n", encoding="utf-8")

    _git(["add", "process/PR_99_HANDOFF.md", "process/HOUSEKEEPING_HANDOFF.md"], repo)

    result = _run_hook(repo)
    assert result.returncode == 0, f"Hook failed: {result.stderr}"

    for handoff in [handoff1, handoff2]:
        content = handoff.read_text(encoding="utf-8")
        assert f"**Commit:** `{head_hash}`" in content, (
            f"Expected HEAD hash in {handoff.name}, got:\n{content}"
        )
        assert "<auto>" not in content


def test_evil_non_handoff_markdown_untouched(tmp_path: Path) -> None:
    """Stage a regular docs/notes.md with <auto> text + a real handoff; run hook.

    Pre-PR: TEST FAILS — script module doesn't exist.
    Post-PR: TEST PASSES — notes.md is unchanged; only the handoff doc is processed.
    """
    repo = _init_repo(tmp_path)
    head_hash = _get_head_hash(repo)

    # Create non-handoff markdown with placeholder text
    docs_dir = repo / "docs"
    docs_dir.mkdir()
    notes = docs_dir / "notes.md"
    notes_content = "**Commit:** <auto>\nSome notes here.\n"
    notes.write_text(notes_content, encoding="utf-8")

    # Create real handoff
    process_dir = repo / "process"
    process_dir.mkdir()
    handoff = process_dir / "PR_99_HANDOFF.md"
    handoff.write_text("**Commit:** <auto>\n", encoding="utf-8")

    _git(["add", "docs/notes.md", "process/PR_99_HANDOFF.md"], repo)

    result = _run_hook(repo)
    assert result.returncode == 0

    # notes.md should be UNTOUCHED
    assert notes.read_text(encoding="utf-8") == notes_content, (
        "Non-handoff markdown should not be modified"
    )

    # handoff should be injected
    handoff_content = handoff.read_text(encoding="utf-8")
    assert f"**Commit:** `{head_hash}`" in handoff_content


# ── Sad Tests ────────────────────────────────────────────────────────


def test_sad_handoff_without_placeholder_is_noop(tmp_path: Path) -> None:
    """Stage a handoff that already has a real hash (no placeholder); run hook.

    Pre-PR: TEST PASSES — script doesn't exist, no error path to fail.
    Post-PR: TEST PASSES — hook returns 0, file unchanged.
    """
    repo = _init_repo(tmp_path)

    process_dir = repo / "process"
    process_dir.mkdir()
    handoff = process_dir / "PR_99_HANDOFF.md"
    original_content = "**Commit:** `abc123def456`\nAlready has a hash.\n"
    handoff.write_text(original_content, encoding="utf-8")

    _git(["add", "process/PR_99_HANDOFF.md"], repo)

    result = _run_hook(repo)
    assert result.returncode == 0

    # File should be unchanged
    assert handoff.read_text(encoding="utf-8") == original_content


# ── Neutral Tests ────────────────────────────────────────────────────


def test_neutral_no_handoffs_staged(tmp_path: Path) -> None:
    """Stage a regular .py file with no markdown changes; run hook.

    Pre-PR: TEST PASSES — script doesn't exist, trivially passes via vacuous truth.
    Post-PR: TEST PASSES — hook returns 0 immediately, no file system operations.
    """
    repo = _init_repo(tmp_path)

    pyfile = repo / "example.py"
    pyfile.write_text("print('hello')\n", encoding="utf-8")
    _git(["add", "example.py"], repo)

    result = _run_hook(repo)
    assert result.returncode == 0

    # No injection message
    assert "inject-handoff-hash:" not in result.stdout
