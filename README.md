# The Bandleader 🎸

**Deterministic Post-Production for AI-Generated Music Stems**

Bandleader is a rule-based Python toolkit for cleaning, re-synthesizing, and augmenting AI-generated stems (Suno, Udio, etc.).

AI generators are great at **vibe**.
They are terrible at **details**.

Bandleader fixes the details — without touching the vibe.

---

## Core Philosophy

* Keep the timing and feel.
* Replace fuzzy audio with clean deterministic layers.
* Generate harmonically safe MIDI additions.
* Produce mix-ready stems for your DAW.

No hallucinated notes.
No black box magic.
Just reproducible musical logic.

---

# What’s Included

| Command            | Purpose                                            |
| ------------------ | -------------------------------------------------- |
| `bandleader`       | Full pipeline orchestrator                         |
| `bandleader-drums` | Re-synthesize AI drum stems via MIDI transcription |
| `bandleader-stems` | Corrective EQ / compression via FFmpeg             |
| `bandleader-synth` | Transcribe + re-synthesize monophonic leads        |
| `bandleader-bass`  | Rule-based MIDI bass generation                    |
| `bandleader-arp`   | Rule-based MIDI arpeggio + pad generation          |

---

# Workflow Overview

```
Suno / Udio Stems
        │
        ├── clean_drums
        ├── clean_vocals
        ├── clean_synth (optional)
        ├── generate_bass
        ├── generate_arp
        │
        ↓
generated/
    gen_*.wav
    gen_*.mid
    preview_mix.mp3
        ↓
Import into DAW → Mix → Master
```

---

# Installation

## System Dependencies

### FFmpeg (required)

```bash
brew install ffmpeg          # macOS
sudo apt-get install ffmpeg  # Linux
```

### FluidSynth (required for MIDI rendering)

```bash
brew install fluid-synth
sudo apt-get install fluidsynth
```

---

## Install Python Package

```bash
git clone https://github.com/yourusername/bandleader.git
cd bandleader
pip install -e .
```

Optional (better drum transcription):

```bash
pip install -e ".[drums]"
```

---

## Quickstart (First Successful Run)

1. Verify external tools:
```bash
ffmpeg -version
fluidsynth --version
```
2. Create a song workspace:
```bash
mkdir -p MySong/raw_stems
cp song_config.example.yaml MySong/song_config.yaml
```
3. Edit `MySong/song_config.yaml`:
set real `.sf2` paths under `soundfonts`, and confirm stem keywords under `stems` match your filenames.
4. Put source stems in `MySong/raw_stems/` (for example files containing `drums`, `vocals`, `synth` in the names).
5. Run orchestrator:
```bash
bandleader ./MySong --verbose
```
6. Expected outputs:
generated stems in `MySong/generated/` named `gen_*.wav`, generated MIDI named `gen_*.mid`, and preview mix at `MySong/generated/preview_mix.mp3` (if ffmpeg mix step succeeds).

Troubleshooting:
1. If `bandleader` command is missing, run `pip install -e .` in the repo.
2. If dependencies are missing, install from `requirements.txt` or reinstall editable package.

---

# Configuration

Each song folder must contain:

```
song_config.yaml
```

If missing, `bandleader` will print an example config and exit.

---

## song_config.yaml (Current Format)

```yaml
song:
  bpm: 120
  time_signature: 4/4
  progression: "Am G | F | C G"
  bars: 32

stems:
  drums: "drums"
  vocals: "vocals"
  synth: "synth"
  overheads: "overheads"
  guitars: "guitars"

soundfonts:
  drums: "/path/to/drums.sf2"
  bass: "/path/to/bass.sf2"
  arp: "/path/to/arp.sf2"
  synth: "/path/to/synth.sf2"

pipeline:

  clean_drums:
    enabled: true
    use_madmom: false
    export_sidechain_trigger: false

  clean_vocals:
    enabled: true
    normalize: false
    target_lufs: -18.0
    target_true_peak: -1.5
    target_lra: 11.0

  generate_bass:
    enabled: true
    style: "two_feel"
    sidechain_ducking: false
    ducking_depth: 0.35
    ducking_attack_ms: 10.0
    ducking_release_ms: 120.0

  generate_arp:
    enabled: false
    style: "eighths"
    motion: "updown"

  phase_align:
    enabled: false
    max_shift_ms: 12.0
    min_confidence: 0.35
    pair_kick_bass: true
    pair_snare_overheads: false
    pair_bass_guitars: false

  clean_synth:
    enabled: false
```

