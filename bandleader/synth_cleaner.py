"""
Synth Transcription and Re-synthesis Tool v2.0

Changelog (v2.0):
- PACKAGE: Moved into bandleader package.
- FEATURE: Added --preset lead|bass|pluck with sensible fmin/fmax/gate/smoothing defaults
  per preset. Explicit CLI flags override preset values (preset is a default, not a lock).
- LOGGING: Replaced print() with Python logging. Use --verbose / -v for debug output.

v1.1:
- FIX: warn_if_likely_polyphonic() was passing multiple strings as separate positional
  arguments to print(), causing each fragment to appear on its own line with extra spacing.
  Now uses a single string with explicit newline characters for clean output.

This script takes a "fuzzy" monophonic synth track (WAV or MP3) and creates a clean version by:
1) Transcribing the pitch contour (what notes are played and when)
2) Generating a MIDI file from the transcription
3) Rendering the MIDI file with a clean synth soundfont using FluidSynth

Key Features:
- RMS Gating: Ignores reverb tails and noise that confuse pitch trackers
- Median Filtering: Smooths out single-frame octave errors and glitches
- Robust Segmentation: Handles vibrato and pitch bends without note stuttering
- Automatic fallback if initial settings are too aggressive

IMPORTANT: This tool is designed for MONOPHONIC (single-note) synth lines only.

Requirements:
    pip install numpy librosa mido pydub

FluidSynth must be installed:
    - macOS: brew install fluid-synth
    - Linux: apt-get install fluidsynth
    - Windows: https://github.com/FluidSynth/fluidsynth/releases

You also need a soundfont (.sf2). Many GM soundfonts include decent synth patches.
"""

import logging
import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

log = logging.getLogger(__name__)

# Optional conversion for MP3/etc.
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

SYNTH_PRESETS = {
    "lead": dict(
        fmin=130.0,   # C3 — typical lead synth low end
        fmax=2093.0,  # C7 — typical lead synth high end
        rms_gate_db=-28.0,
        pitch_smoothing=0.05,
    ),
    "bass": dict(
        fmin=41.0,    # E1 — bass synth fundamental
        fmax=400.0,   # ~G4 — bass synth rarely goes higher
        rms_gate_db=-32.0,
        pitch_smoothing=0.08,
    ),
    "pluck": dict(
        fmin=130.0,   # C3
        fmax=4186.0,  # C8 — pluck/guitar-style can reach very high harmonics
        rms_gate_db=-24.0,
        pitch_smoothing=0.02,  # Less smoothing preserves the pluck attack transient
    ),
}


def convert_to_wav(input_file: str) -> str:
    """
    Convert MP3 or other formats to WAV if needed.
    Returns a path to a WAV file (may be original file if already WAV).
    """
    input_path = Path(input_file)

    if input_path.suffix.lower() == ".wav":
        return str(input_path)

    if not PYDUB_AVAILABLE:
        log.warning(
            "Cannot convert %s to WAV without pydub. Proceeding with original file: %s",
            input_path.suffix, input_file
        )
        return str(input_path)

    log.info("Converting %s to WAV...", input_file)
    audio = AudioSegment.from_file(input_file)
    wav_path = input_path.with_suffix(".temp.wav")
    audio.export(wav_path, format="wav")
    log.info("Converted to %s", wav_path)
    return str(wav_path)


def estimate_tempo_bpm(audio_file: str) -> float:
    """
    Estimate tempo using librosa. On stems this can be half/double-time.
    Used only if user requests tempo estimation.
    """
    if not LIBROSA_AVAILABLE:
        raise ImportError("librosa is required for tempo estimation. Install with: pip install librosa")

    y, sr = librosa.load(audio_file, sr=None, mono=True)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
    bpm = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return bpm


