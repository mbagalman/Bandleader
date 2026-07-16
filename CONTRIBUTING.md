# Contributing to Bandleader

Thanks for your interest in improving Bandleader! Bug reports, fixes, and
feature ideas are all welcome.

## Setup

1. Use Python 3.10+.
2. Fork and clone the repository, then install in editable mode:
```bash
pip install -e .
pip install pytest
```
3. Verify everything works:
```bash
python -m pytest -q
```

Some features shell out to system tools. For full end-to-end runs you also
need FFmpeg and FluidSynth on your PATH (see the [README](README.md)), but
the test suite runs without them.

## Making Changes

1. Open an issue first for anything non-trivial so we can discuss the approach.
2. Create a feature branch from `main`.
3. Keep changes focused — one logical change per pull request.
4. Add or update tests for behavior changes.
5. Keep user-facing errors actionable and specific.
6. Run `python -m pytest -q` before opening the PR.

## Pull Requests

1. Describe what changed and why; link the related issue if there is one.
2. Note any environment limitations you hit (missing tools, missing optional deps).
3. CI must pass before review.

## Commit Guidance

Commit message format recommendation:
`feat(orchestrator): ...`, `fix(generators): ...`, `docs(readme): ...`.
