# Issue #15 Handoff — Pre-commit Hook for Handoff Hash Injection

**Commit:** `a81d701559c9a97c77e74a67170a088fb7a9e570`
**Branch:** issue-15/inject-handoff-hash-hook
**Issue:** https://github.com/iikarus/Dragon-Brain/issues/15

## Diff inventory

```
.pre-commit-config.yaml
process/PR_ISSUE_15_HANDOFF.md
process/README.md
process/REMEDIATION_BUILD_SPEC.md
scripts/hooks/inject_handoff_hash.py
tests/unit/test_inject_handoff_hash.py
```

## Pre-handoff checklist

1. **Commit hash:** `**Commit:** `a81d701559c9a97c77e74a67170a088fb7a9e570`` — this handoff is the first to use the hook itself. The `inject-handoff-hash` pre-commit hook will replace the placeholder at commit time with the implementation commit hash (`a81d701`).
2. **Diff inventory:** see above — matches `git diff --name-only master..HEAD` output (6 files including this handoff doc)
3. **mypy --strict:** `Success: no issues found in 40 source files` — unchanged from baseline (no `src/claude_memory/` changes)
4. **Contract scanner:** `Scanned 40 files. Found 13 violations. SUCCESS: Violations (13) are within baseline (13).` — delta = 0
5. **Ruff:** clean — `noqa: S607` markers on intentional subprocess/git calls in hook script; `noqa: S603` on test helpers
6. **Bandit:** `python -m bandit -r src/claude_memory -ll` — only finding is accepted B104 `hardcoded_bind_all_interfaces` at `embedding_server.py:148:26` (`uvicorn.run(app, host="0.0.0.0", port=port)  # noqa: S104`). 6740 lines scanned, 0 high severity, 1 medium (the accepted bind-all). ✅
7. **Caller sweep:** N/A (no API contract changes)
8. **Test-first evidence:** 3 evil tests captured below — all 5 tests failed pre-PR due to missing script (ENOENT)
9. **Per-criterion evidence:** see section below

## Test-first evidence

All 5 tests failed pre-PR with identical root cause: `python: can't open file '...\scripts\hooks\inject_handoff_hash.py': [Errno 2] No such file or directory`

**3 Evil tests (required captures):**

### test_evil_placeholder_replaced_in_handoff
```
FAILED tests/unit/test_inject_handoff_hash.py::test_evil_placeholder_replaced_in_handoff
AssertionError: Hook failed: python: can't open file 'C:\\Users\\Asus\\.gemini\\antigravity\\scratch\\new_project\\claude-memory-mcp\\scripts\\hooks\\inject_handoff_hash.py': [Errno 2] No such file or directory
assert 2 == 0
```

### test_evil_multiple_handoffs_processed_in_one_commit
```
FAILED tests/unit/test_inject_handoff_hash.py::test_evil_multiple_handoffs_processed_in_one_commit
AssertionError: Hook failed: python: can't open file 'C:\\Users\\Asus\\.gemini\\antigravity\\scratch\\new_project\\claude-memory-mcp\\scripts\\hooks\\inject_handoff_hash.py': [Errno 2] No such file or directory
assert 2 == 0
```

### test_evil_non_handoff_markdown_untouched
```
FAILED tests/unit/test_inject_handoff_hash.py::test_evil_non_handoff_markdown_untouched
assert 2 == 0
 +  where 2 = CompletedProcess(..., returncode=2, stderr="python: can't open file '...\\inject_handoff_hash.py': [Errno 2] No such file or directory\n").returncode
```

**Post-PR: all 5 tests pass:**
```
tests/unit/test_inject_handoff_hash.py::test_sad_handoff_without_placeholder_is_noop PASSED
tests/unit/test_inject_handoff_hash.py::test_evil_placeholder_replaced_in_handoff PASSED
tests/unit/test_inject_handoff_hash.py::test_evil_multiple_handoffs_processed_in_one_commit PASSED
tests/unit/test_inject_handoff_hash.py::test_neutral_no_handoffs_staged PASSED
tests/unit/test_inject_handoff_hash.py::test_evil_non_handoff_markdown_untouched PASSED
============================== 5 passed in 3.27s ==============================
```

## Per-criterion evidence

**(a)** `scripts/hooks/inject_handoff_hash.py` exists with docstring describing the convention — ✅ (lines 1-15)

**(b)** `.pre-commit-config.yaml` registers `inject-handoff-hash` with `pass_filenames: false`, `always_run: true`, `stages: [commit]` — ✅ (lines 32-38)

**(c)** End-to-end: `test_evil_placeholder_replaced_in_handoff` creates mini-git repo, stages handoff with `<auto>`, runs hook, verifies placeholder replaced with parent HEAD hash and file re-staged — ✅

**(d)** Idempotency: `test_sad_handoff_without_placeholder_is_noop` stages a handoff with an existing hash (no `<auto>`), runs hook, verifies file unchanged — ✅

**(e)** Scoping: `test_evil_non_handoff_markdown_untouched` stages `docs/notes.md` with `<auto>` text + a real handoff, verifies only the handoff is processed — ✅

**(f)** 5-row test table implemented; 3 TEST FAILS tests have verbatim pre-PR failure evidence above — ✅

**(g)** `process/REMEDIATION_BUILD_SPEC.md` checklist item 1 updated to document `<auto>` placeholder convention — ✅ (line 378)

**(h)** `process/README.md` "Handoff doc convention" section added — ✅ (lines 18-27)

**(i)** `tox -e contracts` delta = 0 — new files are in `scripts/hooks/` and `tests/unit/`, outside `src/claude_memory/` scan path — ✅

**(j)** `mypy --strict src/claude_memory` passes: `Success: no issues found in 40 source files` — ✅

**(k)** Full unit suite: `1283 passed, 0 failures` — ✅

## Discoveries

1. **Pre-commit stage name deprecation:** Hook registration with `stages: [commit]` triggers a `[WARNING] hook id 'inject-handoff-hash' uses deprecated stage names (commit) which will be removed in a future version. run: 'pre-commit migrate-config' to automatically fix this.` The fix is `stages: [pre-commit]` but spec said `stages: [commit]` — followed spec literally. Future PR can run `pre-commit migrate-config` to modernize all hooks.

2. **Meta-recursion:** This handoff doc is the first to use the hook it documents. The `<auto>` placeholder in the Commit field above will be replaced by the hook at commit time, proving the mechanism works in production on its own artifact.
