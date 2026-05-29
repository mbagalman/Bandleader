# Bandleader

**Deterministic post-production for AI-generated music stems.**

Bandleader is a rule-based Python toolkit for cleaning, re-synthesizing, and augmenting AI-generated stems from tools such as Suno, Udio, and similar music generators.

AI music generators are great at vibe. They are often much worse at details: muddy drums, uneven vocal levels, fuzzy synths, weak low end, and stems that need manual cleanup before they feel usable in a DAW.

Bandleader helps with those details without changing the musical idea. It keeps the timing and feel, then adds deterministic processing around it: cleaner drums, safer MIDI bass and arpeggio layers, optional loudness normalization, sidechain helpers, and phase-alignment checks.

## What Bandleader Does

At a high level, Bandleader takes a folder of stems plus a `song_config.yaml` file and writes cleaned or generated assets into a `generated/` folder.

```text
Suno / Udio stems
  -> clean drums
  -> clean vocals
  -> optionally clean synth
  -> optionally generate bass
  -> optionally generate arpeggio or pad
  -> optionally phase-align related stems
  -> export WAV, MIDI, reports, and preview mix
```

You can run the full orchestrator, or run the individual tools directly.

| Command | Purpose |
| --- | --- |
| `bandleader` | Full pipeline orchestrator |
| `bandleader-drums` | Re-synthesize AI drum stems from detected hits |
| `bandleader-stems` | Apply conservative corrective EQ, compression, and normalization via FFmpeg |
| `bandleader-synth` | Re-synthesize monophonic synth or lead stems |
| `bandleader-bass` | Generate deterministic MIDI bass parts from a chord progression |
| `bandleader-arp` | Generate deterministic arpeggio or pad parts from a chord progression |
| `bandleader-sidechain` | Generate sidechain trigger assets |

## Who This Is For

Bandleader is useful if you:

- Generate songs with Suno, Udio, or similar tools and want cleaner DAW-ready stems.
- Want deterministic MIDI layers instead of another black-box generation pass.
- Need repeatable post-production steps for multiple AI-generated songs.
- Are comfortable editing a small YAML config file.

It is currently a developer-friendly music production tool, not a one-click desktop app.

## Requirements

You need:

- Python 3.10 or newer
- FFmpeg
- FluidSynth
- At least one `.sf2` soundfont for rendered MIDI parts

Optional:

- `madmom` for better drum transcription

### Install System Tools

macOS:

```bash
brew install ffmpeg fluid-synth
```

Linux:

```bash
sudo apt-get install ffmpeg fluidsynth
```

Windows users can install FFmpeg and FluidSynth with the package manager or installers they prefer. Make sure both commands are available in your terminal:

```bash
ffmpeg -version
fluidsynth --version
```

## Install Bandleader

Clone the repo and install it in editable mode:

```bash
git clone https://github.com/mbagalman/Bandleader.git
cd Bandleader
pip install -e .
```

Optional drum transcription extra:

```bash
pip install -e ".[drums]"
```

If your system does not expose `pip` directly, use:

```bash
python -m pip install -e .
```

## Quickstart

Create a song workspace:

```bash
mkdir -p MySong/raw_stems
cp song_config.example.yaml MySong/song_config.yaml
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force MySong\raw_stems
Copy-Item song_config.example.yaml MySong\song_config.yaml
```

Put your source stems into `MySong/raw_stems/`. The filenames should contain the keywords from your config, such as:

```text
MySong/
  raw_stems/
    drums.wav
    vocals.wav
    synth.wav
  song_config.yaml
```

Edit `MySong/song_config.yaml`:

- Set the correct `bpm`, `time_signature`, `progression`, and `bars`.
- Set real `.sf2` paths under `soundfonts`.
- Confirm the `stems` keywords match your filenames.
- Disable any pipeline steps you do not want yet.

Run the orchestrator:

```bash
bandleader ./MySong --verbose
```

Outputs are written to:

```text
MySong/generated/
```

Typical outputs include:

- `gen_*.wav` generated or cleaned audio stems
- `gen_*.mid` generated MIDI files
- `preview_mix.mp3` if the preview mix step succeeds
- `phase_alignment_report.json` if phase alignment is enabled

## A Minimal First Config

For a first successful run, start small. Disable the optional synth, arp, and phase alignment passes until the basic path works.

