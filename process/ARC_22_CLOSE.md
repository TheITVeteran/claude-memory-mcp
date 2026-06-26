# Arc Close: Issue #22 — Test-Suite Mock Architecture (May–June 2026)

This document captures the WHY behind the 5-layer test-suite physical enforcement (`CLAUDE.md` § Test-suite physical enforcement) and the trifecta calibration lessons from the 14a–22f sequence. The HOW lives in `CLAUDE.md`. The reference reading lives in `process/issues/22*_BUILD_SPEC.md` and `process/issues/22*_AUDIT_SPEC.md`. This document is the narrative connecting them.

## What was broken before

Across `tests/unit/`, dozens of test files hand-rolled `MemoryService` fixtures by constructing the real class and then reassigning every dependency to a mock manually:

```python
svc = MemoryService(embedding_service=mock_embedder)
svc.repo = AsyncMock()
svc.activation_engine = MagicMock()                              # ← loses class introspection
svc.activation_engine.activate = AsyncMock(return_value={})      # ← WRONG TYPE (activate is sync def)
svc.activation_engine.spread = AsyncMock(return_value={})        # right type, wrong pattern
```

Two failure modes followed:

1. **Wrong-type mocks** — `ActivationEngine` is a mixed class (`async def spread` per `activation.py:98`, plain `def activate` per `activation.py:76`). Hand-rolled fixtures couldn't track this; tests routinely assigned `AsyncMock` to sync methods (or `MagicMock` to async ones). The mismatches produced unawaited coroutines that surfaced as `RuntimeWarning` at GC time, attributed to the wrong tests (GC nondeterminism).
2. **Suppression sneak-arounds** — instead of fixing the type mismatches, several files added an autouse `_drain_orphan_coroutines` fixture that ran `gc.collect()` inside a `warnings.catch_warnings()` context to silently drain unawaited coroutines per test. This made the symptom invisible without fixing the root cause.

The combination meant the test suite passed under default settings while harboring real type bugs. Under `-W error` (strict warning-as-error mode), warnings leaked unpredictably depending on `pytest-randomly` seed, with ~25–33% emission rate.

## What we built

### Phase 1: helper (`22a`)

`tests/_helpers/mock_factory.py` — `make_mock_service()` constructs a `MemoryService` with type-correct mocks for every dependency. The helper introspects each dependency class via `inspect.iscoroutinefunction()` to decide `AsyncMock` vs `MagicMock` per method automatically.

Key design:
- Pure-async classes (every public method is `async def`) → outer is `AsyncMock(spec=cls)`. AsyncMock auto-coroutines all child calls, so methods not explicitly introspected still behave correctly when awaited.
- Mixed or pure-sync classes → outer is `MagicMock(spec=cls)`, with `AsyncMock` explicitly attached per async method via `inspect.iscoroutinefunction`. Prevents spurious coroutines on sync method calls (e.g., `ActivationEngine.activate` stays `MagicMock`).

The helper has its own 8-test acceptance suite covering 3 evil + 1 sad + 1 neutral patterns. The load-bearing assertion is the canonical introspection sanity check: `svc.activation_engine.spread is AsyncMock`, `svc.activation_engine.activate is MagicMock and not AsyncMock`.

### Phase 2: per-file migrations (`22b`–`22e-bis`)

| PR | Files migrated | Distinguishing constraint |
|----|---------------|--------------------------|
| 22b | test_hybrid_search.py | Worst-leakage file — validating the helper on the file that produced the most warnings |
| 22c | test_tools_coverage.py | Largest dep surface — `lock_manager` context manager, `_fire_salience_update` workaround |
| 22d | test_memory_service.py | Last file with `_drain_orphan_coroutines` suppression (2078 lines, 10 surgery sites) |
| 22e | test_entity_channel + test_search_associative + test_embedding_filter + test_channel_degradation | 4 files in one PR; unique constraint: test_channel_degradation uses `async with` on lock context manager (`__aenter__`/`__aexit__`, not sync `__enter__`/`__exit__`) |
| 22e-bis | test_batch3_contracts + test_batch5_contracts | Caught by Codex's wider AST-style grep that the Architect's fixture-name grep missed; test_batch5 had 8 inline constructions with 16 duplicate-`svc.repo` typo sites |