def choose_tempo_bpm(audio_file: str, user_bpm: Optional[float], use_estimate: bool) -> float:
    """
    Choose tempo:
    - If user provided: use it
    - If use_estimate flag: auto-detect
    - Otherwise: default to 120 BPM
    """
    if user_bpm is not None and user_bpm > 0:
        return float(user_bpm)

    if use_estimate and LIBROSA_AVAILABLE:
        try:
            est = estimate_tempo_bpm(audio_file)
            est = float(np.clip(est, 50.0, 240.0))
            log.info("Estimated tempo: %.1f BPM", est)
            return est
        except Exception as e:
            log.warning("Tempo estimation failed: %s. Defaulting to 120 BPM.", e)

    return 120.0


def hz_to_midi(hz: float) -> float:
    """Convert frequency in Hz to MIDI note number (float)."""
    return 69.0 + 12.0 * np.log2(hz / 440.0)


def midi_to_int(midi_float: float) -> int:
    """Round MIDI float to nearest integer and clamp to valid range."""
    return int(np.clip(int(round(midi_float)), 0, 127))


def apply_median_filter(data: np.ndarray, window_size: int = 5) -> np.ndarray:
    """
    Apply median filter to 1D array, handling NaN values and edges properly.

    Args:
        data: 1D numpy array
        window_size: size of the median filter window (must be odd)

    Returns:
        Filtered array
    """
    if window_size % 2 == 0:
        window_size += 1

    half_window = window_size // 2
    filtered = np.copy(data)

    for i in range(len(data)):
        start = max(0, i - half_window)
        end = min(len(data), i + half_window + 1)
        window = data[start:end]

        # Median ignoring NaNs
        valid = window[np.isfinite(window)]
        if len(valid) > 0:
            filtered[i] = np.median(valid)

    return filtered


def warn_if_likely_polyphonic(midi: np.ndarray, voiced_flag: np.ndarray, voiced_probs: np.ndarray) -> None:
    """
    Print a warning if the signal looks polyphonic/noisy for monophonic pitch tracking.

    This is a lightweight heuristic (80/20):
    - Low voiced ratio after gating
    - Low median voiced probability
    - High rate of large pitch jumps between adjacent voiced frames

    It won't be perfect, but it helps prevent "it ran, but results are nonsense" surprises.
    """
    try:
        voiced_idx = voiced_flag & np.isfinite(midi)
        if voiced_idx.sum() < 10:
            return

        voiced_ratio = float(voiced_idx.mean())

        vp = voiced_probs[voiced_idx] if voiced_probs is not None else None
        vp_med = float(np.median(vp)) if vp is not None and np.isfinite(vp).any() else float("nan")

        m = midi[voiced_idx]
        diffs = np.abs(np.diff(m))
        # "big jump" ~= more than 1 semitone between adjacent voiced frames
        jump_rate = float(np.mean(diffs > 1.0)) if diffs.size else 0.0

        # Heuristic thresholds tuned to be conservative (warn only when pretty suspicious)
        suspicious = (
            (voiced_ratio < 0.55) or
            (np.isfinite(vp_med) and vp_med < 0.70) or
            (jump_rate > 0.30)
        )

        if suspicious:
            log.warning(
                "This stem may be polyphonic, very noisy, or heavily modulated.\n"
                "Monophonic pitch tracking may produce incorrect notes (missing harmony, "
                "stuttering, octave flips).\n"
                "If this is a chord/pad or layered sound, expect quality loss vs the original."
            )
    except Exception:
        # Never fail the run due to a warning heuristic
        return


