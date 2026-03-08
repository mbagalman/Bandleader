# Phase Alignment Design (G1)

Date: 2026-03-07
Status: Config contract defined (implementation of estimator/apply flow in G2+).

## Goal

Define a safe, deterministic contract for phase alignment so later implementation can improve coherence without destructive or surprising behavior.

## Config Contract

```yaml
pipeline:
  phase_align:
    enabled: false
    max_shift_ms: 12.0
    min_confidence: 0.35
    pair_kick_bass: true
    pair_snare_overheads: false
    pair_bass_guitars: false
```

Rules:
- `enabled` is a master toggle for the step.
- `max_shift_ms` bounds absolute time correction and must be positive.
- `min_confidence` gates apply vs skip and must be between `0.0` and `1.0`.
- Pair toggles are independent booleans.

## Pair Priority

Priority order for attempted alignment:
1. Kick -> Bass
2. Snare -> Overheads
3. Bass -> Guitars

Rationale:
- Kick/Bass has highest low-end payoff and lowest ambiguity.
- Snare/Overheads is useful but more sensitive to transient ambiguity.
- Bass/Guitars is optional and should run last to avoid compounding low-end moves too early.

## Output and Non-Destructive Policy

- Dry inputs are preserved.
- Aligned outputs use `*_aligned.wav` naming.
- Downstream preview policy should prefer aligned variants only when alignment was applied successfully.

## Skip and Fallback Guardrails

Skip alignment for a pair when any of the following is true:
- Missing source/reference file.
- Estimated lag exceeds `max_shift_ms`.
- Confidence is below `min_confidence`.
- Signal is too quiet/near-silent in analysis window.

When skipped:
- Keep dry audio unchanged.
- Record explicit skip reason in alignment reporting.
- Continue processing remaining enabled pairs.

## Determinism Requirements

- For identical inputs and config, estimator output (lag/confidence) must be stable.
- Pair processing order is fixed by priority list above.
- No random sampling in analysis windows.
