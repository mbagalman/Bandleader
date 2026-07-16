# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- `song.seed` config option (default `0`): the orchestrator now passes a seed to the bass and arp generators, making orchestrated MIDI output reproducible across runs.
- Preview mix falls back to WAV when the MP3 encoder is unavailable in the local ffmpeg build.
- `bandleader-sidechain` now scans all MIDI tracks (format-1 DAW exports keep notes outside track 0), preserves the position of mid-song tempo changes, and exits non-zero instead of writing an empty trigger file when no kick events are found.
- CI now runs on Windows and macOS (one Python version each) in addition to the Ubuntu matrix, plus a ruff lint job.

### Fixed
- Phase alignment no longer treats a strong *negative* correlation peak as a successful match: only positive peaks are alignment candidates, and a dominant negative peak (likely polarity inversion, which a time shift cannot fix) is reported as a skip with an explicit reason.
- Phase alignment now uses FFT-based correlation instead of direct full correlation, making song-length stems practical (a 60-second 48 kHz stem estimates in ~1 second instead of scaling quadratically toward hours).
- Audio cleaners allocate unique temp paths via `tempfile`; converting `song.mp3` can no longer overwrite (and then delete) a pre-existing `song.temp.wav`, and concurrent runs no longer race on the same path.
- A skipped secondary phase-alignment pair (low confidence, missing reference, non-WAV target) now keeps the dry overheads/guitars stem in the preview mix instead of dropping it entirely.
- `bandleader-sidechain` no longer writes an empty trigger MIDI before failing on zero kick events.
- Pad mode now genuinely honors `--vel-accent` (bar-downbeat chord attacks) and `--vel-jitter` (seeded, per-chord) — they were previously copied into the style but unused.
- `bandleader-bass`, `bandleader-arp`, and `bandleader-sidechain` validate numeric ranges at parse time (positive bars, 4-1000 BPM, MIDI 0-127 note/program, 0-15 channel, 1-127 velocity, 0-1 factors); out-of-range values exit with an argparse error instead of writing empty files or raw tracebacks.
- `bandleader.__version__` now matches the package version (was a stale internal version number).
- `bandleader-stems --deess` now uses valid FFmpeg `deesser` parameters; previously the filter always failed and de-essing was silently skipped via the retry fallback. The fallback warning now states clearly when output is not de-essed.
- Audio cleaners no longer delete an input file that happens to be named `*.temp.wav`; temp-file cleanup now tracks files the tool actually created.
- Arpeggio octave placement now follows the actually selected cycle note for all motions; previously every motion except `up` applied upper-octave offsets to the wrong notes (a `down` arp ascended in register).
- `random_no_repeat` arp motion no longer repeats the same audible note back-to-back; `--gate 0` no longer produces stuck notes; `--octave 8` folds notes back into MIDI range instead of crashing; pad mode now honors `--vel-base`/`--vel-accent`/`--vel-jitter`.
- A YAML syntax error in `song_config.yaml` now exits with a clear message instead of a raw traceback.
- Booleans no longer pass numeric config validation (`bpm: true` was accepted as bpm=1).
- A wrong soundfont path is now reported as "configured path does not exist" instead of "not configured".
- `bandleader-stems` fatal errors (missing ffmpeg, missing input) print a one-line message instead of a traceback when run from the installed console script; drum/synth cleaners validate the input file up front and only print tracebacks with `--verbose`.
- `Co7` and other digit-suffixed diminished shorthands now parse as diminished instead of major.
- Switched to `librosa.feature.tempo` (the deprecated `librosa.beat.tempo` would break tempo estimation on a future librosa release) and set `librosa>=0.10`.
- `bandleader-drums` exits non-zero when no drum hits are detected (previously exited 0 with no output).
- The `.ffmpeg.txt` audit file is written only after ffmpeg succeeds and quotes paths so logged commands are replayable.
- `bandleader-bass`: `--style` typos are rejected instead of silently falling back to `two_feel`; all flags have help text; output directories are created as needed; `--time-signature 0/4` reports a clean error.
- Phase alignment skips non-WAV targets with a clear reason instead of a cryptic decode error, and its confidence "uniqueness" term now compares against genuinely different lags.
- Arp default `--motion` aligned with the documented default (`updown`); arp MIDI resolution matches bass (960 ticks/beat).

### Removed
- madmom drum transcription path (`--method madmom`, `pipeline.clean_drums.use_madmom`, and the `[drums]` extra). No released madmom version provides the drum transcription model the code imported, so the option could never activate; librosa onset detection (the previous fallback) is now the only method.
- `requirements.txt` — `pyproject.toml` is the single source of dependency truth; install with `pip install -e .`.
- Internal version changelogs from module docstrings.
- Dead code: unused legacy dependency check, unused chord-voicing helper, unused imports.

## [0.1.0] - 2026-05-29

### Added
- Generator timing now handles denominator-aware time signatures (for example `6/8`).
- Pad segmentation is now robust for dense chord bars.
- Config validation now reports key-path-specific errors and applies safe defaults for optional sections.
- Initial contributor guide and release checklist docs.
- Drum cleaning can now export sidechain trigger assets (`gen_sidechain_trigger.mid/.wav`).
- Orchestrator can now render sidechain-ducked bass (`gen_bass_ducked.wav`) with configurable depth/attack/release.
- Phase-alignment workflow for kick-bass, snare-overheads, and bass-guitars pairs with bounded lag estimation and confidence gating.
- Phase-alignment report export at `generated/phase_alignment_report.json` including per-pair applied/skipped reasons.

### Changed
- Orchestrator dependency checks are now step-aware instead of globally requiring all tools.
- Preview mix filter graph now normalizes channels/sample format before `amix`.
- Stem file search now uses deterministic tie-breaking and warns on ambiguous equal-rank matches.
- Orchestrator vocal cleaning is now config-driven for loudness normalization targets (`target_lufs`, `target_true_peak`, `target_lra`).

### Fixed
- Config examples (`README.md`, `song_config.example.yaml`, and embedded example template) aligned.
- `stem_cleaner` normalization CLI now uses explicit target names with backward-compatible aliases and writes normalization settings to ffmpeg audit metadata.