def synth_to_notes_monophonic(
    audio_file: str,
    fmin_hz: float = 65.0,
    fmax_hz: float = 2093.0,
    frame_length: int = 2048,
    hop_length: int = 512,
    min_note_ms: float = 60.0,
    min_silence_ms: float = 40.0,
    cents_tolerance: float = 50.0,
    velocity_floor: int = 40,
    velocity_ceil: int = 110,
    rms_gate_db: float = -30.0,
    pitch_smoothing: float = 0.05,
) -> list:
    """
    Extract monophonic notes from synth audio with robust cleaning.

    Returns a list of:
        (start_time_sec, end_time_sec, midi_note_int, velocity_int)
    """
    if not LIBROSA_AVAILABLE:
        raise ImportError("librosa is required for pitch detection")

    log.info("Loading audio: %s", audio_file)
    y, sr = librosa.load(audio_file, sr=None, mono=True)

    # Preemphasis to enhance high frequencies
    y = librosa.effects.preemphasis(y, coef=0.97)

    log.info("Extracting pitch (pyin)... this may take a moment.")
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y,
        fmin=fmin_hz,
        fmax=fmax_hz,
        sr=sr,
        frame_length=frame_length,
        hop_length=hop_length,
        fill_na=None  # Don't interpolate gaps
    )

    # Calculate RMS energy for gating
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

    # Ensure RMS and f0 arrays are same length
    if len(rms) < len(f0):
        rms = np.pad(rms, (0, len(f0) - len(rms)), mode='edge')
    elif len(rms) > len(f0):
        rms = rms[:len(f0)]

    # RMS Gating: Calculate dynamic threshold
    # Use 95th percentile to avoid being thrown off by a few loud peaks
    peak_rms = np.percentile(rms, 95)
    if peak_rms < 1e-6:
        log.warning("Audio appears to be silent or very quiet.")
        return []

    # Convert gate threshold from dB to linear
    gate_linear = peak_rms * (10 ** (rms_gate_db / 20.0))

    # Apply gate (silence threshold)
    silence_thresh = max(gate_linear, peak_rms * 0.01)
    voiced_flag = voiced_flag & (rms > silence_thresh)

    # Convert Hz to MIDI
    midi = np.full_like(f0, np.nan, dtype=float)
    voiced_indices = voiced_flag & np.isfinite(f0)

    if not np.any(voiced_indices):
        log.warning("No voiced frames detected after gating.")
        return []

    midi[voiced_indices] = hz_to_midi(f0[voiced_indices])

    # Validate detected pitch range
    valid_midi = midi[np.isfinite(midi)]
    if len(valid_midi) > 0:
        detected_range_hz = (
            2 ** ((valid_midi.min() - 69) / 12) * 440,
            2 ** ((valid_midi.max() - 69) / 12) * 440
        )
        log.info("Detected pitch range: %.1f - %.1f Hz", detected_range_hz[0], detected_range_hz[1])

        if detected_range_hz[0] < fmin_hz * 0.9 or detected_range_hz[1] > fmax_hz * 1.1:
            log.warning(
                "Detected pitch range extends beyond your fmin/fmax. "
                "If you get poor results, try adjusting --fmin/--fmax."
            )

    # Smooth pitch contour with median filter
    log.info("Applying median filter to smooth pitch contour...")
    midi = apply_median_filter(midi, window_size=5)
    warn_if_likely_polyphonic(midi, voiced_flag, voiced_probs)

    # Convert to time array
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)

    # Helper conversions
    min_note_frames = int(round((min_note_ms / 1000.0) * sr / hop_length))
    min_silence_frames = int(round((min_silence_ms / 1000.0) * sr / hop_length))
    semitone_tol = cents_tolerance / 100.0

    notes = []

    def commit_note(start_f: int, end_f: int):
        """Commit a note spanning frames [start_f, end_f)"""
        seg = midi[start_f:end_f]
        seg_rms = rms[start_f:end_f]

        seg = seg[np.isfinite(seg)]
        if len(seg) == 0:
            return

        midi_med = float(np.median(seg))
        midi_int = midi_to_int(midi_med)

        v = float(np.median(seg_rms))
        scale = float(np.percentile(rms, 95)) + 1e-9
        v_norm = np.clip(v / scale, 0.0, 1.0)
        velocity = int(round(velocity_floor + v_norm * (velocity_ceil - velocity_floor)))
        velocity = int(np.clip(velocity, 1, 127))

        start_t = float(times[start_f])
        end_t = float(times[end_f - 1] + (hop_length / sr))
        notes.append((start_t, end_t, midi_int, velocity))

    i = 0
    n = len(midi)

    while i < n:
        if not (np.isfinite(midi[i]) and voiced_flag[i]):
            i += 1
            continue

        start = i
        current_pitch = float(midi[i])

        i += 1
        last_voiced_frame = start
        gap_frames = 0

        # Continue note while pitch is stable
        while i < n:
            is_voiced = np.isfinite(midi[i]) and voiced_flag[i]

            if is_voiced:
                gap_frames = 0
                last_voiced_frame = i

                pitch_diff = abs(float(midi[i]) - current_pitch)

                if pitch_diff <= semitone_tol:
                    # Pitch is stable: smooth tracking for vibrato/bends
                    current_pitch = (1 - pitch_smoothing) * current_pitch + pitch_smoothing * float(midi[i])
                else:
                    # Pitch changed significantly: end current note
                    break
            else:
                gap_frames += 1
                if gap_frames > min_silence_frames:
                    break

            i += 1

        end = i

        # If we ended due to silence, snap end to last voiced frame
        if gap_frames > min_silence_frames:
            end = last_voiced_frame + 1
            i = end

        # Enforce minimum note duration
        if (end - start) >= max(1, min_note_frames):
            commit_note(start, end)

    log.info("Extracted %d notes", len(notes))
    return notes


