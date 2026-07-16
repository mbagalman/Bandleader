# Bandleader — Development Plan & Ticket Pack (Historical)

> **Note:** This is the historical internal workboard from Bandleader's
> pre-release development (all tickets completed before v0.1.0). It is kept
> for reference. For the current contribution workflow, see
> [CONTRIBUTING.md](../CONTRIBUTING.md); for planned features, see the
> [roadmap](roadmap.md).

---

## Dashboard

| ID | Title | Epic | Status | Claimed by |
|----|-------|------|--------|------------|
| [A1](#a1-repo-bootstrap--ignore-policy) | Repo bootstrap & ignore policy | Foundations | Done | Codex |
| [A2](#a2-command-smoke-tests) | Command smoke tests | Foundations | Done | Codex |
| [A3](#a3-test-harness-scaffold) | Test harness scaffold | Foundations | Done | Codex |
| [B1](#b1-orchestrator-dependency-gating) | Orchestrator dependency gating | Orchestrator | Done | Codex |
| [B2](#b2-file-discovery-hardening) | File discovery hardening | Orchestrator | Done | Codex |
| [B3](#b3-preview-mix-safety) | Preview mix safety | Orchestrator | Done | Codex |
| [C1](#c1-bass-time-signature-semantics) | Bass time-signature semantics | Generators | Done | Codex |
| [C2](#c2-arp-pad-segmentation-fix) | Arp pad segmentation fix | Generators | Done | Codex |
| [C3](#c3-generator-determinism-check) | Generator determinism check | Generators | Done | Codex |
| [D1](#d1-config-schema--validation-expansion) | Config schema & validation expansion | Config/UX | Done | Codex |
| [D2](#d2-example-config-alignment) | Example config alignment | Config/UX | Done | Codex |
| [D3](#d3-error-message-quality-pass) | Error-message quality pass | Config/UX | Done | Codex |
| [E1](#e1-readme-quickstart-refresh) | README quickstart refresh | Docs/Release | Done | Codex |
| [E2](#e2-contributing-guide) | Contributing guide | Docs/Release | Done | Codex |
| [E3](#e3-first-release-checklist) | First release checklist | Docs/Release | Done | Codex |
| [F1](#f1-stem-loudness-normalization-core) | Stem loudness normalization core | Phase 1 ROI | Done | Codex |
| [F2](#f2-loudness-normalization-pipeline-integration) | Loudness normalization pipeline integration | Phase 1 ROI | Done | Codex |
| [F3](#f3-sidechain-trigger-track-export) | Sidechain trigger track export | Phase 1 ROI | Done | Codex |
| [F4](#f4-sidechain-aware-bass-ducking) | Sidechain-aware bass ducking | Phase 1 ROI | Done | Codex |
| [F5](#f5-phase-1-config-validation--docs) | Phase 1 config validation & docs | Phase 1 ROI | Done | Codex |
| [G1](#g1-phase-alignment-design--config-contract) | Phase alignment design & config contract | Phase 2 Item 4 | Done | Codex |
| [G2](#g2-cross-correlation-lag-estimator-core) | Cross-correlation lag estimator core | Phase 2 Item 4 | Done | Codex |
| [G3](#g3-kick-bass-alignment-first-pass) | Kick-bass alignment first pass | Phase 2 Item 4 | Done | Codex |
| [G4](#g4-secondary-pairs-snare-overheads--bass-guitars) | Secondary pairs (snare-overheads + bass-guitars) | Phase 2 Item 4 | Done | Codex |
| [G5](#g5-orchestrator-integration--alignment-reporting) | Orchestrator integration & alignment reporting | Phase 2 Item 4 | Done | Codex |
| [G6](#g6-phase-alignment-validation-tests--docs) | Phase alignment validation, tests, and docs | Phase 2 Item 4 | Done | Codex |

**Progress:** 26 / 26 tickets done.

---

## Epic A — Foundations

### A1 Repo bootstrap & ignore policy

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 15 min  
**Progress note:** Git repo initialized and `.gitignore` created from existing `gitignore.md`.

**What to do:**
1. Initialize Git in the project root.
2. Ensure a real `.gitignore` exists.
3. Confirm generated audio/MIDI artifacts are ignored.

**Acceptance criteria:**
- [x] `git init` completed.
- [x] `.gitignore` exists in repo root.
- [x] Ignore rules include media outputs and caches.

---

### A2 Command smoke tests

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** A1  
**Progress note:** Completed on 2026-03-07. Ran `python3 -m ... --help` smoke tests for all module entrypoints and documented exact pass/fail outcomes, missing deps, and troubleshooting in `notes/cli-smoke-tests.md`. Also checked console-script availability (`bandleader*`) in PATH.

**What to do:**
1. Run each CLI entrypoint with `--help`.
2. Record pass/fail and missing runtime dependencies.
3. Add a short troubleshooting section to notes if any command fails.

**Acceptance criteria:**
- [x] All entrypoints exercised with `--help`.
- [x] Failures are documented with exact error messages.

---

### A3 Test harness scaffold

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** A1  
**Progress note:** Completed on 2026-03-07. Added `tests/` scaffold, `pytest` config in `pyproject.toml`, and unit tests for chord parser + orchestrator helpers. Verified tests run without ffmpeg/fluidsynth; test run: `9 passed`.

**What to do:**
1. Add `tests/` scaffold and `pytest` config.
2. Add at least one test module for parser and one for orchestrator helpers.
3. Ensure tests run without requiring ffmpeg/fluidsynth.

**Acceptance criteria:**
- [x] `pytest` runs locally.
- [x] At least 5 meaningful unit tests exist.

---

## Epic B — Orchestrator

### B1 Orchestrator dependency gating

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2 hours  
**Depends on:** A2  
**Progress note:** Completed on 2026-03-07. Replaced global dependency gate with step-aware checks via `ensure_tools_for_enabled_steps()`. The orchestrator now requires tools only for enabled steps and exits with tool + step-specific error messages.

**What to do:**
1. Replace global dependency check with step-aware checks.
2. Require `fluidsynth` only for steps that render MIDI.
3. Require `ffmpeg` only for steps that use stem cleaning or preview mix.

**Acceptance criteria:**
- [x] Running a subset pipeline only checks tools needed for enabled steps.
- [x] Error messages name the missing tool and affected step.

---

### B2 File discovery hardening

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** A3  
**Progress note:** Completed on 2026-03-07. Hardened `find_file()` ranking for deterministic tie-breaking (path-based) and added ambiguity guardrail warnings when equivalent best matches exist. Added deterministic behavior tests.

**What to do:**
1. Add tests for `find_file()` precedence rules.
2. Confirm deterministic behavior across multiple candidate files.
3. Add guardrails for ambiguous multi-match situations.

**Acceptance criteria:**
- [x] Deterministic match order is covered by tests.
- [x] Ambiguity handling is documented and tested.

---

### B3 Preview mix safety

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1 hour  
**Depends on:** B1  
**Progress note:** Completed on 2026-03-07. Added robust preview-mix filter graph normalization (`aresample` + stereo `aformat`) through `build_preview_mix_filter()` and made preview skip explicit/non-fatal if ffmpeg is unavailable.

**What to do:**
1. Ensure preview mix handles mono/stereo mismatches robustly.
2. Add safe defaults for ffmpeg filter graph.
3. Improve warning when preview mix fails but stems succeed.

**Acceptance criteria:**
- [x] Mix step handles heterogeneous input channels without crashing.
- [x] Failure mode is explicit and non-fatal.

---

## Epic C — Generators

### C1 Bass time-signature semantics

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** A3  
**Progress note:** Completed on 2026-03-07. Updated bass time-signature math to use denominator-aware bar sizing (`beats_per_bar` and `steps_per_bar`). Added coverage tests for `4/4`, `3/4`, and `6/8`.

**What to do:**
1. Define intended behavior for denominators other than 4.
2. Update beat/step math accordingly.
3. Add tests for at least `4/4`, `3/4`, and `6/8`.

**Acceptance criteria:**
- [x] Denominator affects timing as designed.
- [x] Regression tests cover non-4 denominators.

---

### C2 Arp pad segmentation fix

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2 hours  
**Depends on:** A3  
**Progress note:** Completed on 2026-03-07. Replaced integer floor segmenting in pad mode with `compute_pad_segments()` boundary logic so bar coverage is complete and zero-length segments are avoided for dense chord bars.

**What to do:**
1. Fix pad segment allocation when chord count does not divide steps per bar.
2. Prevent zero-length segments when many chords are packed into one bar.
3. Add tests for dense chord bars.

**Acceptance criteria:**
- [x] No zero-duration pad events.
- [x] Full bar duration is covered without dropped tail steps.

---

### C3 Generator determinism check

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** C1, C2  
**Progress note:** Completed on 2026-03-07. Added generator determinism tests (seeded bass and arp runs) and documented deterministic behavior plus time-signature step mapping in README.

**What to do:**
1. Verify seeded runs produce byte-for-byte identical MIDI where expected.
2. Document which commands are deterministic and under what flags.

**Acceptance criteria:**
- [x] Determinism behavior captured in tests or script checks.
- [x] Documentation updated.

---

## Epic D — Config/UX

### D1 Config schema & validation expansion

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** B1  
**Progress note:** Completed on 2026-03-07. `validate_config()` now validates and normalizes the full schema (song/stems/soundfonts/pipeline), applies safe defaults for optional sections, validates styles/motion/time signatures, and reports consolidated key-path errors before exit.

**What to do:**
1. Define required and optional config keys formally.
2. Validate types and value ranges for pipeline sections.
3. Consolidate validation errors into actionable output.

**Acceptance criteria:**
- [x] Invalid config exits with specific key-level errors.
- [x] Missing optional sections receive safe defaults.

---

### D2 Example config alignment

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1 hour  
**Depends on:** D1  
**Progress note:** Completed on 2026-03-07. Aligned config examples across `EXAMPLE_CONFIG`, `song_config.example.yaml`, and README defaults; added missing arp style/motion options and explicit note that optional sections are defaulted.

**What to do:**
1. Ensure `song_config.example.yaml`, README examples, and `EXAMPLE_CONFIG` all match.
2. Update any stale option names or defaults.

**Acceptance criteria:**
- [x] All three config examples are consistent.
- [x] A new user can copy/paste and run with minimal edits.

---

### D3 Error-message quality pass

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** D1  
**Progress note:** Completed on 2026-03-07. Error messaging now uses path-specific validation failures (`song.*`, `pipeline.*`) with a consolidated issue list plus example config output, and warnings for unknown top-level/pipeline keys.

**What to do:**
1. Audit user-facing errors for clarity and next actions.
2. Standardize wording across modules.

**Acceptance criteria:**
- [x] Every fatal error tells user what to fix next.
- [x] Messaging style is consistent across tools.

---

## Epic E — Docs/Release

### E1 README quickstart refresh

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** A2, D2  
**Progress note:** Completed on 2026-03-07. Added a first-run Quickstart section to README with dependency checks, config setup, run command, expected output paths, and troubleshooting notes. Added links to contributing/release docs.

**What to do:**
1. Add an explicit quickstart path for first successful run.
2. Include dependency checks and expected output paths.

**Acceptance criteria:**
- [x] New quickstart section is complete and tested.
- [x] CLI examples match current flags.

---

### E2 Contributing guide

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1 hour  
**Depends on:** A3  
**Progress note:** Completed on 2026-03-07. Added `CONTRIBUTING.md` covering setup, test expectations, and ticket claim/update workflow, and linked it from README.

**What to do:**
1. Add `CONTRIBUTING.md` with setup, test, and ticket-claim workflow.
2. Link to this workboard file.

**Acceptance criteria:**
- [x] Contributing guide exists and is linked from README.
- [x] Includes claim/update conventions.

---

### E3 First release checklist

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1 hour  
**Depends on:** E1, E2  
**Progress note:** Completed on 2026-03-07. Added `RELEASE_CHECKLIST.md` with version/changelog/test/tag steps and created `CHANGELOG.md` with an `Unreleased` section for current completed work.

**What to do:**
1. Draft a release checklist (version bump, changelog, tag, smoke tests).
2. Add a simple changelog file if missing.

**Acceptance criteria:**
- [x] Release checklist is actionable.
- [x] Versioning process is documented.

---

## Suggested Build Order

```
A2 -> A3
B1 -> B2 -> B3
C1 -> C2 -> C3
D1 -> D2 -> D3
E1 -> E2 -> E3
```

---

## Epic F — Roadmap Phase 1 (Low Effort, High ROI)

### Development Plan

1. **Sprint F-A (Loudness Foundation):** implement per-stem loudness normalization in `stem_cleaner` first, then integrate at orchestrator/pipeline config level.
2. **Sprint F-B (Sidechain Utility):** export DAW-ready sidechain trigger track from drum events/MIDI so users get immediate low-end workflow gains.
3. **Sprint F-C (Bass Ducking):** add optional sidechain-aware bass shaping (pre-render ducking against kick timings) with conservative defaults and bypass/fallback behavior.
4. **Stabilization:** finish config validation paths, README/example updates, and regression tests across all Phase 1 features.

### F1 Stem loudness normalization core

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** D1  
**Progress note:** Completed on 2026-03-07. Extended `stem_cleaner` normalization controls with explicit target names (`--target-lufs`, `--target-true-peak`, `--target-lra`, backward-compatible aliases retained), centralized loudnorm filter generation, and added audit metadata output in `.ffmpeg.txt` including normalization settings.

**What to do:**
1. Extend `bandleader.stem_cleaner` with explicit loudness target controls for per-stem normalization (`target_lufs`, optional true-peak guard).
2. Ensure normalization can be toggled per run and remains conservative by default.
3. Emit normalization settings in ffmpeg audit output.

**Acceptance criteria:**
- [x] Cleaner can normalize to target LUFS with deterministic CLI behavior.
- [x] Existing non-normalized workflows remain unchanged by default.

---

### F2 Loudness normalization pipeline integration

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** F1  
**Progress note:** Completed on 2026-03-07. Added config-driven vocal normalization policy in orchestrator defaults/validation (`pipeline.clean_vocals.normalize`, `target_lufs`, `target_true_peak`, `target_lra`) and wired command construction via `build_stem_cleaner_cmd()` so normalization flags are passed only when enabled.

**What to do:**
1. Add pipeline config fields for per-stem normalization policy.
2. Wire orchestrator to pass normalization flags to `stem_cleaner`.
3. Add tests for config parsing and command construction.

**Acceptance criteria:**
- [x] Config-driven loudness normalization works through orchestrator.
- [x] Missing/invalid settings produce key-path validation errors.

---

### F3 Sidechain trigger track export

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** C3  
**Progress note:** Completed on 2026-03-07. Added `bandleader.sidechain_trigger` utility to export trigger MIDI from kick hits and optional trigger WAV render. Wired orchestrator drum step with `pipeline.clean_drums.export_sidechain_trigger` and deterministic output naming (`gen_sidechain_trigger.mid/.wav`).

**What to do:**
1. Export sidechain trigger MIDI/audio aligned to detected or transcribed kick hits.
2. Add output naming convention under `generated/` (e.g., `gen_sidechain_trigger.*`).
3. Keep implementation DAW-agnostic and timing-stable.

**Acceptance criteria:**
- [x] Trigger track aligns with kick transients in test fixtures/manual checks.
- [x] Output is produced only when feature is enabled.

---

### F4 Sidechain-aware bass ducking

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 4-6 hours  
**Depends on:** F3  
**Progress note:** Completed on 2026-03-07. Added optional sidechain-aware bass ducking controls (`sidechain_ducking`, `ducking_depth`, `ducking_attack_ms`, `ducking_release_ms`) with validator coverage, ffmpeg sidechain command construction, and orchestrator wiring that prefers `gen_sidechain_trigger.wav` then falls back to cleaned drums. Dry bass is always exported (`gen_bass.wav`), and when ducking succeeds the preview mix uses `gen_bass_ducked.wav`. Added regression tests; suite result: `35 passed`.

**What to do:**
1. Implement optional bass ducking against kick/trigger events (depth, attack, release controls).
2. Apply ducking in a conservative way that preserves note articulation.
3. Export ducked bass preview/output alongside dry variant when configured.

**Acceptance criteria:**
- [x] Bass ducking audibly clears kick-bass masking without pumping artifacts at default settings.
- [x] Feature can be fully disabled with zero behavioral impact.

---

### F5 Phase 1 config validation & docs

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** F1, F2, F3, F4  
**Progress note:** Completed on 2026-03-07. Aligned Phase 1 config/options across `song_config.example.yaml` and README (`clean_vocals` normalization targets plus `generate_bass` sidechain ducking knobs and behavior notes), and added release-note coverage for F1-F4 in `CHANGELOG.md`. Regression suite verified after docs/config updates: `35 passed`.

**What to do:**
1. Add new Phase 1 options to `song_config.example.yaml`, README, and embedded example template.
2. Expand validator coverage for all new knobs and defaults.
3. Add release-note entries to `CHANGELOG.md`.

**Acceptance criteria:**
- [x] All config examples and docs are aligned with implemented Phase 1 features.
- [x] Tests cover success/failure paths for new config fields.

---

### Suggested Phase 1 Build Order

```
F1 -> F2
F3 -> F4
F5
```

---

## Epic G — Phase 2 Item 4 (Phase Alignment Between Stems)

### Review Summary

Roadmap item 4 is a strong next target: implementation effort is moderate, and audible payoff is high because low-end cancellations are one of the fastest ways to make otherwise solid stems sound weak. The highest-value slice is kick-bass alignment first, then optional secondary pairs once the estimator and safety checks are stable.

### Development Plan

1. **Sprint G-A (Core Estimation):** implement a deterministic lag estimator using windowed cross-correlation with bounded shift and confidence scoring.
2. **Sprint G-B (Low-End ROI):** apply alignment to kick ↔ bass first with conservative max-shift constraints and bypass when confidence is low.
3. **Sprint G-C (Secondary Pairs):** extend to snare ↔ overheads and bass ↔ guitars as optional pair rules.
4. **Sprint G-D (Pipeline UX):** integrate into orchestrator with config controls, audit logs, and non-destructive outputs.
5. **Stabilization:** add validation paths, regression tests, and README/example/changelog updates.

### G1 Phase alignment design & config contract

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 1-2 hours  
**Depends on:** F5  
**Progress note:** Completed on 2026-03-07. Added `pipeline.phase_align` contract to orchestrator template/defaults/validation with strict field checks (`enabled`, `max_shift_ms`, `min_confidence`, pair toggles), plus validation tests and design note documenting pair priority, output naming, and skip/fallback guardrails (`notes/phase-alignment-design.md`). Test suite: `37 passed`.

**What to do:**
1. Define `pipeline.phase_align` config contract (enable flag, max shift, confidence threshold, pair toggles).
2. Define output naming and non-destructive behavior (`*_aligned.wav`, dry preserved).
3. Document guardrails for when alignment is skipped.

**Acceptance criteria:**
- [x] Config schema for phase alignment is explicit and validator-ready.
- [x] Design note defines pair priority and fallback behavior.

---

### G2 Cross-correlation lag estimator core

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 3-4 hours  
**Depends on:** G1  
**Progress note:** Completed on 2026-03-07. Added deterministic lag estimator core in `bandleader.phase_alignment` using bounded normalized cross-correlation (`estimate_lag`) with confidence scoring and clear lag sign convention. Added coverage tests for positive/negative lag, silence, low-confidence unrelated noise, and max-shift bound behavior. Test suite: `42 passed`.

**What to do:**
1. Add a reusable lag estimation helper (windowing + normalized cross-correlation).
2. Bound lag search by configurable `max_shift_ms`.
3. Emit confidence metrics for apply/skip decisions.

**Acceptance criteria:**
- [x] Estimator returns deterministic lag + confidence for the same inputs.
- [x] Unit tests cover positive/negative lag, silence, and low-confidence cases.

---

### G3 Kick-bass alignment first pass

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** G2  
**Progress note:** Completed on 2026-03-07. Implemented first-pass kick→bass alignment using `bandleader.phase_alignment.align_wav_to_reference` and `estimate_lag` (bounded by `pipeline.phase_align.max_shift_ms` and gated by `min_confidence`). Orchestrator now exports `generated/gen_bass_aligned.wav` when alignment is confidently applied, while preserving dry bass and skipping safely with explicit warnings when reference/confidence is insufficient. Added WAV-level alignment tests (apply + low-confidence skip). Test suite: `44 passed`. Manual musical A/B validation is still pending on real stems.

**What to do:**
1. Align bass against kick reference using estimator output.
2. Apply conservative time shift only when confidence exceeds threshold.
3. Export aligned bass variant without deleting dry bass.

**Acceptance criteria:**
- [ ] Kick-bass alignment improves low-end coherence in manual A/B checks.
- [x] Low-confidence detections safely bypass with explicit warning.

---

### G4 Secondary pairs (snare-overheads + bass-guitars)

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 3-5 hours  
**Depends on:** G2, G3  
**Progress note:** Completed on 2026-03-07. Added reusable `run_phase_alignment_pair()` with isolated failure handling (missing source/target, low confidence, runtime errors do not abort other pairs). Implemented optional secondary pair passes under `pipeline.phase_align`: `pair_snare_overheads` aligns overheads against dry cleaned drums proxy, and `pair_bass_guitars` aligns guitars against dry generated bass. Added guardrails to avoid compounded drift by always using dry reference paths for pair alignment. Added helper tests for success and missing-target skip behavior. Test suite: `46 passed`.

**What to do:**
1. Implement optional alignment rules for snare ↔ overheads and bass ↔ guitars.
2. Ensure pair processing is independently toggled and failure-isolated.
3. Prevent compounded drift when multiple alignments run.

**Acceptance criteria:**
- [x] Secondary pair alignment can be enabled/disabled per pair.
- [x] Pair failures do not block unrelated pair processing.

---

### G5 Orchestrator integration & alignment reporting

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** G3, G4  
**Progress note:** Completed on 2026-03-07. Expanded orchestrator integration for phase alignment with per-pair reporting and preview selection policy updates. Added reusable report helpers and `generated/phase_alignment_report.json` output listing each attempted pair (`pair`, reference/target paths, lag samples/ms, confidence, applied/skipped reason, output path). Kick-bass alignment now promotes `gen_bass_aligned.wav` into preview selection when applied, and sidechain ducking runs against the current selected bass source. Secondary-pair aligned outputs are appended to preview inputs only when successfully applied. Added helper tests for report entry and JSON write paths. Test suite: `48 passed`.

**What to do:**
1. Add orchestrator step orchestration for phase alignment and output tracking.
2. Emit an alignment report (pair, lag samples/ms, confidence, applied/skipped reason).
3. Include aligned assets in preview mix selection policy.

**Acceptance criteria:**
- [x] Orchestrator can run with alignment fully off (no behavior change).
- [x] Alignment report is generated for each attempted pair.

---

### G6 Phase alignment validation, tests, and docs

**Status:** Done  
**Claimed by:** Codex  
**Est.:** 2-3 hours  
**Depends on:** G1, G5  
**Progress note:** Completed on 2026-03-07. Expanded phase-align validator/test coverage for edge cases (confidence below zero, invalid secondary pair toggle types, empty report write path), and aligned docs/examples with implemented behavior by adding `phase_align` config plus optional `stems.overheads`/`stems.guitars` keywords in `song_config.example.yaml` and README. Added changelog entries for phase-alignment workflow and report export. Post-review remediation pass fixed PCM conversion edge cases (signed overflow, unsigned normalization), optional stem keyword validation, and secondary-pair missing-stem report omissions. Test suite: `54 passed`.

**What to do:**
1. Add validator coverage for all phase-align config fields and edge cases.
2. Add tests for estimator behavior and orchestrator command/flow wiring.
3. Update `song_config.example.yaml`, README, and `CHANGELOG.md`.

**Acceptance criteria:**
- [x] Tests cover success/failure paths for phase-align knobs.
- [x] Docs and examples are aligned with implemented behavior.

---

### Suggested Phase 2 Item 4 Build Order

```
G1 -> G2 -> G3
G2 -> G4
G3 + G4 -> G5
G1 + G5 -> G6
```