### Important Notes

* `use_madmom: true` enables neural net drum detection (higher accuracy).
* `export_sidechain_trigger: true` exports `gen_sidechain_trigger.mid/.wav` from kick timing.
* `normalize: true` under `clean_vocals` enables LUFS normalization using configured targets.
* `sidechain_ducking: true` under `generate_bass` renders `gen_bass_ducked.wav` while preserving `gen_bass.wav`.
* Bass ducking key source priority: `gen_sidechain_trigger.wav` (if exported), else cleaned drum audio.
* `phase_align.enabled: true` turns on pair-wise time alignment and writes `generated/phase_alignment_report.json`.
* `pair_kick_bass`, `pair_snare_overheads`, and `pair_bass_guitars` are independent toggles.
* Secondary-pair alignment uses optional `stems.overheads` and `stems.guitars` keywords if provided.
* Soundfonts are defined globally under `soundfonts`, not per-step.
* Any pipeline step set to `enabled: false` is skipped entirely.
* Stems are discovered via partial filename matching (case-insensitive).
* Missing optional sections are defaulted safely (`stems`, `soundfonts`, `pipeline`).

---

# Using the Orchestrator

```bash
bandleader ./MySong
bandleader ./MySong --verbose
```

All outputs are written to:

```
MySong/generated/
```

---

# Individual Commands

You can run tools independently.

---

## Drum Cleaner

Replaces muddy AI drums with clean soundfont drums while preserving timing.

```bash
bandleader-drums drums.wav \
  --soundfont drums.sf2 \
  --tempo 120
```

Two detection modes:

* `madmom` (neural net, best)
* `basic` (librosa-based fallback)

---

## Stem Cleaner

Corrective EQ / compression via FFmpeg.

```bash
bandleader-stems vocals.wav \
  --stem vocal \
  --strength medium \
  --deess \
  --normalize
```

Writes an FFmpeg audit file alongside output.

---

## Synth Cleaner

Pitch-tracks monophonic leads using pYIN and re-renders via MIDI.

```bash
bandleader-synth lead.wav \
  --soundfont synth.sf2 \
  --preset lead
```

Best for:

* Leads
* Plucks
* Single-note bass

Not for:

* Chords
* Pads
* Polyphonic material

---

## Bass Generator

Harmonically conservative, root-based MIDI bass.

```bash
bandleader-bass \
  --progression "Am | F | C | G" \
  --style eighths \
  --bpm 120
```

Styles:

* `two_feel`
* `four_on_floor`
* `eighths`
* `disco`

---

## Arp & Pad Generator

Deterministic chord-tone arpeggios and gravity-based pad voice leading.

```bash
bandleader-arp \
  --progression "Am | F | C | G" \
  --mode pad
```

Pad mode uses chord-set voice leading to minimize movement and avoid voice crossing.

---

# Determinism Notes

`bandleader-bass` and `bandleader-arp` are deterministic when you pass an explicit `--seed`.
Use the same progression, options, and seed to reproduce identical MIDI output between runs.

Time-signature handling uses denominator-aware bar sizing:

* `4/4` = 16 grid steps per bar
* `3/4` = 12 grid steps per bar
* `6/8` = 12 grid steps per bar

---

# Folder Structure

```
MySong/
  raw_stems/
  song_config.yaml
  generated/
```

All pipeline outputs land in `generated/`.

---

# Dependencies

Installed automatically via `pip install -e .`.

Core:

* numpy
* scipy
* librosa
* mido
* pydub
* pyyaml

Optional:

* madmom (drum transcription)

System:

* FFmpeg
* FluidSynth

---

# Roadmap

See `Roadmap.md` for planned enhancements, including:

* Loudness normalization
* Phase alignment
* Groove quantization
* Drum replacement
* Section detection
* Style transfer

---

# Who This Is For

* Producers using Suno or Udio
* DAW users who want cleaner stems
* Songwriters who want deterministic MIDI layers
* Developers interested in rule-based music tooling

---

# License

MIT — free to use and modify.

See also:
1. [CONTRIBUTING.md](CONTRIBUTING.md)
2. [CHANGELOG.md](CHANGELOG.md)
3. [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)
