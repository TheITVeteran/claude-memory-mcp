# PR-1 Handoff to Codex Round 2

## Diff summary
- Files changed: `src/claude_memory/schema.py`, `src/claude_memory/repository.py`, `tests/unit/test_schema.py` (new)
- LoC added: ~220 (mostly tests); ~15 in production code
- Branch: `remediation/pr-1-cypher-guard`
- Commit: `56f888d`

## Tool outputs (run in order — Codex audit protocol)

### 1. `tox -e contracts` (contract scanner)
```
Scanned 40 files. Found 75 violations.

By category:
  Sync IO in Async: 62
  Bare Pass: 6
  Silent Fallback: 5
  Per-Item Swallow: 2

ERROR: Violations (75) exceed baseline (0)!
```
**Note:** Baseline is set to 0 in the scanner config (not 13). The 75 count is unchanged from pre-PR state. Real violations = 13 (baseline). The 62 "Sync IO in Async" are false positives fixed in PR-6. Violation count is identical pre- and post-PR.

### 2. `python -m mypy --strict src/claude_memory/schema.py src/claude_memory/repository.py`
```
Success: no issues found in 2 source files
```

### 3. `python -m ruff check src/claude_memory/schema.py src/claude_memory/repository.py tests/unit/test_schema.py`
```
All checks passed!
```
One `# noqa: S101` on `repository.py:80` — justified: intentional defensive assert per remediation spec PR-1 design.

### 4. Unit test output
```
35 passed in 2.20s
```

### 5. Full regression suite
```
1264 passed, 1 failed in 191.08s
```
The 1 failure is **pre-existing on master** (`test_embedding_coverage.py::test_happy_call_api_success`) — caused by `c6ef638` attribution hook adding `params={'client_id': 'unknown'}` without updating the test mock. Not related to PR-1. Verified by running the same test on master branch — same failure.

## Evidence per audit criterion

### (a) Confirm validator rejects: empty string, lowercase start, spaces, `}`, `{`, `:`, `'`, `"`, backtick, newline

| Input | Test | Result |
|-------|------|--------|
| `""` (empty) | `test_evil2_empty_string_rejected` | ✅ `ValueError` raised |
| `"entity"` (lowercase) | `test_evil2_lowercase_start_rejected` | ✅ `ValueError` raised |
| `"Memory Type"` (space) | `test_evil2_spaces_rejected` | ✅ `ValueError` raised |
| `"Entity { x: 1}"` (`}`) | `test_evil1_cypher_close_brace_rejected` | ✅ `ValueError` raised |
| `"Entity{name:$x}"` (`{`) | `test_evil1_cypher_open_brace_rejected` | ✅ `ValueError` raised |
| `"Entity:Hacked"` (`:`) | `test_evil1_cypher_colon_rejected` | ✅ `ValueError` raised |
| `"Entity'DROP"` (`'`) | `test_evil1_single_quote_rejected` | ✅ `ValueError` raised |
| `'Entity"DROP'` (`"`) | `test_evil1_double_quote_rejected` | ✅ `ValueError` raised |
| `` "Entity`DROP`" `` (backtick) | `test_evil1_backtick_rejected` | ✅ `ValueError` raised |
| `"Entity\nDROP"` (newline) | `test_evil1_newline_rejected` | ✅ `ValueError` raised |

Evidence: `tests/unit/test_schema.py` — all pass.

### (b) Confirm validator accepts: `Entity`, `MemoryType`, `Concept_v2`, `A`, max-64-char identifier

| Input | Test | Result |
|-------|------|--------|
| `Entity` | `test_happy_existing_node_types_all_valid[Entity]` | ✅ Accepted |
| `MemoryType` | `test_happy_mixed_case_alphanumeric` | ✅ Accepted |
| `Concept_v2` | `test_happy_underscore_name_accepted` | ✅ Accepted |
| `A` | `test_sad1_single_char_accepted` | ✅ Accepted |
| `A` + 63 chars | `test_happy_max_64_chars_accepted` | ✅ Accepted |
| All 13 live node_types | `test_happy_existing_node_types_all_valid[*]` (parametrized) | ✅ All 13 accepted |

### (c) Run `tox -e contracts` post-PR — baseline must remain 13

Violation count unchanged at 75 (same as pre-PR). Real baseline = 13. Scanner baseline config = 0 (fixed in PR-6). No new violations introduced.

### (d) Verify the assert in `repository.py:80` triggers on injection attempt via direct call

| Test | Result |
|------|--------|
| `test_evil1_direct_call_injection_asserts` — `"Entity { x: 1}"` | ✅ `AssertionError` raised |
| `test_evil2_lowercase_label_asserts` — `"entity"` | ✅ `AssertionError` raised |
| `test_evil3_empty_label_asserts` — `""` | ✅ `AssertionError` raised |
| `test_happy_valid_label_passes_assert` — `"Concept"` | ✅ Passes, reaches graph query |

Evidence: `tests/unit/test_schema.py::TestCreateNodeLabelAssert` — all 4 pass.

## Discoveries (out-of-scope findings)

1. **Pre-existing test failure on master:** `test_embedding_coverage.py::test_happy_call_api_success` fails because commit `c6ef638` (attribution hook) added `params={'client_id': 'unknown'}` to the API call but didn't update the corresponding test mock expectation. This is a 1-line fix in the test file but is out of scope for the remediation spec.
