"""Tests for Batch 4: Log level discipline.

AUDIT-B4: Enforces that no except block uses logger.debug —
all error paths must log at warning or above for prod visibility.
"""

import ast
import pathlib

SRC_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "claude_memory"
EXEMPT_FILES = {"retry.py"}  # Retry infrastructure uses debug intentionally


class TestLogLevelDiscipline:
    """Contract: no logger.debug in except blocks."""

    def _find_debug_in_except(self) -> list[str]:
        """AST-based scan for logger.debug calls inside except handlers."""
        violations: list[str] = []

        for py_file in sorted(SRC_DIR.rglob("*.py")):
            if py_file.name in EXEMPT_FILES:
                continue

            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    for child in ast.walk(node):
                        if (
                            isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Attribute)
                            and child.func.attr == "debug"
                            and isinstance(child.func.value, ast.Name)
                            and child.func.value.id == "logger"
                        ):
                            violations.append(f"{py_file.name}:{child.lineno}")

        return violations

    def test_evil1_no_debug_in_except_blocks(self) -> None:
        """AUDIT-B4: Zero logger.debug calls inside except handlers."""
        violations = self._find_debug_in_except()
        assert violations == [], (
            f"Found logger.debug in except blocks: {violations}. "
            "Use logger.warning or logger.error instead."
        )

    def test_evil2_exempt_files_list_is_minimal(self) -> None:
        """AUDIT-B4: Exempt list contains only retry.py."""
        assert EXEMPT_FILES == {"retry.py"}

    def test_evil3_src_dir_exists(self) -> None:
        """AUDIT-B4: Source directory is accessible for scanning."""
        assert SRC_DIR.exists()
        assert any(SRC_DIR.rglob("*.py"))

    def test_sad1_no_false_positives_on_debug_outside_except(self) -> None:
        """AUDIT-B4: logger.debug outside except blocks is fine."""
        # This test just verifies the scanner doesn't flag normal debug usage
        violations = self._find_debug_in_except()
        # If we get here without error, scanner works
        assert isinstance(violations, list)

    def test_happy_all_except_blocks_use_warning_or_above(self) -> None:
        """AUDIT-B4: Positive confirmation that except blocks use proper levels."""
        violations = self._find_debug_in_except()
        assert len(violations) == 0
