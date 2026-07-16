"""
Drum transcription and re-synthesis tool.

This script takes a "fuzzy" drum track (WAV or MP3) and creates a clean version by:
1) Transcribing drum hits (timing, drum type, velocity) via onset detection
2) Generating a MIDI file from the transcription
3) Rendering the MIDI file with a clean drum soundfont using FluidSynth

Key timing detail:
- Onset detection happens in absolute time (seconds) and does NOT require BPM.
- BPM DOES matter for converting seconds -> MIDI ticks and for FluidSynth playback.
  If you know the song BPM, pass --tempo for best alignment and correct playback speed.

Requirements:
    pip install mido numpy librosa pydub

FluidSynth must be installed:
    - macOS: brew install fluid-synth
    - Linux: apt-get install fluidsynth
    - Windows: https://github.com/FluidSynth/fluidsynth/releases

You also need a drum soundfont (.sf2).
"""

import logging
import os
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

log = logging.getLogger(__name__)

# Optional: for audio file format conversion if needed
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


# General MIDI drum note mapping (MIDI channel 10 -> channel index 9)
DRUM_MAPPING = {
    "kick": 36,  # Bass Drum 1
    "snare": 38,  # Acoustic Snare
    "closed_hat": 42,  # Closed Hi-Hat
    "open_hat": 46,  # Open Hi-Hat
    "low_tom": 45,  # Low Tom
    "mid_tom": 47,  # Mid Tom
    "high_tom": 50,  # High Tom
    "crash": 49,  # Crash Cymbal 1
    "ride": 51,  # Ride Cymbal 1
}


def convert_to_wav(input_file: str) -> tuple[str, bool]:
    """
    Convert MP3 or other formats to WAV if needed.
    Returns (wav_path, created_temp). created_temp is True only when this
    function wrote a new temporary file that the caller should delete;
    the original input file is never flagged for deletion.
    """
    input_path = Path(input_file)

    if input_path.suffix.lower() == ".wav":
        return str(input_file), False

    if not PYDUB_AVAILABLE:
        log.warning(
            "Cannot convert %s to WAV without pydub. "
            "Proceeding with original file: %s",
            input_path.suffix,
            input_file,
        )
        return str(input_file), False

    log.info("Converting %s to WAV...", input_file)
    audio = AudioSegment.from_file(input_file)
    # Unique temp path: a fixed sibling name could overwrite a pre-existing
    # file (then delete it during cleanup) and races between concurrent runs.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{input_path.stem}_", suffix=".temp.wav", dir=str(input_path.parent)
    )
    os.close(fd)
    audio.export(tmp_name, format="wav")
    log.info("Converted to %s", tmp_name)
    return tmp_name, True


def estimate_tempo_bpm(audio_file: str) -> float:
    """
    Estimate tempo using librosa. Drum-only stems can often produce half/double-time results.
    Returns a float BPM.
    """
    if not LIBROSA_AVAILABLE:
        raise ImportError(
            "librosa is required for tempo estimation. Install with: pip install librosa"
        )

    y, sr = librosa.load(audio_file, sr=None)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # librosa.feature.tempo is the non-deprecated home of tempo estimation
    # (librosa.beat.tempo is deprecated); it returns an array.
    tempo = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    bpm = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return bpm


def tempo_sanity_check(user_bpm: float, estimated_bpm: float) -> None:
    """
    Warn if the estimated BPM strongly disagrees with user BPM, especially by ~2x or ~0.5x.
    This catches the most common beat-tracking ambiguity on drum-heavy audio.
    """
    if user_bpm <= 0 or estimated_bpm <= 0:
        return

    ratios = [
        estimated_bpm / user_bpm,
        user_bpm / estimated_bpm,
    ]

    # Common ambiguities: 2x, 1/2x
    # We'll flag if within ~12% of 2.0 or 0.5 (i.e., 1.76-2.24 or 0.44-0.56)
    close_to_double = any(1.76 <= r <= 2.24 for r in ratios)
    close_to_half = any(0.44 <= r <= 0.56 for r in ratios)

    # Also warn if just "very different" (>25%) but not a clear half/double
    rel_diff = abs(user_bpm - estimated_bpm) / max(user_bpm, 1e-9)
    very_different = rel_diff >= 0.25

    if close_to_double or close_to_half:
        log.warning(
            "Estimated tempo (~%.1f BPM) differs from your --tempo (%.1f BPM) by ~2x.\n"
            "Beat trackers often return half/double-time on drum-heavy audio.\n"
            "Using your provided BPM for MIDI timing/playback.",
            estimated_bpm,
            user_bpm,
        )
    elif very_different:
        log.warning(
            "Estimated tempo (~%.1f BPM) differs substantially from your --tempo (%.1f BPM).\n"
            "Using your provided BPM for MIDI timing/playback.",
            estimated_bpm,
            user_bpm,
        )


