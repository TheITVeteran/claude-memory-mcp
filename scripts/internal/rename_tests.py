"""Automated test renaming script.

Classifies test functions as evil/sad/happy based on their content patterns,
then renames them in-place. Run with --dry-run first to preview changes.

Classification heuristics:
  EVIL  = pytest.raises, side_effect=.*Error, "raises", "fails", "error", "corrupt"
  SAD   = "not_found", "empty", "no_results", "missing", "none", "invalid"
  HAPPY = everything else (normal operation)
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

# Patterns that indicate evil tests (error conditions)
EVIL_PATTERNS = [
    r"pytest\.raises",
    r"side_effect\s*=\s*\w*Error",
    r"side_effect\s*=\s*\w*Exception",
    r"side_effect\s*=\s*ConnectionError",
    r"side_effect\s*=\s*RuntimeError",
    r"side_effect\s*=\s*ValueError",
    r"side_effect\s*=\s*TypeError",
    r"side_effect\s*=\s*KeyError",
    r"side_effect\s*=\s*OSError",
    r"assert.*error.*in.*result",
    r'assert.*\{.*"error"',
    r'"error".*in.*result',
]

# Function name patterns that indicate evil
EVIL_NAME_PATTERNS = [
    r"_raises",
    r"_fails",
    r"_error",
    r"_corrupt",
    r"_invalid",
    r"_malformed",
    r"_broken",
    r"_crash",
    r"_timeout",
    r"_overflow",
    r"_injection",
    r"_refused",
    r"_denied",
]

# Function name patterns that indicate sad (edge cases)
SAD_NAME_PATTERNS = [
    r"_not_found",
    r"_empty",
    r"_no_results",
    r"_no_path",
    r"_missing",
    r"_none\b",
    r"_no_nodes",
    r"_no_edges",
    r"_no_data",
    r"_stale",
    r"_orphan",
    r"_fallback",
    r"_no_project",
    r"_skip",
    r"_default",
    r"_unsupported",
    r"_unknown",
    r"_no_vector",
    r"_backward_compat",
]

# Patterns in body that indicate sad
SAD_BODY_PATTERNS = [
    r"assert.*==\s*\[\]",
    r"assert.*==\s*\{\}",
    r"assert.*is\s+None",
    r"return_value\s*=\s*None",
    r"return_value\s*=\s*\[\]",
    r"return_value\s*=\s*\{\}",
]


def extract_functions(content: str) -> list[dict]:
    """Extract test function name, line number, and body."""
    lines = content.split("\n")
    functions = []
    i = 0
    while i < len(lines):
        match = re.match(r"^(\s*)(async )?def (test_\w+)\(", lines[i])
        if match:
            func_name = match.group(3)
            start_line = i
            # Collect function body until next function or class or end
            body_lines = [lines[i]]
            i += 1
            while i < len(lines):
                if re.match(r"^\s*(async )?def test_", lines[i]) or re.match(
                    r"^\s*class ", lines[i]
                ):
                    break
                body_lines.append(lines[i])
                i += 1
            body = "\n".join(body_lines)
            functions.append(
                {
                    "name": func_name,
                    "start_line": start_line + 1,  # 1-indexed
                    "body": body,
                }
            )
        else:
            i += 1
    return functions


def classify(func: dict) -> str:
    """Classify a test function as evil, sad, or happy."""
    name = func["name"]
    body = func["body"]

    # Already classified? Skip.
    if re.match(r"test_(evil|sad|happy)", name):
        return "skip"

    # Check evil patterns in body
    for pattern in EVIL_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            return "evil"

    # Check evil patterns in name
    for pattern in EVIL_NAME_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return "evil"

    # Check sad patterns in name
    for pattern in SAD_NAME_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return "sad"

    # Check sad patterns in body
    for pattern in SAD_BODY_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            return "sad"

    return "happy"


def generate_new_name(func: dict, category: str, counters: dict) -> str:
    """Generate a new name following the convention."""
    old_name = func["name"]
    # Strip the test_ prefix
    suffix = old_name[5:]  # Remove 'test_'

    if category == "evil":
        counters["evil"] += 1
        return f"test_evil{counters['evil']}_{suffix}"
    elif category == "sad":
        counters["sad"] += 1
        return f"test_sad{counters['sad']}_{suffix}"
    else:  # happy
        return f"test_happy_{suffix}"


def process_file(filepath: Path, dry_run: bool = True) -> list[tuple[str, str]]:
    """Process a single test file and return rename pairs."""
    content = filepath.read_text(encoding="utf-8")
    functions = extract_functions(content)

    counters = {"evil": 0, "sad": 0}
    renames = []

    for func in functions:
        category = classify(func)
        if category == "skip":
            continue
        new_name = generate_new_name(func, category, counters)
        renames.append((func["name"], new_name, category, func["start_line"]))

    if not dry_run and renames:
        for old_name, new_name, _, _ in renames:
            # Only replace exact function definition and calls within the file
            content = re.sub(rf"\bdef {old_name}\b", f"def {new_name}", content)
        filepath.write_text(content, encoding="utf-8")

    return renames


def main():
    dry_run = "--dry-run" in sys.argv
    apply = "--apply" in sys.argv

    if not dry_run and not apply:
        print("Usage: python rename_tests.py --dry-run  (preview)")
        print("       python rename_tests.py --apply    (apply renames)")
        sys.exit(1)

    tests_dir = Path("tests")
    total_renames = 0
    file_stats = defaultdict(lambda: {"evil": 0, "sad": 0, "happy": 0})

    # Skip gauntlet tests — they have their own naming
    for test_file in sorted(tests_dir.rglob("test_*.py")):
        if "gauntlet" in str(test_file):
            continue

        renames = process_file(test_file, dry_run=dry_run)
        if renames:
            rel_path = test_file.relative_to(tests_dir)
            print(f"\n{'=' * 60}")
            print(f"  {rel_path}: {len(renames)} renames")
            print(f"{'=' * 60}")
            for old_name, new_name, category, line in renames:
                marker = {"evil": "[EVIL]", "sad": "[SAD]", "happy": "[HAPPY]"}[category]
                print(f"  L{line:4d}  {marker} {old_name}")
                print(f"         → {new_name}")
                file_stats[str(rel_path)][category] += 1
            total_renames += len(renames)

    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {total_renames} renames")
    if dry_run:
        print("  Mode: DRY RUN (no changes made)")
        print("  Run with --apply to execute renames")
    else:
        print("  Mode: APPLIED ✅")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
