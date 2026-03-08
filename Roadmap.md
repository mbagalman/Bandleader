# AI Stem Post-Production Pipeline

## Development Roadmap for Audio Quality & Musical Coherence

### Purpose

This roadmap outlines a prioritized development plan for enhancing an AI-assisted music production pipeline. The pipeline ingests generated stems (e.g., drums, vocals, synths), performs cleanup and enhancement, optionally generates musical layers (bass, arpeggios), and exports mix-ready assets for a DAW.

The roadmap is prioritized:

1. **By implementation effort (low → very high)**
2. **Within each effort tier, by audible impact (high → low)**

This ensures early work yields the largest improvement in final song quality.

---

# Priority Scale

### Effort (Code Complexity)

* **Low** — straightforward DSP or metadata tasks
* **Medium** — moderate signal processing or musical logic
* **High** — complex DSP, analysis, or multi-stage workflows
* **Very High** — advanced ML/audio inference or research-level problems

### Impact (Audible Improvement)

* **Medium** — noticeable improvement
* **High** — major improvement in clarity or cohesion
* **Very High** — transformative improvement to perceived production quality

---

# Phase 1 — Low Effort, High Impact (Quick Wins)

These features deliver immediate improvements with minimal engineering cost.
**Status (as of 2026-03-07):** Complete in Bandleader (`F1`-`F5` done).

## 1. Loudness Normalization (Per Stem)

**Impact:** High
**Why it matters:** AI stems often have inconsistent levels, making mixes muddy or unbalanced.

**Feature:**

* Normalize stems to target LUFS (e.g., −18 LUFS)
* Maintain headroom for mixing

**Benefits:**

* Faster DAW workflow
* Prevents clipping and level mismatch

---

## 2. Sidechain Trigger Track Export

**Impact:** High
**Why it matters:** Modern mixes rely on sidechain compression for clarity (kick vs bass).

**Feature:**

* Export a silent trigger track aligned to kick hits
* DAWs can use this for sidechain compression

**Benefits:**

* Professional low-end clarity
* No manual trigger setup

---

## 3. Sidechain-Aware Bass Shaping

**Impact:** High
**Why it matters:** Bass masking kick is a common issue.

**Feature:**

* Duck bass amplitude at detected kick transients
* Optional export of pre-ducked bass

**Benefits:**

* Clean low end
* Modern EDM/pop compatibility

---

# Phase 2 — Medium Effort, High Impact

These features significantly improve musicality and mix clarity.

## 4. Phase Alignment Between Stems

**Impact:** Very High
**Why it matters:** Phase misalignment causes weak bass and thin drums.

**Feature:**

* Cross-correlation alignment between:

  * Kick ↔ bass
  * Snare ↔ overheads
  * Bass ↔ guitars

**Benefits:**

* Punchier low end
* Fuller mix

---

## 5. Voice-Leading in Bass Generation

**Impact:** High
**Why it matters:** Bass lines feel artificial without smooth note transitions.

**Feature:**

* Prefer stepwise motion
* Minimize large jumps between notes

**Benefits:**

* More natural bass lines
* Improved musical coherence

---

## 6. Style-Aware Bass Patterns

**Impact:** High
**Why it matters:** Generic patterns reduce genre authenticity.

**Feature:**

* Pattern templates by style:

  * Rock: root–fifth–octave
  * Funk: syncopation
  * Pop: passing tones
  * EDM: sustained notes

**Benefits:**

* Genre realism
* More engaging rhythm

---

## 7. Dynamic Intensity Shaping by Section

**Impact:** High
**Why it matters:** Songs feel static without dynamic variation.

**Feature:**

* Adjust layer density by section:

  * Verse: sparse
  * Chorus: full
  * Bridge: contrast

**Benefits:**

* Emotional arc
* Professional arrangement feel

---

## 8. Automatic EQ Carving

**Impact:** High
**Why it matters:** Frequency clashes create muddiness.

**Feature:**

* High-pass non-bass instruments
* Reduce 200–400 Hz mud
* Tame harshness at 3–5 kHz

**Benefits:**

* Clearer mix
* Less DAW cleanup

---

## 9. Transient Shaping for Drums

**Impact:** High
**Why it matters:** AI drums often lack punch.

