#!/usr/bin/env python3
"""
Rule-based bass generator.

Generates deterministic MIDI basslines from a chord progression. Harmonically
aware: respects diminished, augmented, and sus chord qualities when choosing
fifths. Supports non-4/4 time signatures via denominator-aware grid sizing.

Usage:
  bandleader-bass --progression "Am G | F | C/G" --style two_feel
  bandleader-bass --progression "Am | G" --time-signature 3/4
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from bandleader.chord_parser import (
    clamp_int,
    pc_to_midi,
    parse_progression_with_quality,
    triad_pcs,
)
from bandleader.cli_args import float_in_range, int_in_range, positive_int
from bandleader.utils import TimeSignature

log = logging.getLogger(__name__)


# -----------------------------
# Pattern / Style
# -----------------------------


@dataclass
class BassStyle:
    pattern_16: Tuple[int, ...]
    weak_hit_prob_per_bar: float = 0.15
    fifth_prob: float = 0.10
    octave_up_prob: float = 0.12
    vel_strong: int = 95
    vel_weak: int = 75
    vel_random_jitter: int = 6
    legato_factor: float = 0.95


# -----------------------------
# Generator
# -----------------------------


def generate_bass_events(
    progression: List[
        List[Tuple[int, str]]
    ],  # List of bars, each bar is list of (Root, Quality)
    *,
    total_bars: int,
    ts: TimeSignature,
    style: BassStyle,
    base_octave: int = 2,
    seed: Optional[int] = None,
    approach_prob_per_bar: float = 0.06,
    approach_mode: str = "safe",
) -> List[Tuple[float, int, int, float]]:

    rng = random.Random(seed)
    beats_per_bar = ts.beats_per_bar
    steps_per_beat = 4
    steps_per_bar = ts.steps_per_bar

    events: List[Tuple[float, int, int, float]] = []

    def get_chord_for_step(bar_idx: int, step_idx: int) -> Tuple[int, str]:
        """Determine which chord is active at this 16th-note step."""
        bar_chords = progression[bar_idx % len(progression)]
        num_chords = len(bar_chords)
        steps_per_chord = steps_per_bar / num_chords
        chord_idx = int(step_idx // steps_per_chord)
        chord_idx = min(chord_idx, num_chords - 1)
        return bar_chords[chord_idx]

    def choose_note(root: int, qual: str) -> int:
        """Choose note based on chord quality (Root, 5th, Octave)."""
        pc = root

        # Decide whether to play root or 5th
        if rng.random() < style.fifth_prob:
            # Calculate the correct 5th for this quality
            # triad_pcs returns [root, 3rd, 5th] (or similar for sus)
            intervals = triad_pcs(root, qual)
            if len(intervals) >= 3:
                pc = intervals[2]  # The 5th
            else:
                pc = (root + 7) % 12  # Fallback

        note = pc_to_midi(pc, base_octave)

        if rng.random() < style.octave_up_prob:
            note += 12

        return clamp_int(note, 28, 55)

    def is_strong_step(step: int) -> bool:
        return (step == 0) or (step == steps_per_beat * 2)

    for bar in range(total_bars):
        bar_start_beats = bar * beats_per_bar

        # 1. Active Steps from Pattern
        active_steps: List[int] = []
        pat_len = len(style.pattern_16)

        for step in range(steps_per_bar):
            # Wrap safely for time signatures where steps_per_bar != 16
            if style.pattern_16[step % pat_len] != 1:
                continue
            # Variation: skip some non-strong hits
            if (not is_strong_step(step)) and rng.random() < 0.08:
                continue
            active_steps.append(step)

        # 2. Extra Weak Hit (Variation)
        if rng.random() < style.weak_hit_prob_per_bar:
            rest_steps = [s for s in range(1, steps_per_bar) if s not in active_steps]
            if rest_steps:
                active_steps.append(rng.choice(rest_steps))

        # 3. Approach Note Logic
        add_approach = rng.random() < approach_prob_per_bar
        if add_approach:
            if (steps_per_bar - 1) not in active_steps:
                active_steps.append(steps_per_bar - 1)

        active_steps = sorted(set(active_steps))

        # 4. Generate Events
        for i, step in enumerate(active_steps):
            time_beats = bar_start_beats + (step / steps_per_beat)

            # Identify current chord
            root_pc, quality = get_chord_for_step(bar, step)

            # Determine Note
            if add_approach and step == steps_per_bar - 1:
                # Look ahead to next bar's first chord
                next_bar_chords = progression[(bar + 1) % len(progression)]
                target_root, target_qual = next_bar_chords[0]

                if approach_mode == "chromatic":
                    approach_pc = (target_root - 1) % 12
                    note = pc_to_midi(approach_pc, base_octave)
                else:
                    # Safe pickup: The 5th of the NEXT chord
                    target_intervals = triad_pcs(target_root, target_qual)
                    approach_pc = (
                        target_intervals[2]
                        if len(target_intervals) >= 3
                        else (target_root + 7) % 12
                    )
                    note = pc_to_midi(approach_pc, base_octave)

                note = clamp_int(note, 28, 55)
            else:
                note = choose_note(root_pc, quality)

            # Velocity
            strong = is_strong_step(step)
            base_vel = style.vel_strong if strong else style.vel_weak
            jitter = rng.randint(-style.vel_random_jitter, style.vel_random_jitter)
            vel = clamp_int(base_vel + jitter, 40, 120)

            # Duration
            if i < len(active_steps) - 1:
                gap_steps = active_steps[i + 1] - step
            else:
                gap_steps = steps_per_bar - step

            raw_dur_beats = gap_steps / steps_per_beat
            dur_beats = max(raw_dur_beats * style.legato_factor, 0.10)

            events.append((time_beats, note, vel, dur_beats))

    events.sort(key=lambda e: e[0])
    return events


# -----------------------------
# MIDI Writing
# -----------------------------


def write_midi(events, out_path, bpm, program=34, channel=0, ticks_per_beat=960):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mid = MidiFile(ticks_per_beat=ticks_per_beat)
    track = MidiTrack()
    mid.tracks.append(track)
    track.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    track.append(Message("program_change", program=program, time=0, channel=channel))

    msgs = []
    for t_beats, note, vel, dur_beats in events:
        t0 = int(round(t_beats * ticks_per_beat))
        t1 = int(round((t_beats + dur_beats) * ticks_per_beat))
        t1 = max(t1, t0 + 1)
        msgs.append(
            (t0, Message("note_on", note=note, velocity=vel, time=0, channel=channel))
        )
        msgs.append(
            (t1, Message("note_off", note=note, velocity=0, time=0, channel=channel))
        )

    msgs.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))

    last_tick = 0
    for tick, msg in msgs:
        msg.time = max(0, tick - last_tick)
        track.append(msg)
        last_tick = tick

    mid.save(out_path)


# -----------------------------
# CLI
# -----------------------------

BASS_PATTERNS = {
    "two_feel": (1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0),
    "four_on_floor": (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0),
    "eighths": (1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0),
    "disco": (0, 0, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 0),
}


def main():
    parser = argparse.ArgumentParser(description="Rule-based bass generator")
    parser.add_argument(
        "--progression", required=True, help='Chord progression, e.g., "Am G | F | C/G"'
    )
    parser.add_argument(
        "--bars",
        type=positive_int,
        default=32,
        help="Total bars to generate (default: 32)",
    )
    parser.add_argument(
        "--bpm",
        type=float_in_range(4.0, 1000.0),
        default=120.0,
        help="Tempo in BPM, 4-1000 (default: 120; MIDI cannot encode tempos below ~4 BPM)",
    )
    parser.add_argument(
        "--time-signature", default="4/4", help="Time signature, e.g., '4/4' or '3/4'"
    )
    parser.add_argument(
        "--out", default="bass.mid", help="Output MIDI file (default: bass.mid)"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducible output"
    )
    parser.add_argument(
        "--style",
        choices=sorted(BASS_PATTERNS),
        default="two_feel",
        help="Bass rhythm pattern (default: two_feel)",
    )
    parser.add_argument(
        "--legato",
        type=float_in_range(0.0, 1.0),
        default=0.95,
        help="Note duration factor 0.0-1.0 (default: 0.95)",
    )
    parser.add_argument(
        "--base-octave",
        type=int_in_range(0, 8),
        default=2,
        help="Base octave for bass notes 0-8 (default: 2)",
    )
    parser.add_argument(
        "--program",
        type=int_in_range(0, 127),
        default=34,
        help="MIDI program number 0-127 (default: 34 = Electric Bass)",
    )
    parser.add_argument(
        "--channel",
        type=int_in_range(0, 15),
        default=0,
        help="MIDI channel 0-15 (default: 0)",
    )
    parser.add_argument(
        "--weak-prob",
        type=float_in_range(0.0, 1.0),
        default=0.15,
        help="Probability of an extra weak-beat hit per bar (default: 0.15)",
    )
    parser.add_argument(
        "--approach-prob",
        type=float_in_range(0.0, 1.0),
        default=0.06,
        help="Probability of an approach note per bar (default: 0.06)",
    )
    parser.add_argument(
        "--approach",
        choices=["safe", "chromatic"],
        default="safe",
        help="Approach-note style (default: safe)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug output"
    )

    args = parser.parse_args()

    from bandleader.utils import setup_logging

    setup_logging(args.verbose)

    try:
        # UPDATED: Use the quality-aware parser
        progression = parse_progression_with_quality(args.progression)
    except ValueError as e:
        log.error("Error parsing progression: %s", e)
        sys.exit(1)

    try:
        ts_num, ts_den = map(int, args.time_signature.strip().split("/"))
        ts = TimeSignature(numerator=ts_num, denominator=ts_den)
        if ts_num <= 0 or ts_den <= 0:
            raise ValueError("time signature values must be positive")
    except ValueError:
        log.error(
            "Invalid time signature %r. Use 'numerator/denominator' with positive integers, e.g. '4/4'.",
            args.time_signature,
        )
        sys.exit(1)

    selected_pat = BASS_PATTERNS[args.style]

    style = BassStyle(
        pattern_16=selected_pat,
        weak_hit_prob_per_bar=float(args.weak_prob),
        legato_factor=float(args.legato),
    )

    events = generate_bass_events(
        progression,
        total_bars=int(args.bars),
        ts=ts,
        style=style,
        base_octave=int(args.base_octave),
        seed=args.seed,
        approach_prob_per_bar=float(args.approach_prob),
        approach_mode=args.approach,
    )

    write_midi(
        events,
        out_path=args.out,
        bpm=float(args.bpm),
        program=int(args.program),
        channel=int(args.channel),
    )

    log.info("Generated: %s", args.out)


if __name__ == "__main__":
    main()
