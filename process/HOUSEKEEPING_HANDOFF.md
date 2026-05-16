# Housekeeping PR — Process Dir + Cleanup

**Commit:** `6c9554e` (post-handoff-add amend; original pre-handoff commit was `6471604a`)
**Branch:** housekeeping/process-dir-and-cleanup

## Diff inventory
```text
REMEDIATION_SPEC_2026-05-13.md
process/HOUSEKEEPING_HANDOFF.md
process/PR_1_HANDOFF.md
process/PR_2_HANDOFF.md
process/PR_3_HANDOFF.md
process/PR_4_HANDOFF.md
process/PR_5_HANDOFF.md
process/PR_6_HANDOFF.md
process/README.md
process/REMEDIATION_AUDIT_SPEC.md
process/REMEDIATION_BUILD_SPEC.md
```

## Pre-handoff checklist

Docs-only PR. Most items N/A; deterministic gates still verified unchanged.

1. **Commit hash:** `6c9554e` (post-handoff-add amend)
2. **Diff inventory:** see above; matches `git diff --name-only` output
3. **mypy --strict:** Success: no issues found in 40 source files (unchanged from PR-6 baseline)
4. **tox -e contracts:** 13 violations, baseline 13, PASS (unchanged from PR-6 baseline)
5. **ruff:** All checks passed! (unchanged)
6. **bandit:** Only accepted B104 at embedding_server.py:148 (unchanged)
7. **Caller sweep:** N/A — no API contract change
8. **Test-first evidence:** N/A — no new tests
9. **Per-criterion walkthrough:** N/A — no per-PR criteria for housekeeping PR

## What changed
- Moved 2 spec docs + 6 handoff docs from root → `process/`
- Added `process/README.md` explaining the directory and the AI Council
- Removed debug/scratch files: `REMEDIATION_SPEC_2026-05-13.md` (old merged spec, superseded by BUILD/AUDIT split)
- `contract_violations_report.md`: already in `.gitignore`; file remains on disk as scanner output, not committed
- Removed worktrees: `audit-pr5-base-c127865` (pruned; Windows file lock prevented clean removal — `git worktree prune` succeeded)
- Updated cross-references: None needed — all references are internal to `process/` (same-directory relative resolution)
- `.gitignore` already contained `contract_violations_report.md` — no changes needed

## Audit treatment

Docs-only PR with no code/behavior change. Tabish may self-review and merge without Codex audit at his discretion.
