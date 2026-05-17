# Issue #15 — Pre-commit Hook for Handoff Hash Injection (Build Spec)

**Issue:** [iikarus/Dragon-Brain#15](https://github.com/iikarus/Dragon-Brain/issues/15)
**Architect:** Claude
**Builder:** Antigravity (this is your spec)
**Auditor:** Codex (under separate `15_AUDIT_SPEC.md`)
**Director:** Tabish

Audit guidelines for Codex live in `process/issues/15_AUDIT_SPEC.md` — you don't need to read that one. Per-PR audit criteria are reproduced below as "The Bar" so you know what your work will be measured against.

---

## Problem

Every PR in the v1.2.1 Round 2 remediation arc (May 13-17, 2026) flagged handoff doc commit-hash drift as a Discovery. 6+ recurrences across all 6 remediation PRs plus housekeeping + docs PRs.

**The chicken-and-egg root cause:**

1. AG writes `process/PR_N_HANDOFF.md` with `git rev-parse HEAD` value embedded as the "Commit" field
2. AG commits — including the handoff doc — which produces a NEW HEAD hash
3. The handoff doc now records the PRIOR commit, not its own commit
4. AG amends to fix → another new hash → still drifts

There is no manual exit from this loop. AG cannot know the commit hash before the commit because the commit content (including the handoff doc) determines the hash.

## Solution: shift the convention + automate

**Convention shift (this is the key insight):** the handoff doc records the **commit being audited** — i.e., the implementation commit — NOT the handoff's own commit. The handoff itself is metadata ABOUT that prior commit.

So when the handoff is being committed, `git rev-parse HEAD` returns the implementation commit (the thing being audited). That's the hash the handoff should record.

**Automation:** a pre-commit hook detects a `**Commit:** <auto>` placeholder in any staged `process/PR_*_HANDOFF.md` or `process/HOUSEKEEPING_HANDOFF.md` file, replaces the placeholder with the current HEAD hash (= the implementation commit), and re-stages the modified handoff. The final commit contains the handoff with the correct hash embedded.

## Concrete fix (no inference allowed)

### Step 1 — Create the hook script

**File:** `scripts/hooks/inject_handoff_hash.py` (new)

```python
#!/usr/bin/env python3
"""Pre-commit hook: inject parent commit hash into PR handoff docs.

When a `process/PR_*_HANDOFF.md` or `process/HOUSEKEEPING_HANDOFF.md` is staged
with a `**Commit:** <auto>` placeholder, replace the placeholder with the
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
HANDOFF_PATTERN = re.compile(
    r"^process/(PR_.+|HOUSEKEEPING)_HANDOFF\.md$"
)


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True,
    )
    return [
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def get_head_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
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
    subprocess.run(["git", "add", str(path)], check=True)
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
```

### Step 2 — Register the hook in `.pre-commit-config.yaml`

Add this hook entry to the existing `.pre-commit-config.yaml` (append to the `repos:` list or to an existing `local` repo section if one exists):

```yaml
  - repo: local
    hooks:
      - id: inject-handoff-hash
        name: Inject HEAD hash into PR handoff docs
        entry: python scripts/hooks/inject_handoff_hash.py
        language: system
        pass_filenames: false
        always_run: true
        stages: [commit]
```

Notes:
- `pass_filenames: false` — the hook discovers its own targets via `git diff --cached`, doesn't rely on pre-commit's file list
- `always_run: true` — must fire on every commit (otherwise pre-commit may skip when no `.md` files are staged but a handoff IS staged via different filter)
- `language: system` — uses the system Python; the script is stdlib-only, no extra deps

### Step 3 — Update `process/REMEDIATION_BUILD_SPEC.md` pre-handoff checklist item 1

Find the pre-handoff checklist (in the handoff hygiene section) and update item 1. Current text says something like "Run `git rev-parse HEAD` — record the hash. Use this exact hash in the handoff." Update to:

```markdown
1. **Commit hash:** Write `**Commit:** <auto>` in the handoff doc's commit-hash field. The pre-commit hook at `scripts/hooks/inject_handoff_hash.py` will replace the placeholder with the actual HEAD hash (= the implementation commit being audited) at commit time. The handoff records the commit BEING AUDITED, not the handoff's own commit — this is the documented convention that resolves the chicken-and-egg hash-drift problem. **Do NOT manually edit the injected hash after commit.** If you amend the implementation commit, regenerate the handoff with `<auto>` and re-commit; the hook will re-inject.
```

### Step 4 — Add docstring to `process/README.md`

Find the "Files" section in `process/README.md` and add a brief note about the placeholder convention:

```markdown
### Handoff doc convention

Handoff docs (`PR_N_HANDOFF.md`, `HOUSEKEEPING_HANDOFF.md`) record the COMMIT BEING AUDITED, not the handoff's own commit. When authoring a handoff:

1. Write `**Commit:** <auto>` in the commit-hash field
2. Commit the handoff with the work it documents
3. The `inject-handoff-hash` pre-commit hook replaces the placeholder with the actual HEAD hash

This is the documented resolution to the chicken-and-egg hash-drift problem that plagued the v1.2.1 Round 2 remediation arc (6+ recurrences). See [issue #15](https://github.com/iikarus/Dragon-Brain/issues/15) for the design discussion.
```

## Files affected

- **New:** `scripts/hooks/inject_handoff_hash.py` (~70 LoC including docstring)
- **New:** `tests/unit/test_inject_handoff_hash.py` (~120 LoC for the 5 tests)
- **Modified:** `.pre-commit-config.yaml` (+8 lines)
- **Modified:** `process/REMEDIATION_BUILD_SPEC.md` (~5-line update to checklist item 1)
- **Modified:** `process/README.md` (~10-line section addition)

**LoC:** ~213 total (~70 production + ~120 test + ~23 doc/config).

## Tests (3 evil + 1 sad + 1 neutral, test-first)

Create `tests/unit/test_inject_handoff_hash.py` (new file). Use `pytest`'s `tmp_path` fixture + `subprocess` to set up real mini-git repos for each test.

| Test | Category | Scenario | Pre-PR | Post-PR |
|------|----------|----------|--------|---------|
| test_evil_placeholder_replaced_in_handoff | evil | Mini-repo with one commit; stage a `process/PR_99_HANDOFF.md` containing `**Commit:** <auto>`; run hook | TEST FAILS (script module doesn't exist — ImportError) | TEST PASSES (placeholder replaced with the commit hash, file re-staged, hook prints injection message) |
| test_evil_multiple_handoffs_processed_in_one_commit | evil | Stage two handoff files (`PR_99_HANDOFF.md` + `HOUSEKEEPING_HANDOFF.md`), both with `<auto>` placeholder; run hook once | TEST FAILS | TEST PASSES (both files get the hash injected; both re-staged) |
| test_evil_non_handoff_markdown_untouched | evil | Stage a regular `docs/notes.md` containing `**Commit:** <auto>` text + a real `process/PR_99_HANDOFF.md` with the placeholder; run hook | TEST FAILS | TEST PASSES (notes.md is unchanged; only the handoff doc is processed) |
| test_sad_handoff_without_placeholder_is_noop | sad | Stage `process/PR_99_HANDOFF.md` that does NOT contain the placeholder string (already has a real hash); run hook | TEST PASSES (script doesn't exist, no error path to fail) | TEST PASSES (hook returns 0, file unchanged, no spurious modifications) |
| test_neutral_no_handoffs_staged | neutral | Stage a regular `.py` file with no markdown changes; run hook | TEST PASSES (script doesn't exist, trivially passes via vacuous truth) | TEST PASSES (hook returns 0 immediately, no file system operations) |

**Test-first evidence requirement:** for tests marked "TEST FAILS" pre-PR (3 of 5: the three evil tests), AG MUST capture verbatim failure output against pre-PR base by running the test file against the master branch without the new script. Paste in handoff under "Test-first evidence" section.

## The bar (Codex will verify)

- (a) `scripts/hooks/inject_handoff_hash.py` exists at the expected path with the docstring describing the convention
- (b) `.pre-commit-config.yaml` registers the `inject-handoff-hash` hook with `pass_filenames: false`, `always_run: true`, `stages: [commit]`
- (c) End-to-end test: synthetic mini-git scenario where staging a handoff doc with `<auto>` placeholder and committing produces a commit whose handoff file contains the parent HEAD hash (not the literal `<auto>` string, not an empty hash)
- (d) Hook is idempotent — running it twice on the same staged handoff produces the same hash (because the second run finds no placeholder; no-op)
- (e) Hook is scoped — running with a non-handoff `.md` file staged with `<auto>` text leaves that file unchanged
- (f) 5-row test table is implemented; the 3 TEST FAILS tests have verbatim pre-PR failure evidence captured in handoff
- (g) `process/REMEDIATION_BUILD_SPEC.md` pre-handoff checklist item 1 updated to document the placeholder convention
- (h) `process/README.md` "Handoff doc convention" section added
- (i) `tox -e contracts` post-PR shows delta = 0 (new script + new test add nothing to contract scanner since they're in `scripts/hooks/` and `tests/unit/`, outside `src/claude_memory/`)
- (j) `mypy --strict src/claude_memory` still passes (no changes to source layer)
- (k) Full unit suite (`tox -e py312` or `pytest tests/unit/ -q`) passes including the 5 new tests

## Branch + handoff conventions

Branch: `issue-15/inject-handoff-hash-hook`
Branched from: `master` HEAD (`e3c4b31` per v1.2.1 merge)
Handoff doc: `process/PR_ISSUE_15_HANDOFF.md` (note: deviation from `PR_N_HANDOFF.md` naming — these are issue-driven PRs now, not arc-numbered)

**Handoff template — use this format:**

```markdown
# Issue #15 Handoff — Pre-commit Hook for Handoff Hash Injection

**Commit:** <auto>
**Branch:** issue-15/inject-handoff-hash-hook
**Issue:** https://github.com/iikarus/Dragon-Brain/issues/15

## Diff inventory
[git diff --name-only master..HEAD output]

## Pre-handoff checklist
[All 9 items per the master spec's pre-handoff checklist]

## Test-first evidence
[Verbatim failure output for the 3 TEST FAILS tests on master base]

## Per-criterion evidence
[Evidence for each (a) through (k) above]

## Discoveries
[Any out-of-scope findings]
```

## Out of scope

- Do NOT modify any existing test files unrelated to the hook
- Do NOT change the existing pre-commit hook entries (ruff, codespell, etc.) — purely additive
- Do NOT modify any source code in `src/claude_memory/` — this is tooling-only
- Do NOT bundle other tooling improvements; if you have ideas, file separate issues

## Round 5 discipline reminder

If anything in this spec is ambiguous, contradicts itself, or the picked option seems wrong: **escalate to re-spec — do not infer.** The cost of a re-spec round is small. The cost of a wrong-inference build is large.