**Feature:**

* Enhance attack on kick/snare
* Reduce sustain for tightness

**Benefits:**

* More realistic drums
* Improved groove

---

## 10. Stereo Field Management

**Impact:** Medium–High
**Why it matters:** Poor stereo balance reduces perceived quality.

**Feature:**

* Monoize sub frequencies (<120 Hz)
* Widen pads and synths

**Benefits:**

* Professional stereo image
* Better translation to playback systems

---

## 11. Automatic Key Detection Fallback

**Impact:** Medium
**Why it matters:** Incorrect keys cause wrong generated notes.

**Feature:**

* Detect key from stems using chroma analysis
* Warn on mismatch

**Benefits:**

* Prevents harmonic errors
* Improves reliability

---

# Phase 3 — High Effort, Very High Impact

These features bring the pipeline closer to professional production tools.

## 12. Groove Quantization (Humanized)

**Impact:** Very High
**Why it matters:** AI timing drift sounds unprofessional.

**Feature:**

* Detect beat grid
* Apply groove-preserving quantization
* Modes: tight / human / loose

**Benefits:**

* Tight rhythm
* Retains natural feel

---

## 13. Drum Replacement / Augmentation

**Impact:** Very High
**Why it matters:** AI drums often sound synthetic.

**Feature:**

* Detect kick/snare hits
* Layer high-quality samples

**Benefits:**

* Radio-ready drums
* Genre authenticity

---

## 14. Noise Floor Reduction

**Impact:** High
**Why it matters:** AI stems contain artifacts and noise.

**Feature:**

* Spectral gating
* Adaptive noise reduction

**Benefits:**

* Cleaner stems
* Professional polish

---

## 15. Section Detection (Verse/Chorus/Bridge)

**Impact:** High
**Why it matters:** Enables intelligent arrangement decisions.

**Feature:**

* Detect structural changes in energy and harmony
* Export section markers

**Benefits:**

* Arrangement automation
* DAW marker generation

---

## 16. DAW-Ready Session Export

**Impact:** Medium–High
**Why it matters:** Streamlines workflow.

**Feature:**

* Export tempo map
* Export markers
* Standardized naming

**Benefits:**

* Faster mixing
* Professional handoff

---

# Phase 4 — Very High Effort, Transformational Impact

These are advanced features that could differentiate the pipeline from existing tools.

## 17. Chord Inference from Audio

**Impact:** Very High
**Why it matters:** Eliminates manual chord entry.

**Feature:**

* Detect chords from harmony stem
* Generate MIDI layers automatically

**Benefits:**

* Fully automated workflow
* Greater musical accuracy

---

## 18. Artifact Detection & Repair

**Impact:** High–Very High
**Why it matters:** AI artifacts reduce perceived quality.

**Feature:**

* Detect warbling, metallic textures, clipping
* Apply corrective processing

**Benefits:**

* Cleaner, more natural sound
* Increased listener trust

---

## 19. Stem Style Transfer

**Impact:** Very High
**Why it matters:** Enables creative sound design.

**Feature:**

* Transform drum or instrument tone to match target style

**Benefits:**

* Unique sonic identity
* Competitive differentiation

---

# Recommended Development Order

## Phase 1 (Immediate ROI)

1. Loudness normalization
2. Sidechain trigger export
3. Sidechain-aware bass shaping

## Phase 2 (Musical polish)

4. Phase alignment
5. Voice-leading bass
6. Style-aware bass
7. Dynamic intensity shaping
8. Automatic EQ carving
9. Transient shaping
10. Stereo management
11. Key detection fallback

## Phase 3 (Professional production)

12. Groove quantization
13. Drum replacement
14. Noise reduction
15. Section detection
16. DAW export

## Phase 4 (Advanced differentiation)

17. Chord inference
18. Artifact repair
19. Style transfer

---

# Strategic Vision

This roadmap evolves the pipeline from a **utility for cleaning AI stems** into a **production-grade post-AI music engine** that:

* Restores realism to generated audio
* Enhances musical coherence
* Automates arrangement intelligence
* Produces mix-ready assets

The long-term opportunity is significant: most generative music tools stop at creation. The real value lies in making that output sound like a finished record.
