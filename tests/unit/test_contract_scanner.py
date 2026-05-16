"""Tests for the contract scanner (scripts/trace_contracts_dragon.py).

Uses synthetic-AST fixtures (temp .py files) to verify Pattern 10's
await-detection logic, plus a baseline integration test against the
real src/claude_memory directory.
"""

import importlib.util
import tempfile
import textwrap
from pathlib import Path
from typing import Any

# ── Test Constants ──────────────────────────────────────────────────
SCANNER_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "trace_contracts_dragon.py"
)
REAL_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "claude_memory"
ABSOLUTE_BASELINE = 13

# ── Import scanner ──────────────────────────────────────────────────

# We import analyze_file directly rather than subprocess the script.

_spec = importlib.util.spec_from_file_location("trace_contracts_dragon", str(SCANNER_SCRIPT))
assert _spec is not None and _spec.loader is not None
_scanner_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scanner_mod)
analyze_file: Any = _scanner_mod.analyze_file  # type: ignore[attr-defined]


def _write_temp_py(content: str) -> Path:
    """Write content to a temp .py file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# ── Evil Tests ──────────────────────────────────────────────────────


def test_evil1_awaited_self_repo_call_not_flagged() -> None:
    """Synthetic async function with `await self.repo.get_node(x)`.

    Pre-PR: TEST FAILS — scanner incorrectly flags this as Sync IO in Async.
    Post-PR: TEST PASSES — scanner correctly skips awaited calls.
    """
    source = """\
    class MyService:
        async def do_work(self):
            result = await self.repo.get_node("test-id")
            return result
    """
    path = _write_temp_py(source)
    try:
        violations = analyze_file(str(path))
        sync_io_violations = [v for v in violations if v[4] == "Sync IO in Async"]
        assert len(sync_io_violations) == 0, (
            f"Expected 0 Sync IO violations for awaited call, got {len(sync_io_violations)}: "
            f"{sync_io_violations}"
        )
    finally:
        path.unlink()


def test_evil2_unawaited_self_repo_call_is_flagged() -> None:
    """Synthetic async function with bare `self.repo.get_node(x)` (no await).

    Pre-PR: TEST PASSES — scanner correctly flags this.
    Post-PR: TEST PASSES — must remain flagged (regression-prevention).
    """
    source = """\
    class MyService:
        async def do_work(self):
            result = self.repo.get_node("test-id")
            return result
    """
    path = _write_temp_py(source)
    try:
        violations = analyze_file(str(path))
        sync_io_violations = [v for v in violations if v[4] == "Sync IO in Async"]
        assert len(sync_io_violations) == 1, (
            f"Expected 1 Sync IO violation for unawaited call, got {len(sync_io_violations)}: "
            f"{sync_io_violations}"
        )
    finally:
        path.unlink()


def test_evil3_sync_io_outside_async_def_not_flagged() -> None:
    """Synthetic regular `def` (not async) calling `self.repo.get_node(x)`.

    Pre-PR: TEST PASSES — scanner only fires inside async def.
    Post-PR: TEST PASSES — must remain not-flagged (regression-prevention).
    """
    source = """\
    class MyService:
        def do_work(self):
            result = self.repo.get_node("test-id")
            return result
    """
    path = _write_temp_py(source)
    try:
        violations = analyze_file(str(path))
        sync_io_violations = [v for v in violations if v[4] == "Sync IO in Async"]
        assert len(sync_io_violations) == 0, (
            f"Expected 0 Sync IO violations for sync def, got {len(sync_io_violations)}: "
            f"{sync_io_violations}"
        )
    finally:
        path.unlink()


# ── Sad Tests ───────────────────────────────────────────────────────


def test_sad1_malformed_python_file_handled() -> None:
    """Synthetic file with syntax error fed to scanner.

    Pre-PR: May crash or handle gracefully — verify.
    Post-PR: Must not crash; returns empty list.
    """
    source = """\
    def broken(
        # Missing closing paren and colon
        x
    """
    path = _write_temp_py(source)
    try:
        # Should NOT raise an exception
        violations = analyze_file(str(path))
        assert isinstance(violations, list), f"Expected list, got {type(violations)}"
        assert len(violations) == 0, (
            f"Expected 0 violations for malformed file, got {len(violations)}"
        )
    finally:
        path.unlink()


# ── Neutral Tests ───────────────────────────────────────────────────


def test_neutral_baseline_against_real_repo() -> None:
    """Run scanner against current `src/claude_memory` directory.

    Pre-PR: TEST FAILS — returns 75 violations (62 false positives).
    Post-PR: TEST PASSES — returns exactly 13 violations matching absolute baseline.
    """
    total_violations = 0
    for py_file in sorted(REAL_SRC_DIR.rglob("*.py")):
        violations = analyze_file(str(py_file))
        total_violations += len(violations)

    assert total_violations == ABSOLUTE_BASELINE, (
        f"Expected exactly {ABSOLUTE_BASELINE} violations against real repo, got {total_violations}"
    )
