# PR-3 Handoff — Temporal Direction Enum Drift

**Branch:** `remediation/pr-3-temporal-enum-drift`
**Commit:** `4a4b226`
**Base:** `c560e1c` (master, post PR-2 merge + backfill fix + tox posargs)

---

## Diff Summary

| File | Change | Purpose |
|------|--------|---------|
| `src/claude_memory/schema.py` | Modified | Widened `Literal` to `["before", "after", "both", "forward", "backward"]` |
| `src/claude_memory/repository_queries.py` | Modified | Updated if-elif chain to accept all four direction spellings |
| `tests/unit/test_repository_queries.py` | Modified | Added 3 evil tests for alias behavior |

---

## Per-Criterion Evidence

### (a) All four spellings produce semantically correct results

| Direction | Cypher Pattern | Semantics |
|-----------|---------------|-----------|
| `"before"` | `<-[r:...]-(m)` | Incoming temporal edges (the past) |
| `"backward"` | `<-[r:...]-(m)` | Same as `"before"` |
| `"after"` | `-[r:...]->(m)` | Outgoing temporal edges (the future) |
| `"forward"` | `-[r:...]->(m)` | Same as `"after"` |
| `"both"` | `-[r:]-(m) DISTINCT` | Union of both directions |

### (b) `tox -e contracts` delta = 0

```
75 violations (Sync IO: 62, Bare Pass: 6, Silent Fallback: 5, Per-Item Swallow: 2)
```

### (c) No `warnings` module imports

```
$ grep -r "import warnings" src/claude_memory/repository_queries.py
(no results)
```

### (d) No callers rely on silent-fallthrough-to-both

```
$ grep -rn "direction=" src/claude_memory/
```
All callers pass explicit values or use the default `"both"`.

---

## Tool Outputs

| Check | Result |
|-------|--------|
| Unit tests | 1268 passed (1265 + 3 new) |
| Contracts | 75 violations (delta = 0) |
| Ruff | Passed |
| Pre-commit | All hooks passed |
