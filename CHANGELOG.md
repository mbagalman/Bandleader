# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

No unreleased changes yet.

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