def notes_to_midi(
    notes: list,
    output_midi: Path,
    tempo_bpm: float = 120.0,
    program: int = 81,
    channel: int = 0,
    ticks_per_beat: int = 960,
) -> Path:
    """
    Convert (start,end,midi,vel) notes into a MIDI file.

    We schedule note_on and note_off using absolute tick times, then sort events.
    This avoids delta-time drift and handles overlaps cleanly.
    """
    log.info("Creating MIDI file: %s", output_midi)

    mid = MidiFile(ticks_per_beat=ticks_per_beat)
    track = MidiTrack()
    mid.tracks.append(track)

    tempo_value = mido.bpm2tempo(float(tempo_bpm))
    track.append(MetaMessage("set_tempo", tempo=tempo_value, time=0))

    # Program change for synth sound
    program = int(np.clip(program, 0, 127))
    track.append(Message("program_change", program=program, time=0, channel=channel))

    ticks_per_second = (float(tempo_bpm) / 60.0) * ticks_per_beat

    events = []
    for start_t, end_t, midi_note, vel in notes:
        start_tick = int(round(float(start_t) * ticks_per_second))
        end_tick = int(round(float(end_t) * ticks_per_second))
        end_tick = max(end_tick, start_tick + 1)

        events.append((start_tick, Message("note_on", note=int(midi_note), velocity=int(vel), time=0, channel=channel)))
        events.append((end_tick, Message("note_off", note=int(midi_note), velocity=0, time=0, channel=channel)))

    # Sort by time; note_off before note_on at same time
    def sort_key(ev):
        t, msg = ev
        off_first = 0 if msg.type == "note_off" else 1
        return (t, off_first)

    events.sort(key=sort_key)

    # Absolute -> delta
    last_tick = 0
    for tick, msg in events:
        delta = max(0, tick - last_tick)
        msg.time = delta
        track.append(msg)
        last_tick = tick

    mid.save(str(output_midi))
    log.info("MIDI saved: %s", output_midi)
    return output_midi


