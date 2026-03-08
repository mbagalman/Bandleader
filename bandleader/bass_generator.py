#!/usr/bin/env python3
"""
Rule-Based Bass Generator v2.2

Changelog (v2.2):
- FIX: Added `--time-signature` CLI argument to receive config from orchestrator.
- FIX: Replaced strict pattern length validation with a safe modulo wrap, allowing
  16-step grid patterns to adapt smoothly to non-4/4 time signatures like 3/4 or 6/8.

Changelog (v2.1):
- FEATURE: Added harmonic awareness. Now respects Diminished, Augmented, and Sus chords.
  Previously, the bass blindly played perfect 5ths. Now it calculates the 5th based on
  chord quality (e.g., playing a b5 for dim chords).
- REFACTOR: Switched from `parse_progression_roots` to `parse_progression_with_quality`.

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
from typing import List, Optional, Tuple

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from bandleader.chord_parser import (
    clamp_int,
    pc_to_midi,
    parse_progression_with_quality,
    triad_pcs,
)

log = logging.getLogger(__name__)


# -----------------------------
# Pattern / Style
# -----------------------------

@dataclass(frozen=True)
class TimeSignature:
    numerator: int = 4
    denominator: int = 4

    @property
    def beats_per_bar(self) -> float:
        """
        Quarter-note beats per bar.
        Example: 4/4 -> 4.0, 3/4 -> 3.0, 6/8 -> 3.0
        """
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError("Time signature values must be positive.")
        return self.numerator * (4.0 / self.denominator)

    @property
    def steps_per_bar(self) -> int:
        """
        16th-note grid steps per bar, rounded to nearest integer.
        Example: 4/4 -> 16, 3/4 -> 12, 6/8 -> 12.
        """
        return max(1, int(round(self.numerator * 16.0 / self.denominator)))


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
    progression: List[List[Tuple[int, str]]],  # List of bars, each bar is list of (Root, Quality)
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
                pc = (root + 7) % 12 # Fallback
        
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
                    approach_pc = target_intervals[2] if len(target_intervals) >= 3 else (target_root + 7) % 12
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
        msgs.append((t0, Message("note_on", note=note, velocity=vel, time=0, channel=channel)))
        msgs.append((t1, Message("note_off", note=note, velocity=0, time=0, channel=channel)))

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

def main():
    parser = argparse.ArgumentParser(description="Rule-Based Bass Generator v2.2")
    parser.add_argument("--progression", required=True, help='Chord progression')
    parser.add_argument("--bars", type=int, default=32)
    parser.add_argument("--bpm", type=float, default=120.0)
    parser.add_argument("--time-signature", default="4/4", help="Time signature, e.g., '4/4' or '3/4'")
    parser.add_argument("--out", default="bass.mid")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--style", default="two_feel")
    parser.add_argument("--legato", type=float, default=0.95)
    parser.add_argument("--base-octave", type=int, default=2)
    parser.add_argument("--program", type=int, default=34)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--weak-prob", type=float, default=0.15)
    parser.add_argument("--approach-prob", type=float, default=0.06)
    parser.add_argument("--approach", choices=["safe", "chromatic"], default="safe")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    try:
        # UPDATED: Use the quality-aware parser
        progression = parse_progression_with_quality(args.progression)
    except ValueError as e:
        log.error("Error parsing progression: %s", e)
        sys.exit(1)
        
    try:
        ts_num, ts_den = map(int, args.time_signature.strip().split('/'))
        ts = TimeSignature(numerator=ts_num, denominator=ts_den)
    except ValueError:
        log.error("Invalid time signature format. Use 'numerator/denominator' e.g. '4/4'")
        sys.exit(1)

    patterns = {
        "two_feel":      (1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0),
        "four_on_floor": (1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0),
        "eighths":       (1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0),
        "disco":         (0,0,1,0, 1,0,1,0, 0,0,1,0, 1,0,1,0),
    }
    selected_pat = patterns.get(args.style, patterns["two_feel"])

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