```yaml
song:
  bpm: 120
  time_signature: 4/4
  progression: "Am G | F | C G"
  bars: 32

stems:
  drums: "drums"
  vocals: "vocals"

soundfonts:
  drums: "/path/to/drums.sf2"
  bass: "/path/to/bass.sf2"

pipeline:
  clean_drums:
    enabled: true
    use_madmom: false
    export_sidechain_trigger: false

  clean_vocals:
    enabled: true
    normalize: false

  generate_bass:
    enabled: true
    style: "two_feel"
    sidechain_ducking: false

  generate_arp:
    enabled: false

  phase_align:
    enabled: false

  clean_synth:
    enabled: false
```

For the full config schema, use [song_config.example.yaml](song_config.example.yaml).

## Configuration Notes

Every song folder needs a `song_config.yaml` file. If it is missing, `bandleader` prints an example config and exits.

Important config ideas:

- `song.bpm` should match the source track tempo.
- `song.progression` drives generated MIDI bass and arpeggio layers.
- `stems` values are filename keywords, not full paths.
- `soundfonts` values can be absolute paths or paths relative to the song folder.
- Any pipeline step with `enabled: false` is skipped.
- Missing optional sections are defaulted safely where possible.

### Pipeline Steps

`clean_drums`

Re-synthesizes the drum stem from detected hits. With `use_madmom: false`, Bandleader uses the default librosa-based fallback. With `use_madmom: true`, it uses the optional neural-net detector.

`clean_vocals`

Applies conservative stem cleanup. If `normalize: true`, Bandleader applies FFmpeg loudness normalization using `target_lufs`, `target_true_peak`, and `target_lra`.

`generate_bass`

Creates a deterministic MIDI bassline from the chord progression, renders it through FluidSynth, and can optionally create a sidechain-ducked version.

`generate_arp`

Creates a deterministic arpeggio or pad layer from the chord progression.

`phase_align`

Applies bounded pair-wise timing alignment and writes a report to `generated/phase_alignment_report.json`.

`clean_synth`

Pitch-tracks and re-synthesizes monophonic synth or lead material. This is best for single-note lines, not chords or pads.

## Individual Commands

You can also run tools independently.

### Drum Cleaner

```bash
bandleader-drums drums.wav \
  --soundfont drums.sf2 \
  --tempo 120
```

### Stem Cleaner

```bash
bandleader-stems vocals.wav \
  --stem vocal \
  --strength medium \
  --deess \
  --normalize
```

### Synth Cleaner

```bash
bandleader-synth lead.wav \
  --soundfont synth.sf2 \
  --preset lead
```

Best for leads, plucks, and simple monophonic parts. Not recommended for chords, pads, or polyphonic material.

### Bass Generator

```bash
bandleader-bass \
  --progression "Am | F | C | G" \
  --style eighths \
  --bpm 120
```

Supported styles include `two_feel`, `four_on_floor`, `eighths`, and `disco`.

### Arp and Pad Generator

```bash
bandleader-arp \
  --progression "Am | F | C | G" \
  --mode pad
```

Pad mode uses chord-set voice leading to minimize movement and avoid voice crossing.

## Determinism

`bandleader-bass` and `bandleader-arp` are deterministic when you pass an explicit `--seed`.

Use the same progression, options, and seed to reproduce the same MIDI output between runs.

Time-signature handling uses denominator-aware bar sizing:

- `4/4` = 16 grid steps per bar
- `3/4` = 12 grid steps per bar
- `6/8` = 12 grid steps per bar

## Troubleshooting

`bandleader` command is missing:

Run `pip install -e .` from the repo root, or use `python -m pip install -e .`.

FFmpeg or FluidSynth is missing:

Install the system tool and confirm `ffmpeg -version` and `fluidsynth --version` work in the same terminal.

Bandleader cannot find a stem:

Check the `stems` keywords in `song_config.yaml`. A value such as `"drums"` matches filenames containing `drums`, case-insensitively.

A soundfont path fails:

Use an absolute `.sf2` path first. Once that works, you can switch to paths relative to the song folder.

The synth cleaner sounds wrong:

Use it only on monophonic material. Polyphonic pads and chords are outside its intended scope.

## Project Docs

- [Roadmap](docs/roadmap.md)
- [Release checklist](docs/release-checklist.md)
- [Development workboard](docs/workboard.md)
- [Contributing guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).