Each migration followed the same Topographical Forcing pattern: delete the suppression fixture if present, replace the fixture body with `make_mock_service()`, add a `test_meta_fixture_topology_required` forcing test that fails-loud on any regression, scan for and clean up mid-test mock surgery sites.

The migrations preserved 16 files as **Category D** — intentional patterns where the helper would change semantics: bare-MagicMock stubs (test_router, test_list_orphans), real-dependency tests (test_locking uses real `LockManager`, test_dynamic_validation uses real `OntologyManager`), mutant-testing factories (test_mutant_dict_crud, test_mutant_dict_services, test_mutant_temporal), and lightweight-integration tests using `service.repo.client = MagicMock()` direct access (test_temporal, test_hologram, test_full_workflow, test_analysis_radar, test_entity_lifecycle, test_graph_traversal, test_phase4, test_semantic_radar, test_session).

### Phase 3: lockdown (`22f`)

Five layers of physical enforcement. Each catches a specific class of regression at commit/build time:

1. **`branch_write_guard.py`** — pre-commit hook reading per-issue `process/issues/N_HARNESS.toml` denylists. Catches Architect spec edits on Builder branches, conftest sneak-arounds, `src/` scope creep on test-only PRs.
2. **`inject_handoff_hash.py`** — pre-commit hook auto-injecting implementation commit's hash into handoff doc's `**Commit:** <auto>` placeholder. Catches hand-edited or fabricated hashes.
3. **`verify_handoff_completeness.py`** — pre-commit hook validating handoff files for 4-seed baseline, canonical ruff command (no `--exclude`), no `N/A` shortcuts on deterministic gate sections.
4. **`trace_contracts_dragon.py` Pattern 12** — AST scanner flagging hand-rolled `MemoryService(embedding_service=...)` constructions outside the 17-entry allowlist (1 helper + 16 architect-verified Category D files). Baseline = 0; any reintroduction fails CI.
5. **Existing scanner Patterns 1–11** — baseline 13 (ratcheting toward zero quarterly) for the original audit-remediation contract violations.

The audit spec for layer 4 includes an AST-based smuggling check that fails if the detector function body contains hardcoded `test_*.py` literals — all allowlisting MUST flow through the public `PATTERN_12_ALLOWLIST` constant so the structural check is meaningful.

## Trifecta calibration lessons

This was the first major arc to run end-to-end with the 4-seat trifecta formalized post-v1.2.1 (Director, Architect, Builder, adversarial Auditor). Codex earned its seat four times:

1. **Original Round 1 substance bugs** — Cypher injection at `repository.py:90`, point-in-time `created_at` payload drift, temporal direction enum drift. The prior 3-seat trifecta shipped 10 batches without catching these.
2. **Hygiene drift pattern** — four consecutive R1 audits (22a/22b/22c/22d) failed criterion (j) handoff completeness in different specific ways. Verbal discipline and spec hardening couldn't close the loop. The structural fix was `verify_handoff_completeness.py` in 22f. Lesson: when verbal discipline fails 3+ times, switch to physical enforcement.
3. **Architect spec false-positive (22e R1)** — audit check for the async lock context manager looked for bare string `__enter__` in fixture source; the Architect's own build-spec golden-diff docstring contained the literal `__enter__/__exit__` as a teaching note about how this file differs from the others, triggering a false-positive FAIL. The patched check matches assignment patterns specifically (`\.__enter__\s*=`) so docstring text doesn't trigger.
4. **Builder workaround attempt (22f R1)** — Builder added 6 file path exemptions hardcoded inside the detector function body, hiding them from the `PATTERN_12_ALLOWLIST` constant the audit's structural check verifies. Architect investigation confirmed the 6 files were genuinely Category D (same lightweight-integration pattern as test_temporal/test_hologram) — substance was correct, process was wrong. Fix: moved exemptions into the public constant + added smuggling check to audit spec.

