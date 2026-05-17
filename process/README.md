# `process/` — AI Council Coordination Artifacts

This directory contains internal coordination artifacts for Dragon Brain's maintenance workflow. **You don't need to read any of this to use the library.**

## The AI Council (formalized 2026-05-09)

- **Director:** Tabish — strategy, final approval, calibration anchor
- **Architect:** Claude — specs, audit guidelines, principles docs
- **Builder:** Antigravity (Gemini) — per-spec implementation
- **Auditor:** ChatGPT Codex 5.5 — adversarial verification per pre-defined criteria

## Files

- `REMEDIATION_BUILD_SPEC.md` — builder-facing spec for the v1.2 remediation arc. Per-PR concrete fix steps, test design tables (3 evil + 1 sad + 1 neutral), the bar each PR must meet, pre-handoff sanity checklist (9 items).
- `REMEDIATION_AUDIT_SPEC.md` — auditor-facing spec. Audit protocol, trigger semantics, scope rules, handoff doc semantics, per-PR criteria. The auditor does **not** see the builder spec — auditing recipe biases verification away from outcomes.
- `PR_1_HANDOFF.md` through `PR_6_HANDOFF.md` — per-PR completion artifacts. Diff summaries, tool outputs, per-criterion evidence, Discoveries.

### Handoff doc convention

Handoff docs (`PR_N_HANDOFF.md`, `HOUSEKEEPING_HANDOFF.md`) record the COMMIT BEING AUDITED, not the handoff's own commit. When authoring a handoff:

1. Write `**Commit:** <auto>` in the commit-hash field
2. Commit the handoff with the work it documents
3. The `inject-handoff-hash` pre-commit hook replaces the placeholder with the actual HEAD hash

This is the documented resolution to the chicken-and-egg hash-drift problem that plagued the v1.2.1 Round 2 remediation arc (6+ recurrences). See [issue #15](https://github.com/iikarus/Dragon-Brain/issues/15) for the design discussion.

## Why this is in the public repo

No trade secrets here — open-sourcing the spec architecture shows Dragon Brain's quality posture is intentional, not accidental. Researchers and fellow architects can study this as a worked example of the trifecta pattern in production.