def render_midi_with_fluidsynth(midi_file: Path, soundfont: str, output_wav: Path, gain: float = 0.5) -> Path:
    """
    Render MIDI file to WAV using FluidSynth.

    Args:
        midi_file: Path to MIDI file
        soundfont: Path to soundfont (.sf2)
        output_wav: Path for output WAV file
        gain: Output gain (0.0-1.0)

    Returns:
        Path to rendered WAV file
    """
    log.info("Rendering with FluidSynth...")

    # Check FluidSynth availability
    try:
        subprocess.run(["fluidsynth", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "FluidSynth not found. Install it:\n"
            "  macOS: brew install fluid-synth\n"
            "  Linux: apt-get install fluidsynth\n"
            "  Windows: https://github.com/FluidSynth/fluidsynth/releases"
        )

    # Check soundfont exists
    if not os.path.exists(soundfont):
        raise FileNotFoundError(f"Soundfont not found: {soundfont}")

    cmd = [
        "fluidsynth",
        "-ni",           # Non-interactive
        "-g", str(gain), # Gain
        "-T", "wav",     # Output format
        "-F", str(output_wav),  # Output file
        soundfont,
        str(midi_file)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FluidSynth stderr: %s", result.stderr)
        raise RuntimeError(f"FluidSynth failed with code {result.returncode}")

    log.info("Rendered WAV: %s", output_wav)
    return output_wav


def main():
    parser = argparse.ArgumentParser(
        description="Clean monophonic synth tracks by transcribing and re-synthesizing"
    )

    # Required arguments
    parser.add_argument("input_file", help="Input audio file (WAV, MP3, etc.)")
    parser.add_argument("--soundfont", "-s", required=True, help="Path to .sf2 soundfont")

    # Output options
    parser.add_argument("--output", "-o", help="Output WAV file (default: input_synth_clean.wav)")
    parser.add_argument("--midi-output", "-m", help="Output MIDI file (default: input_synth.mid)")

    # Preset (sets sensible defaults for common synth types)
    parser.add_argument(
        "--preset",
        choices=["lead", "bass", "pluck"],
        default=None,
        help=(
            "Synth type preset. Sets sensible fmin/fmax/gate/smoothing defaults. "
            "Explicit flags override preset values. "
            "lead: 130-2093 Hz; bass: 41-400 Hz; pluck: 130-4186 Hz."
        ),
    )

    # Tempo options
    parser.add_argument("--tempo", "-t", type=float, help="Tempo in BPM (recommended if known)")
    parser.add_argument("--use-tempo-estimate", action="store_true",
                        help="Auto-estimate tempo if not provided")

    # Render options
    parser.add_argument("--gain", type=float, default=0.5, help="FluidSynth gain (default: 0.5)")
    parser.add_argument("--program", type=int, default=81, help="GM program number (default: 81)")

    # Pitch detection range
    parser.add_argument("--hop-length", type=int, default=512,
                        help="Hop length in samples for pitch tracking (default: 512). Lower = better timing, slower.")
    parser.add_argument("--fmin", type=float, default=None,
                        help="Minimum frequency in Hz (default: 65.0 = C2, or preset value)")
    parser.add_argument("--fmax", type=float, default=None,
                        help="Maximum frequency in Hz (default: 2093.0 = C7, or preset value)")

    # Transcription tuning
    parser.add_argument("--min-note-ms", type=float, default=60.0,
                        help="Minimum note duration in ms (default: 60)")
    parser.add_argument("--min-silence-ms", type=float, default=40.0,
                        help="Minimum silence between notes in ms (default: 40)")
    parser.add_argument("--cents-tolerance", type=float, default=50.0,
                        help="Pitch deviation tolerance in cents (default: 50 = quarter tone)")
    parser.add_argument("--gate-db", type=float, default=None,
                        help="RMS noise gate threshold in dB (default: -30, or preset value)")
    parser.add_argument("--pitch-smoothing", type=float, default=None,
                        help="Pitch tracking smoothing factor 0.0-1.0 (default: 0.05, or preset value)")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    if not PYDUB_AVAILABLE:
        log.warning("pydub not available. MP3 conversion may be limited.")

    # Apply preset defaults for unset parameters
    # A parameter is "unset" if it still matches the parser default (None means explicit CLI override)
    fmin = args.fmin
    fmax = args.fmax
    gate_db = args.gate_db
    pitch_smoothing = args.pitch_smoothing

    if args.preset is not None:
        preset_vals = SYNTH_PRESETS[args.preset]
        log.info("Applying preset: %s (%s)", args.preset, preset_vals)
        if fmin is None:
            fmin = preset_vals["fmin"]
        if fmax is None:
            fmax = preset_vals["fmax"]
        if gate_db is None:
            gate_db = preset_vals["rms_gate_db"]
        if pitch_smoothing is None:
            pitch_smoothing = preset_vals["pitch_smoothing"]

    # Fall back to built-in defaults if still unset
    if fmin is None:
        fmin = 65.0
    if fmax is None:
        fmax = 2093.0
    if gate_db is None:
        gate_db = -30.0
    if pitch_smoothing is None:
        pitch_smoothing = 0.05

    # Set up file paths
    input_path = Path(args.input_file)
    output_wav = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_synth_clean.wav")
    midi_path = Path(args.midi_output) if args.midi_output else input_path.with_name(f"{input_path.stem}_synth.mid")

    wav_file = None
    created_temp = False

    try:
        # Convert to WAV if needed
        wav_file = convert_to_wav(args.input_file)
        created_temp = wav_file.endswith(".temp.wav")

        # Choose tempo
        tempo_bpm = choose_tempo_bpm(wav_file, args.tempo, args.use_tempo_estimate)
        log.info("Using tempo: %.1f BPM", tempo_bpm)

        # Extract notes (first pass)
        notes = synth_to_notes_monophonic(
            wav_file,
            fmin_hz=fmin,
            fmax_hz=fmax,
            hop_length=args.hop_length,
            min_note_ms=args.min_note_ms,
            min_silence_ms=args.min_silence_ms,
            cents_tolerance=args.cents_tolerance,
            velocity_floor=40,
            velocity_ceil=110,
            rms_gate_db=gate_db,
            pitch_smoothing=pitch_smoothing,
        )

        # Fallback: if no notes and gate was strict, retry with a more permissive gate
        if not notes and gate_db > -50.0:
            log.warning(
                "No notes found with current settings. "
                "Retrying with more permissive gate threshold..."
            )
            notes = synth_to_notes_monophonic(
                wav_file,
                fmin_hz=fmin,
                fmax_hz=fmax,
                hop_length=args.hop_length,
                min_note_ms=args.min_note_ms,
                min_silence_ms=args.min_silence_ms,
                cents_tolerance=args.cents_tolerance,
                velocity_floor=40,
                velocity_ceil=110,
                rms_gate_db=-40.0,  # More permissive
                pitch_smoothing=pitch_smoothing,
            )

        if not notes:
            log.error("No notes extracted. This may not be a clean monophonic synth stem.")
            sys.exit(1)

        # Write MIDI
        notes_to_midi(
            notes,
            output_midi=midi_path,
            tempo_bpm=tempo_bpm,
            program=args.program,
            channel=0
        )

        # Render MIDI -> WAV
        render_midi_with_fluidsynth(
            midi_file=midi_path,
            soundfont=args.soundfont,
            output_wav=output_wav,
            gain=args.gain
        )

        log.info("=" * 60)
        log.info("SUCCESS!")
        log.info("MIDI saved to: %s", midi_path)
        log.info("Clean synth saved to: %s", output_wav)
        log.info("=" * 60)

    except Exception as e:
        log.error("Error: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # Clean up temporary files
        if created_temp and wav_file and os.path.exists(wav_file):
            log.debug("Cleaning up temporary file: %s", wav_file)
            try:
                os.remove(wav_file)
            except OSError as e:
                log.warning("Could not remove temp file: %s", e)


if __name__ == "__main__":
    main()