def choose_tempo_bpm(audio_file: str, user_bpm: float | None) -> float:
    """
    Choose tempo:
    - If user provided BPM: use it (with a warning if it clashes with estimated BPM).
    - Otherwise: estimate BPM.
    Clamp to a reasonable range to avoid absurd conversions, but keep it wide enough for EDM/fast genres.
    """
    if user_bpm is not None and user_bpm > 0:
        # Optional: compare against estimate for warning only
        if LIBROSA_AVAILABLE:
            try:
                est = estimate_tempo_bpm(audio_file)
                tempo_sanity_check(float(user_bpm), est)
            except (RuntimeError, OSError, ValueError) as e:
                log.warning("Tempo sanity check skipped: %s", e)
        return float(user_bpm)

    if not LIBROSA_AVAILABLE:
        log.warning(
            "librosa not available for tempo estimation; defaulting to 120 BPM."
        )
        return 120.0

    try:
        est = estimate_tempo_bpm(audio_file)
    except (RuntimeError, OSError, ValueError) as e:
        log.warning("Tempo estimation failed (%s); defaulting to 120 BPM.", e)
        return 120.0

    # Wider clamp than 60-200, because half/double-time + fast dance genres are common
    est_clamped = float(np.clip(est, 50.0, 240.0))
    if abs(est_clamped - est) > 1e-6:
        log.warning("Tempo estimate %.1f BPM clamped to %.1f BPM.", est, est_clamped)

    log.info("Estimated tempo: %.1f BPM", est_clamped)
    return est_clamped


