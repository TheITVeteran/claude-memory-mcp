# Issue #15 — Pre-commit Hook for Handoff Hash Injection (Audit Spec)

**Issue:** [iikarus/Dragon-Brain#15](https://github.com/iikarus/Dragon-Brain/issues/15)
**Architect:** Claude (defines audit criteria)
**Auditor:** ChatGPT Codex 5.5 (this is your spec)
**Builder:** Antigravity (under separate `15_BUILD_SPEC.md` — you do not see their implementation recipe)
**Director:** Tabish

This is the audit-side document. The build spec lives in `process/issues/15_BUILD_SPEC.md` — **you do not need to read it.** Auditing recipes biases verification toward checkbox-following instead of outcome-achievement. **Audit outcomes, not recipes.**

The master `process/REMEDIATION_AUDIT_SPEC.md` defines the general audit protocol (trigger, scope, handoff doc semantics, pre-handoff checklist verification, test-first verification, Discoveries section). This document narrows the per-issue criteria.

---

## What You're Auditing

A pre-commit hook + supporting docs that resolves the recurring handoff-hash-drift Discovery flagged in every PR of the v1.2.1 Round 2 remediation arc.

**Background context (relevant for outcome verification, not for recipe-following):**

Every handoff doc had a `**Commit:**` field that AG manually populated with `git rev-parse HEAD`. But the act of committing the handoff doc itself produced a NEW hash, drifting the recorded value immediately. The structural fix is to (a) shift the convention so handoffs record the COMMIT BEING AUDITED (= the prior implementation commit, not the handoff's own commit), and (b) automate the hash injection via a pre-commit hook that fires before the commit finalizes.

**The "TEST FAILS" pre-PR rule applies here:** PR-5 onwards uses the 5-row test design table format (3 evil + 1 sad + 1 neutral) with explicit pre-PR/post-PR behavior. For TEST FAILS rows, verify the handoff includes verbatim failure output AND independently re-run the test against the master base in a worktree to confirm the failure is real.

---

## Audit Trigger

Standard per-master-spec: fires when AG creates `process/PR_ISSUE_15_HANDOFF.md` at the repo root AND pushes the branch `issue-15/inject-handoff-hash-hook`. Director invokes with branch ref + handoff doc + this audit spec.

---

## Per-Issue Criteria

Verify each criterion against ground truth. No "looks fine" — paste evidence (file:line, command output, test output).

### (a) Hook script exists with correct semantics

The file `scripts/hooks/inject_handoff_hash.py` exists and:

- Is a valid Python 3 module (`python -c "import ast; ast.parse(open('scripts/hooks/inject_handoff_hash.py').read())"` succeeds)
- Contains a module-level docstring explaining the **handoff records the commit being audited** convention (verify by reading the docstring)
- Has a `main()` entry point that exits with code 0 on success and non-zero on error

### (b) Pre-commit framework registration is correct

`.pre-commit-config.yaml` contains an entry for `inject-handoff-hash` with at least these properties:

- `entry` points to `scripts/hooks/inject_handoff_hash.py`
- `pass_filenames: false`
- `always_run: true`
- `stages: [commit]`

If any property is missing or different, flag it — these are intentional choices (the hook discovers its own targets via `git diff --cached`; must fire on every commit since handoffs aren't always `.md`-filtered).

### (c) End-to-end hash injection test (this is the outcome verification, do this carefully)

Set up a temporary mini-git scenario:

```bash
# In a tmp directory outside the repo
mkdir /tmp/audit-15 && cd /tmp/audit-15
git init && git config user.email a@b && git config user.name a
echo "first" > file.txt && git add . && git commit -m "first commit"
# Capture HEAD hash — this is what should appear in the handoff after injection
PARENT_HASH=$(git rev-parse HEAD)
mkdir -p process scripts/hooks
# Copy the hook script from the PR
cp /path/to/repo/scripts/hooks/inject_handoff_hash.py scripts/hooks/
# Stage a handoff with the placeholder
echo "# Handoff" > process/PR_ISSUE_15_HANDOFF.md
echo "" >> process/PR_ISSUE_15_HANDOFF.md
echo "**Commit:** <auto>" >> process/PR_ISSUE_15_HANDOFF.md
git add process/PR_ISSUE_15_HANDOFF.md
# Run the hook directly (no pre-commit framework needed for this audit)
python scripts/hooks/inject_handoff_hash.py
# Verify the placeholder was replaced with the PARENT_HASH
grep -c "\\*\\*Commit:\\*\\* \`${PARENT_HASH}\`" process/PR_ISSUE_15_HANDOFF.md
# Expected: 1 (placeholder replaced with backtick-wrapped parent hash)
grep -c "<auto>" process/PR_ISSUE_15_HANDOFF.md
# Expected: 0 (no leftover placeholder)
```

Pass if the parent hash appears verbatim in the post-hook file. Fail if the placeholder remains or any other string appears in place.

### (d) Idempotency

Run the hook twice in succession on the same staged handoff (the same scenario as (c)). Verify:

- First run: replaces placeholder, prints injection message
- Second run: finds no placeholder (because first run already replaced it), prints nothing, exits 0
- File content is identical between the two runs

### (e) Scope discipline — non-handoff files untouched

Create a `docs/notes.md` (or any non-`process/PR_*_HANDOFF.md` markdown file) with `**Commit:** <auto>` text. Stage it. Run the hook. Verify:

- The non-handoff file is UNCHANGED post-hook
- Only files matching `^process/(PR_.+|HOUSEKEEPING)_HANDOFF\.md$` are processed

### (f) Test design table implemented + test-first evidence

`tests/unit/test_inject_handoff_hash.py` exists with all 5 tests from the build spec's Tests table:

- `test_evil_placeholder_replaced_in_handoff`
- `test_evil_multiple_handoffs_processed_in_one_commit`
- `test_evil_non_handoff_markdown_untouched`
- `test_sad_handoff_without_placeholder_is_noop`
- `test_neutral_no_handoffs_staged`

All 5 pass against the new code. Per the master AUDIT_SPEC step 9, for the 3 TEST FAILS pre-PR rows (the three evil tests), the handoff doc MUST include verbatim first-run failure output captured against the pre-PR base. **Independently verify** by checking out master in a worktree, copying the new test file in, and running the 3 evil tests — they should fail with ImportError or similar (because the script module doesn't exist on master).

### (g) Documentation updated

`process/REMEDIATION_BUILD_SPEC.md` pre-handoff checklist item 1 has been updated to document the `<auto>` placeholder convention. Verify by reading the updated text.

`process/README.md` has a new "Handoff doc convention" section explaining the placeholder and linking to issue #15.

### (h) Deterministic gates unchanged

- `tox -e contracts` post-PR shows delta = 0 (the new files are in `scripts/hooks/` and `tests/unit/`, outside `src/claude_memory/` — should not affect the contract scanner's per-file count)
- `python -m mypy --strict src/claude_memory` still passes (no source layer changes)
- `python -m ruff check src/claude_memory tests scripts` passes
- Full unit suite (`pytest tests/unit/ -q`) passes including the 5 new tests

---

## Audit Protocol Summary

Standard per master spec:

1. Run deterministic tools first (`tox -e contracts`, `mypy --strict`, `bandit`, `ruff`, `pytest tests/unit/`)
2. Run the per-criterion verifications (a) through (h) above
3. Verify pre-handoff checklist completeness in the handoff doc (master spec step 8)
4. Verify test-first evidence for the 3 TEST FAILS rows (master spec step 9)
5. Flag any Discoveries outside this spec's scope

---

## Constraints (Codex Must NOT)

- Audit aspects outside this issue's scope (this is a hook, not a code change; ignore unrelated tooling)
- Audit recipe-following (you don't see the build spec; verify the OUTCOMES described above)
- Mark a criterion as failed if the implementation differs from the recipe but achieves the documented outcome
- Accept the handoff's claims without ground-truth verification

---

## Output Format

Standard per master spec:

```markdown
# Issue #15 Audit Result

**Verdict:** PASS | FAIL | PARTIAL PASS

## Tool outputs (verbatim)
[paste outputs from steps 1-5 of the master spec protocol]

## Per-criterion evidence
### (a) Hook script exists with correct semantics
**Status:** PASS | FAIL
**Evidence:** [file:line, command output, etc.]

### (b) Pre-commit framework registration
...

[continue through (h)]

## Pre-handoff checklist verification
[per master spec step 8]

## Test-first evidence verification
[per master spec step 9, independently re-ran the 3 TEST FAILS tests against master]

## Discoveries (out-of-scope findings)
[any net-new bugs not covered by this issue's scope]

## Cross-check verdict
[summary]
```

If verdict is FAIL or PARTIAL PASS, name the failing criteria precisely. Don't bury the lede.

*Audit outcomes, not recipes. The end-to-end hash-injection test in (c) is the canonical outcome check — if a handoff with `<auto>` placeholder ends up with the parent HEAD hash after the hook runs, the implementation works regardless of how the script is structured internally.*
