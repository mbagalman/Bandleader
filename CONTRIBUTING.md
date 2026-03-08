# Contributing to Bandleader

## Setup

1. Use Python 3.10+.
2. Install dependencies:
```bash
pip install -e .
```
3. Optional drum transcription dependency:
```bash
pip install -e ".[drums]"
```
4. Verify local checks:
```bash
python3 -m pytest -q
```

## Workflow

1. Check [bandleader-workboard.md](bandleader-workboard.md) before starting.
2. Claim your ticket in the Dashboard by setting `Status` to `Claimed` and `Claimed by` to your name.
3. Keep changes scoped to the claimed ticket(s).
4. If you pause mid-ticket, leave a short `Progress note` with exact remaining work.
5. Mark ticket `Done` and update acceptance checkboxes when complete.

## Coding and Testing Expectations

1. Add or update tests for behavior changes.
2. Keep user-facing errors actionable and specific.
3. Run `python3 -m pytest -q` before handing off.
4. Note any environment limitations (missing tools, missing optional deps) in your handoff.

## Commit Guidance

1. Use one commit per logical ticket or tightly related ticket set.
2. Commit message format recommendation:
`feat(orchestrator): ...`, `fix(generators): ...`, `docs(readme): ...`.
3. Reference ticket IDs from `bandleader-workboard.md` in commit body when useful.
