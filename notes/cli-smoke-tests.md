# Bandleader CLI Smoke Tests

Date: 2026-03-07
Runner: Codex
Environment: macOS system Python 3.9 in workspace, project not installed via `pip install -e .`

## Entry-point command availability

The console scripts are **not available** in PATH in the current environment:

- `bandleader`: not found
- `bandleader-drums`: not found
- `bandleader-stems`: not found
- `bandleader-synth`: not found
- `bandleader-bass`: not found
- `bandleader-arp`: not found

Likely cause: package not installed in active environment.

## Module help smoke tests

Commands executed from project root using `python3 -m ... --help`.

### PASS

- `python3 -m bandleader.stem_cleaner --help`

### FAIL

- `python3 -m bandleader --help`
  - `ModuleNotFoundError: No module named 'yaml'`

- `python3 -m bandleader.drum_cleaner --help`
  - `ModuleNotFoundError: No module named 'mido'`

- `python3 -m bandleader.synth_cleaner --help`
  - `ModuleNotFoundError: No module named 'mido'`

- `python3 -m bandleader.bass_generator --help`
  - `ModuleNotFoundError: No module named 'mido'`

- `python3 -m bandleader.arp_generator --help`
  - `ModuleNotFoundError: No module named 'mido'`

## Troubleshooting

1. Install project dependencies:
   - `python3 -m pip install -r requirements.txt`
   - or `python3 -m pip install -e .`
2. Re-run smoke tests after dependency install.
3. If console scripts are still not found, confirm the active Python environment is the same one where package install occurred.