**Three of those four were on Architect/Builder, not on Auditor.** The Auditor's value is not catching the Auditor's own bugs — it's catching the rest of the trifecta when they drift.

### Spec-patch discipline (the goalposts guard)

Two arc events tested the discipline of patching audit specs after a FAIL: 22e R1 (docstring false-positive) and 22f R1 (allowlist expansion). Both passed the substance test:

- **22e R1:** would Builder have had to do something WORSE to pass the original check? Yes — delete the useful teaching docstring. Patched check captured intent more precisely (assignment pattern, not bare string). **Direction:** tightened substance, loosened text-presence. Oracle correction.
- **22f R1:** were the 6 newly-exempted files genuinely Category D? Yes — same lightweight-integration pattern as 4 existing Category D files. Patched spec also added smuggling check (AST scan for hardcoded literals inside detector body). **Direction:** captured more intent (structural integrity) on top of expanding the allowlist. Oracle correction.

Neither was goalposts-moving. Going forward: when patching audit spec after FAIL, commit message must explicitly answer "what was implementation semantically required to do?" and "why does the patched check capture that intent more precisely?"

### Architect methodology gap

Single-line `grep` missed multi-line `MemoryService(embedding_service=...,\n    vector_store=...)` constructions three times across the 22e/22e-bis/22f investigations. The Auditor's AST-based scan caught them each time. Lesson: for systematic enumeration questions ("find all places that do X across the codebase"), use AST-based tools or the codebase's own scanner. Single-line grep is for grep-shaped problems, not for AST-shaped problems. Logged for future investigations.

## Final state

- **Bug class structurally eliminated** outside the 17-entry allowlist (1 helper + 16 architect-verified Category D)
- **Zero `_drain_orphan_coroutines`** suppressions repo-wide (verified by closing Discovery)
- **Pattern 12 baseline contribution = 0** — any future hand-rolled `MemoryService(embedding_service=...)` outside the allowlist fails CI
- **5 layers of physical enforcement** active and verified via synthetic violation + synthetic hook rejection demonstrations
- **Helper acceptance tests, both new pre-commit hooks, and the contracts scanner** all green under `tox -e contracts`, mypy strict, ruff canonical, bandit
- **`tox -e contracts` baseline holds at 13** (down from 64 at the original Audit Remediation start; quarterly ratchet continues)

## For future maintainers

**Adding a new test file?** Use `make_mock_service()` from `tests/_helpers/mock_factory.py`. The fixture body is:

```python
@pytest.fixture()
def service():
    return make_mock_service()
```

For test-specific configuration, configure on the helper-built mocks rather than replacing them: `svc.repo.get_node.return_value = ...`, `svc.activation_engine.activate.return_value = ...` (helper already typed it correctly as `MagicMock`), etc.

**Adding a new test file that genuinely needs hand-rolled construction?** Add the path to `PATTERN_12_ALLOWLIST` in `scripts/trace_contracts_dragon.py` AND add a comment explaining which architectural group it belongs to (bare-stub, real-dep, mutant-testing factory, lightweight-integration). If it doesn't fit any of the four groups, the file probably needs migration, not allowlisting.

**Hitting a spec false-positive in your CI?** The substance test: would your implementation have had to do something WORSE to pass the original check? If yes, escalate as a spec issue. If no, fix the implementation. Do not bypass via `--no-verify` or smuggle exemptions into private function bodies.

**Encountering a recurring hygiene drift across multiple PRs?** Stop trying to fix it via verbal discipline or spec hardening. After 3 consecutive failures of the same checklist item in different specific ways, switch to physical enforcement (pre-commit hook, scanner pattern). The 22f `verify_handoff_completeness.py` hook is the working template.
