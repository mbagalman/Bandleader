#!/usr/bin/env python3
"""Export a sidechain trigger MIDI (and optional WAV) from drum MIDI."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import mido

from bandleader.cli_args import float_in_range, int_in_range, positive_int

log = logging.getLogger(__name__)


def _collect_kick_ticks(
    mid: mido.MidiFile, kick_note: int
) -> tuple[list[int], list[tuple[int, mido.MetaMessage]]]:
    """Collect kick note_on ticks and tempo changes across ALL tracks.

    Format-1 MIDI (the common DAW export layout) keeps notes in tracks 1+,
    so scanning only track 0 would silently find nothing. Tempo messages
    keep their absolute tick positions so mid-song tempo changes stay
    aligned in the trigger file.
    """
    kick_ticks: list[int] = []
    tempo_events: list[tuple[int, mido.MetaMessage]] = []

    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.is_meta and msg.type == "set_tempo":
                tempo_events.append((abs_tick, msg.copy(time=0)))
            if msg.type == "note_on" and msg.velocity > 0 and msg.note == kick_note:
                kick_ticks.append(abs_tick)

    kick_ticks.sort()
    tempo_events.sort(key=lambda x: x[0])
    return kick_ticks, tempo_events


def export_trigger_midi(
    input_midi: Path,
    output_midi: Path,
    *,
    kick_note: int = 36,
    trigger_note: int = 36,
    velocity: int = 127,
    note_len_ticks: int = 60,
) -> int:
    """Create trigger MIDI aligned to kick transients from a drum MIDI file."""
    mid = mido.MidiFile(str(input_midi))
    kick_ticks, tempo_events = _collect_kick_ticks(mid, kick_note)

    if not kick_ticks:
        # Do not write an output at all: an empty trigger file is useless and
        # the caller treats a zero count as failure.
        return 0

    out_mid = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)
    track = mido.MidiTrack()
    out_mid.tracks.append(track)

    # Merge tempo changes (at their original positions) with trigger notes.
    # Sort priority: tempo before note_off before note_on at the same tick.
    events: list[tuple[int, int, mido.Message]] = []
    for tick, tempo_msg in tempo_events:
        events.append((tick, -1, tempo_msg))
    for t in kick_ticks:
        on = mido.Message(
            "note_on", note=trigger_note, velocity=velocity, channel=9, time=0
        )
        off = mido.Message("note_off", note=trigger_note, velocity=0, channel=9, time=0)
        events.append((t, 1, on))
        events.append((t + max(1, note_len_ticks), 0, off))

    events.sort(key=lambda x: (x[0], x[1]))

    last_tick = 0
    for tick, _, msg in events:
        msg.time = max(0, tick - last_tick)
        track.append(msg)
        last_tick = tick

    output_midi.parent.mkdir(parents=True, exist_ok=True)
    out_mid.save(str(output_midi))
    return len(kick_ticks)


def render_trigger_audio(
    midi_file: Path, soundfont: Path, output_wav: Path, *, gain: float = 0.2
) -> None:
    cmd = [
        "fluidsynth",
        "-ni",
        "-g",
        str(gain),
        "-T",
        "wav",
        "-F",
        str(output_wav),
        str(soundfont),
        str(midi_file),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "FluidSynth render failed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export sidechain trigger from drum MIDI"
    )
    parser.add_argument("--input-midi", required=True)
    parser.add_argument("--output-midi", required=True)
    parser.add_argument(
        "--kick-note",
        type=int_in_range(0, 127),
        default=36,
        help="MIDI note treated as the kick 0-127 (default: 36)",
    )
    parser.add_argument(
        "--trigger-note",
        type=int_in_range(0, 127),
        default=36,
        help="MIDI note for trigger events 0-127 (default: 36)",
    )
    parser.add_argument(
        "--trigger-velocity",
        type=int_in_range(1, 127),
        default=127,
        help="Trigger note velocity 1-127 (default: 127)",
    )
    parser.add_argument(
        "--trigger-length-ticks",
        type=positive_int,
        default=60,
        help="Trigger note length in ticks (default: 60)",
    )
    parser.add_argument(
        "--render-audio",
        default=None,
        help="Optional output WAV path to render via FluidSynth",
    )
    parser.add_argument(
        "--soundfont", default=None, help="Soundfont for --render-audio"
    )
    parser.add_argument(
        "--audio-gain",
        type=float_in_range(0.0, 10.0),
        default=0.2,
        help="FluidSynth gain 0-10 (default: 0.2)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    from bandleader.utils import setup_logging

    setup_logging(args.verbose)

    input_midi = Path(args.input_midi)
    output_midi = Path(args.output_midi)

    if not input_midi.exists():
        raise FileNotFoundError(f"Input MIDI not found: {input_midi}")

    kick_count = export_trigger_midi(
        input_midi=input_midi,
        output_midi=output_midi,
        kick_note=int(args.kick_note),
        trigger_note=int(args.trigger_note),
        velocity=int(args.trigger_velocity),
        note_len_ticks=int(args.trigger_length_ticks),
    )
    if kick_count == 0:
        log.error(
            "No kick events (note %d) found in any track of %s; an empty trigger "
            "track is not useful. Check --kick-note against your drum mapping.",
            int(args.kick_note),
            input_midi,
        )
        sys.exit(1)
    log.info("Wrote trigger MIDI: %s (%d kick events)", output_midi, kick_count)

    if args.render_audio:
        if not args.soundfont:
            raise ValueError("--soundfont is required when --render-audio is set")
        render_trigger_audio(
            midi_file=output_midi,
            soundfont=Path(args.soundfont),
            output_wav=Path(args.render_audio),
            gain=float(args.audio_gain),
        )
        log.info("Wrote trigger WAV: %s", args.render_audio)


if __name__ == "__main__":
    main()
