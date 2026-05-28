# Issue #22a — Audit Spec (the foundational mock factory)

**Issue:** parent #22 — sub-chunk 22a
**Auditor:** ChatGPT Codex 5.5
**Builder spec:** `process/issues/22a_BUILD_SPEC.md` — **do NOT read**.

---

## Canonical pass/fail

```bash
python -m pytest tests/_helpers/ -v
```

All 8 tests must pass. Plus the deterministic gates below.

Plus an introspection sanity check (architect-prescribed, since the helper IS the outcome being audited):

```bash
python -c "
from tests._helpers.mock_factory import make_mock_service
from unittest.mock import AsyncMock, MagicMock
svc = make_mock_service()
assert isinstance(svc.repo, AsyncMock), 'repo must be AsyncMock'
assert isinstance(svc.vector_store, AsyncMock), 'vector_store must be AsyncMock'
assert isinstance(svc.activation_engine.activate, AsyncMock), 'activate must be AsyncMock'
assert isinstance(svc.activation_engine.spread, AsyncMock), 'spread must be AsyncMock'
assert isinstance(svc.fts_store, MagicMock) and not isinstance(svc.fts_store, AsyncMock), 'fts_store must be MagicMock (sync target)'
print('PASS: type-correct mock topology verified')
"
```

Must print `PASS: type-correct mock topology verified` with exit code 0.

## Per-criterion verification

### (a) Helper module exists at expected path

```bash
ls tests/_helpers/mock_factory.py tests/_helpers/conftest.py tests/_helpers/__init__.py tests/_helpers/test_mock_factory.py
```

All four files must exist.

### (b) `make_mock_service` signature is correct

```bash
python -c "
import inspect
from tests._helpers.mock_factory import make_mock_service
sig = inspect.signature(make_mock_service)
params = sig.parameters
assert 'embedding_service' in params, 'embedding_service kwarg required'
assert 'allow_sync' in params, 'allow_sync kwarg required'
assert any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()), '**overrides required'
print('PASS: signature correct')
"
```

### (c) Type-correct introspection

The architect-prescribed sanity check from "Canonical pass/fail" above. All 5 assertions must hold.

### (d) `mock_service_factory` fixture exists and threads marker

Inspect `tests/_helpers/conftest.py` — must define `mock_service_factory` fixture and call `config.addinivalue_line` for the `allow_sync_mock` marker. Then verify via:

```bash
python -m pytest --markers 2>&1 | grep "allow_sync_mock"
```

Must return a non-empty match describing the marker.

### (e) 8 tests present + all pass

```bash
python -m pytest tests/_helpers/test_mock_factory.py -v --tb=short
```

Output must show 8 PASSED. Verify each test name from build spec's Tests table is present:
- `test_evil_repo_is_asyncmock_with_async_methods`
- `test_evil_vector_store_is_asyncmock`
- `test_evil_activation_engine_methods_are_asyncmock`
- `test_evil_sync_targets_are_magicmock`
- `test_sad_override_replaces_dep`
- `test_sad_allow_sync_keeps_magicmock_on_async_target`
- `test_sad_marker_threading_via_fixture`
- `test_neutral_construction_succeeds`

### (f) Test-first evidence captured

Per master spec step 9, all 8 tests are marked "TEST FAILS" pre-PR (the helper doesn't exist yet → ImportError). Handoff must include verbatim pre-PR failure output for each. Independently re-run against pre-PR commit hash to verify.

### (g) Scope discipline — write-guard not bypassed

```bash
git diff --name-only master..HEAD
```

Expected output (must match exactly, ordering insensitive):
- `process/PR_ISSUE_22A_HANDOFF.md`
- `tests/_helpers/__init__.py`
- `tests/_helpers/conftest.py`
- `tests/_helpers/mock_factory.py`
- `tests/_helpers/test_mock_factory.py`

Any other file in the diff = write-guard bypassed or scope creep — FAIL with the surprise file listed.

### (h) Hash topology

Handoff `**Commit:**` field equals `git rev-parse HEAD~1`. The two-commit topology must be intact.

### (i) Deterministic gates unchanged

- `tox -e contracts` — baseline 13 unchanged
- `python -m mypy --strict src/claude_memory` — 40 files clean (no source changes)
- `python -m ruff check src/claude_memory tests scripts` — clean (existing invalid-noqa tolerated)
- `python -m bandit -r src/claude_memory -ll` — only accepted B104

### (j) Pre-handoff checklist complete

Per master spec — 9 items with real evidence pasted, no `N/A` on bandit/contracts/ruff.

## Output format

Standard. Lead with verdict. If PASS, explicitly note: "Helper foundation built. Issue #22b (test_hybrid_search migration) and subsequent per-file migrations now unblocked."