def transcribe_drums_basic(audio_file: str):
    """
    Basic onset detection using librosa.
    Approx drum-type classification via spectral centroid.

    Returns: list of (time_seconds, drum_name, velocity_int)
    """
    if not LIBROSA_AVAILABLE:
        raise ImportError(
            "librosa is required for basic transcription. Install with: pip install librosa"
        )

    log.info("Using basic onset detection on %s...", audio_file)

    y, sr = librosa.load(audio_file, sr=None)

    # Separate harmonic and percussive components
    _, y_percussive = librosa.effects.hpss(y)

    hop_length = 512

    onset_frames = librosa.onset.onset_detect(
        y=y_percussive,
        sr=sr,
        hop_length=hop_length,
        wait=1,
        pre_avg=1,
        post_avg=1,
        pre_max=1,
        post_max=1,
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
    onset_env = librosa.onset.onset_strength(
        y=y_percussive, sr=sr, hop_length=hop_length
    )

    drum_events = []

    for onset_frame, onset_time in zip(onset_frames, onset_times):
        onset_sample = librosa.frames_to_samples(onset_frame, hop_length=hop_length)

        window_samples = int(0.05 * sr)  # ~50ms
        window_start = max(0, onset_sample - window_samples // 4)
        window_end = min(len(y_percussive), onset_sample + window_samples)
        window = y_percussive[window_start:window_end]

        if len(window) == 0:
            continue

        spectral_centroid = float(
            librosa.feature.spectral_centroid(y=window, sr=sr)[0, 0]
        )

        if spectral_centroid < 500:
            drum_type = "kick"
        elif spectral_centroid < 3000:
            drum_type = "snare"
        else:
            drum_type = "closed_hat"

        env_val = float(onset_env[onset_frame]) if onset_frame < len(onset_env) else 0.0
        velocity = int(min(127, env_val * 20))
        velocity = max(40, velocity)

        drum_events.append((float(onset_time), drum_type, velocity))

    log.info("Found %d onsets (basic)", len(drum_events))
    return drum_events


def create_midi(drum_events, output_file: str, tempo_bpm: float) -> str:
    """
    Create a MIDI file from the transcribed drum events.

    IMPORTANT: For percussion we use note_off time=0 to avoid shifting subsequent events.
    """
    log.info("Creating MIDI file: %s", output_file)

    mid = MidiFile(ticks_per_beat=960)
    track = MidiTrack()
    mid.tracks.append(track)

    tempo_value = mido.bpm2tempo(float(tempo_bpm))
    track.append(MetaMessage("set_tempo", tempo=tempo_value, time=0))

    # Sort by time
    drum_events.sort(key=lambda x: x[0])

    ticks_per_beat = mid.ticks_per_beat
    ticks_per_second = (float(tempo_bpm) / 60.0) * ticks_per_beat

    last_time_sec = 0.0

    for time_sec, drum_type, velocity in drum_events:
        time_sec = float(time_sec)
        delta_ticks = int(round((time_sec - last_time_sec) * ticks_per_second))
        delta_ticks = max(0, delta_ticks)

        note = DRUM_MAPPING.get(drum_type, DRUM_MAPPING["snare"])

        track.append(
            Message(
                "note_on",
                note=note,
                velocity=int(velocity),
                time=delta_ticks,
                channel=9,
            )
        )
        track.append(Message("note_off", note=note, velocity=0, time=0, channel=9))

        last_time_sec = time_sec

    mid.save(output_file)
    log.info("MIDI file created with %d notes", len(drum_events))
    return output_file


def render_midi_with_fluidsynth(
    midi_file: str, soundfont: str, output_file: str, gain: float = 0.5
) -> str:
    """
    Render MIDI file to audio using FluidSynth.
    """
    log.info("Rendering MIDI with FluidSynth...")

    try:
        subprocess.run(["fluidsynth", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "FluidSynth not found. Please install it and ensure it's on your PATH."
        ) from e

    if not os.path.exists(soundfont):
        raise FileNotFoundError(f"Soundfont not found: {soundfont}")

    cmd = [
        "fluidsynth",
        "-ni",
        "-g",
        str(gain),
        "-T",
        "wav",
        "-F",
        output_file,
        soundfont,
        midi_file,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    if result.returncode != 0:
        log.error("FluidSynth stderr: %s", result.stderr)
        raise RuntimeError(f"FluidSynth failed with code {result.returncode}")

    log.info("Audio rendered successfully: %s", output_file)
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Clean fuzzy drum tracks by transcribing + re-synthesizing."
    )
    parser.add_argument("input_file", help="Input audio file (WAV/MP3/etc.)")
    parser.add_argument(
        "--soundfont", "-s", required=True, help="Path to .sf2 soundfont"
    )
    parser.add_argument(
        "--output", "-o", help="Output audio file (default: <input>_clean.wav)"
    )
    parser.add_argument(
        "--midi-output", "-m", help="Save MIDI file path (default: <input>.mid)"
    )
    parser.add_argument(
        "--tempo",
        "-t",
        type=float,
        default=None,
        help="Tempo in BPM. Strongly recommended if known (better alignment + playback speed).",
    )
    parser.add_argument(
        "--gain", "-g", type=float, default=0.5, help="Output gain 0.0-1.0"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug output"
    )
    args = parser.parse_args()

    from bandleader.utils import setup_logging

    setup_logging(args.verbose)

    # Emit availability warnings now that logging is set up
    if not PYDUB_AVAILABLE:
        log.warning("pydub not available. MP3 conversion may be limited.")

    input_path = Path(args.input_file)
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)
    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(f"{input_path.stem}_clean.wav")
    )
    midi_path = (
        Path(args.midi_output) if args.midi_output else input_path.with_suffix(".mid")
    )

    wav_file = None
    created_temp = False

    try:
        wav_file, created_temp = convert_to_wav(args.input_file)

        # Decide tempo: user override beats auto-estimate (but we warn if wildly different)
        tempo_bpm = choose_tempo_bpm(wav_file, args.tempo)
        log.info("Using tempo for MIDI/playback: %.1f BPM", tempo_bpm)

        # Transcribe
        drum_events = transcribe_drums_basic(wav_file)

        if not drum_events:
            log.error("No drum hits detected; no output written.")
            sys.exit(1)

        create_midi(drum_events, str(midi_path), tempo_bpm=tempo_bpm)
        render_midi_with_fluidsynth(
            str(midi_path), args.soundfont, str(output_path), gain=args.gain
        )

        log.info("=" * 50)
        log.info("SUCCESS!")
        log.info("Clean drums saved to: %s", output_path)
        log.info("MIDI saved to: %s", midi_path)
        log.info("=" * 50)

    except (RuntimeError, OSError, ValueError) as e:
        log.error("Error: %s", e)
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)

    finally:
        if created_temp and wav_file and os.path.exists(wav_file):
            log.debug("Cleaning up temporary file: %s", wav_file)
            try:
                os.remove(wav_file)
            except OSError as e:
                log.warning("Could not remove temp file: %s", e)


if __name__ == "__main__":
    main()
