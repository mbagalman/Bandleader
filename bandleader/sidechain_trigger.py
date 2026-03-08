#!/usr/bin/env python3
"""Export a sidechain trigger MIDI (and optional WAV) from drum MIDI."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import mido

log = logging.getLogger(__name__)


def _collect_kick_ticks(mid: mido.MidiFile, kick_note: int) -> tuple[list[int], list[mido.MetaMessage]]:
    abs_tick = 0
    kick_ticks: list[int] = []
    tempo_msgs: list[mido.MetaMessage] = []

    if not mid.tracks:
        return kick_ticks, tempo_msgs

    for msg in mid.tracks[0]:
        abs_tick += msg.time
        if msg.is_meta and msg.type == "set_tempo":
            tempo_msgs.append(msg.copy(time=0))
        if msg.type == "note_on" and msg.velocity > 0 and msg.note == kick_note:
            kick_ticks.append(abs_tick)

    return kick_ticks, tempo_msgs


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
    kick_ticks, tempo_msgs = _collect_kick_ticks(mid, kick_note)

    out_mid = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)
    track = mido.MidiTrack()
    out_mid.tracks.append(track)

    for tempo_msg in tempo_msgs:
        track.append(tempo_msg.copy(time=0))

    events: list[tuple[int, mido.Message]] = []
    for t in kick_ticks:
        on = mido.Message("note_on", note=trigger_note, velocity=velocity, channel=9, time=0)
        off = mido.Message("note_off", note=trigger_note, velocity=0, channel=9, time=0)
        events.append((t, on))
        events.append((t + max(1, note_len_ticks), off))

    events.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))

    last_tick = 0
    for tick, msg in events:
        msg.time = max(0, tick - last_tick)
        track.append(msg)
        last_tick = tick

    output_midi.parent.mkdir(parents=True, exist_ok=True)
    out_mid.save(str(output_midi))
    return len(kick_ticks)


def render_trigger_audio(midi_file: Path, soundfont: Path, output_wav: Path, *, gain: float = 0.2) -> None:
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "FluidSynth render failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export sidechain trigger from drum MIDI")
    parser.add_argument("--input-midi", required=True)
    parser.add_argument("--output-midi", required=True)
    parser.add_argument("--kick-note", type=int, default=36)
    parser.add_argument("--trigger-note", type=int, default=36)
    parser.add_argument("--trigger-velocity", type=int, default=127)
    parser.add_argument("--trigger-length-ticks", type=int, default=60)
    parser.add_argument("--render-audio", default=None)
    parser.add_argument("--soundfont", default=None)
    parser.add_argument("--audio-gain", type=float, default=0.2)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

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
