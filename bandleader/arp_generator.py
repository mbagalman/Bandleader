#!/usr/bin/env python3
"""
Rule-Based Arp/Pad Generator v2.2

Changelog (v2.2):
- FIX: Explicitly set logging stream to sys.stderr for consistency with the rest of the orchestration pipeline.

Changelog (v2.1):
- FIX: Dynamic `steps_per_bar` and `beats_per_step` calculation to correctly support 
  non-4/4 time signatures without stretching/squishing the grid tempo.
- FEATURE: Added `--time-signature` CLI argument to receive config from orchestrator.

Changelog (v2.0):
- PACKAGE: Moved into bandleader package.
- REFACTOR: Chord/progression parsing now imported from bandleader.chord_parser
  (single source of truth shared with bass_generator).
- FEATURE (pad mode): Upgraded pad voicing from note-by-note gravity to chord-as-a-set
  voice leading. Each chord is voiced to minimize total 'movement' from previous chord.
- FEATURE: Added more arp patterns (alberti, broken, random_no_repeat).

Usage examples:
  python -m bandleader.arp_generator --progression "Am | F | C | G" --out layer.mid
  python -m bandleader.arp_generator --progression "Dm | G | C" --time-signature "3/4"
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

from bandleader.chord_parser import parse_progression

log = logging.getLogger(__name__)


# -----------------------------
# Data Models
# -----------------------------

@dataclass(frozen=True)
class TimeSignature:
    """Time signature representation (e.g., 4/4, 3/4, 6/8)."""
    numerator: int
    denominator: int = 4

    @property
    def beats_per_bar(self) -> float:
        """Quarter-note beats per bar."""
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError("Time signature values must be positive.")
        return self.numerator * (4.0 / self.denominator)

    @property
    def steps_per_bar(self) -> int:
        """16th-note steps per bar."""
        return max(1, int(round(self.numerator * 16.0 / self.denominator)))


@dataclass
class ArpStyle:
    """Style configuration for arpeggiator/pad generation."""
    pattern_16: Tuple[int, ...]  # 16th-note pattern (1=hit, 0=rest)
    pattern_name: str = "eighths"  # Rhythm/pattern name (e.g., eighths, alberti)
    gate: float = 0.85            # Note duration as fraction of grid step
    vel_base: int = 75            # Base velocity
    vel_accent: int = 95          # Accented beat velocity
    vel_jitter: int = 5           # Random velocity variation
    motion: str = "up"            # Arp direction: up, down, updown, random
    include_octave: bool = True   # Whether to include upper octave in arp
    pad_legato: float = 0.95      # Pad note duration factor (0.95 = slight gap)


# -----------------------------
# Pattern Library
# -----------------------------

PATTERNS_16 = {
    # 16 slots, typical for one 4/4 bar, each slot = 16th note.
    # The generation loop safely wraps this pattern via modulo for non-4/4 signatures.
    "eighths": (1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0),
    "sixteenths": (1,) * 16,
    "syncop": (1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0),
    "pop_arp": (1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0),
    "alberti": (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0),  # Will use special alberti logic
    "broken": (1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0),
    "random_no_repeat": (1,) * 16,  # Use random picking logic; pattern indicates "grid is active"
}


def pattern_for_style(name: str) -> Tuple[int, ...]:
    """Return 16-step pattern for a given style name."""
    key = (name or "").strip().lower()
    if key not in PATTERNS_16:
        raise ValueError(f"Unknown style pattern: {name!r}. Choices: {sorted(PATTERNS_16.keys())}")
    return PATTERNS_16[key]


# -----------------------------
# Music Helpers
# -----------------------------

def triad_for_chord(root_pc: int, quality: str) -> List[int]:
    """
    Return triad pitch classes (0-11) for chord root and quality.
    quality typically: maj, min, dim, aug, sus2, sus4, 7, maj7, min7...
    For arp/pad v2.0 we focus on basic triads + common 7th chords simplified to triad.
    """
    q = (quality or "maj").lower()

    # Base triad intervals
    if q in ("min", "m"):
        intervals = [0, 3, 7]
    elif q in ("dim", "o"):
        intervals = [0, 3, 6]
    elif q in ("aug", "+"):
        intervals = [0, 4, 8]
    elif q in ("sus2",):
        intervals = [0, 2, 7]
    elif q in ("sus4", "sus"):
        intervals = [0, 5, 7]
    else:
        # Default to major
        intervals = [0, 4, 7]

    return [((root_pc + i) % 12) for i in intervals]


def pc_to_midi(pc: int, octave: int) -> int:
    """Convert pitch class and octave to MIDI note number. Octave: 0= C0.. 4=C4."""
    return int(12 * (octave + 1) + pc)  # MIDI C4 = 60 when pc=0 octave=4


def nearest_note(target: int, candidates: List[int]) -> int:
    """Return candidate note closest to target."""
    return min(candidates, key=lambda n: abs(n - target))


def voice_lead_chord(prev_notes: List[int], chord_pcs: List[int], *, center: int) -> List[int]:
    """
    Voice-lead a chord (set of pitch classes) by selecting MIDI notes near previous chord notes
    and near a center key. This keeps pads smooth.

    - prev_notes: MIDI notes from previous chord (sorted)
    - chord_pcs: pitch classes for current chord
    - center: center MIDI note (e.g., 60)

    Returns list of MIDI notes (sorted).
    """
    # If no previous chord, build a simple close voicing around center
    if not prev_notes:
        # Build base octave from center
        base_oct = max(0, min(8, (center // 12) - 1))
        notes = sorted(pc_to_midi(pc, base_oct) for pc in chord_pcs)
        # If notes too low/high relative to center, nudge by octaves
        for i in range(len(notes)):
            while notes[i] < center - 8:
                notes[i] += 12
            while notes[i] > center + 8:
                notes[i] -= 12
        return sorted(notes)

    # Otherwise, choose notes for each chord pc that are close to prev notes and center.
    # We generate candidate octaves and then pick nearest per voice slot.
    chosen: List[int] = []

    # Use same number of voices as prev_notes (or triad size) — prefer prev voice count.
    voice_count = max(1, min(len(prev_notes), len(chord_pcs)))
    pcs = chord_pcs[:voice_count]

    for v in range(voice_count):
        pc = pcs[v]
        # Candidates over a few octaves around center
        cands = []
        for octv in range(0, 9):
            cands.append(pc_to_midi(pc, octv))
        # Prefer notes near prev voice and center (weighted)
        prev_target = prev_notes[v] if v < len(prev_notes) else center
        best = min(cands, key=lambda n: (abs(n - prev_target) + 0.5 * abs(n - center)))
        chosen.append(best)

    # If we dropped tones because prev had fewer voices, optionally add extra chord tones near center
    if len(chord_pcs) > voice_count:
        remaining = chord_pcs[voice_count:]
        for pc in remaining:
            cands = [pc_to_midi(pc, o) for o in range(0, 9)]
            best = min(cands, key=lambda n: abs(n - center))
            chosen.append(best)

    # Sort and spread out duplicates by octave if needed
    chosen.sort()
    # De-duplicate exact notes by nudging octaves
    seen = set()
    for i in range(len(chosen)):
        while chosen[i] in seen:
            chosen[i] += 12
        seen.add(chosen[i])

    return sorted(chosen)


def resolve_bar_chords(progression: List[List[Tuple[int, str]]], bar_idx: int) -> List[Tuple[int, str]]:
    """Return chord list for a given bar index, repeating progression as needed."""
    if not progression:
        return [(0, "maj")]
    return progression[bar_idx % len(progression)]


def compute_pad_segments(bar_chords: List[Tuple[int, str]], steps_per_bar: int) -> List[Tuple[int, str, int, int]]:
    """
    Compute non-overlapping pad segments that fully cover the bar.
    Returns tuples: (root_pc, qual, start_step, seg_len_steps)
    """
    if steps_per_bar <= 0:
        return []
    if not bar_chords:
        bar_chords = [(0, "maj")]

    n_chords = len(bar_chords)
    boundaries: List[Tuple[int, int]] = []
    last_idx = None
    for step in range(steps_per_bar):
        idx = (step * n_chords) // steps_per_bar
        if idx != last_idx:
            boundaries.append((idx, step))
            last_idx = idx

    segments: List[Tuple[int, str, int, int]] = []
    for i, (idx, start) in enumerate(boundaries):
        end = boundaries[i + 1][1] if i + 1 < len(boundaries) else steps_per_bar
        seg_len = end - start
        if seg_len <= 0:
            continue
        root_pc, qual = bar_chords[idx]
        segments.append((root_pc, qual, start, seg_len))
    return segments


def chord_for_step(bar_chords: List[Tuple[int, str]], step: int, steps_per_bar: int) -> Tuple[int, str]:
    """Choose chord for a particular grid step within the bar, based on number of chords in bar."""
    n = max(1, len(bar_chords))
    steps_per_chord = max(1, steps_per_bar // n)
    idx = (step // steps_per_chord)
    idx = min(idx, n - 1)
    return bar_chords[idx]


def build_arp_cycle(triad: List[int], *, include_octave: bool, style: str) -> List[int]:
    """
    Build the note sequence for arpeggiation.

    Returns list where first half is base octave, second half (if include_octave) is +1 octave.
    Position in list determines octave offset during playback.

    Special patterns:
    - alberti: [root, fifth, third, fifth] (Alberti bass pattern)
    - Others: standard [root, third, fifth] + optional octave
    """
    if style == "alberti":
        # Alberti bass: root, fifth, third, fifth
        # [0, 2, 1, 2] indices into triad
        base = [triad[0], triad[2], triad[1], triad[2]]
    else:
        base = triad[:]

    if include_octave:
        # Add upper octave version
        base = base + base

    return base


def pick_next_degree(
    order: List[int],
    pos: int,
    *,
    motion: str,
    rng: random.Random,
    last_idx: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Pick the next arpeggio degree from 'order' given a position and motion.

    Returns (degree_value, new_pos)
    degree_value is a pitch class (0-11) from order list.
    """
    n = len(order)
    if n == 0:
        return 0, pos

    motion = (motion or "up").lower()

    if motion == "up":
        idx = pos % n
        return order[idx], pos + 1

    if motion == "down":
        idx = (-pos) % n
        return order[idx], pos + 1

    if motion == "updown":
        # bounce between ends
        cycle_len = max(1, (n * 2) - 2)
        t = pos % cycle_len
        idx = t if t < n else cycle_len - t
        return order[idx], pos + 1

    if motion == "random":
        idx = rng.randrange(n)
        return order[idx], pos + 1

    if motion == "random_no_repeat":
        # pick random idx != last_idx if possible
        if n == 1:
            return order[0], pos + 1
        idx = rng.randrange(n)
        if last_idx is not None and idx == last_idx:
            idx = (idx + 1 + rng.randrange(n - 1)) % n
        return order[idx], pos + 1

    # default fallback
    idx = pos % n
    return order[idx], pos + 1


# -----------------------------
# Event Generation
# -----------------------------

def generate_events(
    progression: List[List[Tuple[int, str]]],
    *,
    bars: int,
    ts: TimeSignature,
    mode: str,
    style: ArpStyle,
    base_octave: int = 4,
    center_key: int = 60,
    channel: int = 0,
    seed: Optional[int] = None,
) -> List[Tuple[float, int, int, float, int]]:
    """
    Generate MIDI events for arpeggiator or pad.

    Returns list of events: (time_beats, midi_note, velocity, duration_beats, channel)

    Args:
        progression: List of bars, each bar is list of (root_pc, quality) tuples
        bars: Total number of bars to generate
        ts: Time signature
        mode: "arp" or "pad"
        style: ArpStyle configuration
        base_octave: Base octave for arp mode (0-8)
        center_key: Center MIDI note for pad voicing (0-127, default 60=C4)
        channel: MIDI channel (0-15)
        seed: Random seed for reproducibility
    """
    # Input validation
    if not 0 <= base_octave <= 8:
        raise ValueError(f"base_octave {base_octave} out of range 0-8")
    if not 0 <= center_key <= 127:
        raise ValueError(f"center_key {center_key} out of range 0-127")
    if not 0 <= channel <= 15:
        raise ValueError(f"channel {channel} out of range 0-15")

    rng = random.Random(seed)

    # Dynamic Grid based on Time Signature
    # 16th notes = 4 steps per beat. This ensures that regardless of time signature, 
    # the temporal scaling is identical to standard 4/4 BPM.
    steps_per_beat = 4
    beats_per_bar = ts.beats_per_bar
    steps_per_bar = ts.steps_per_bar
    beats_per_step = 1.0 / steps_per_beat  # e.g., 0.25 beats per 16th note step

    events: List[Tuple[float, int, int, float, int]] = []

    mode = (mode or "arp").lower()
    if mode not in ("arp", "pad"):
        raise ValueError("mode must be 'arp' or 'pad'")

    arp_pos = 0
    last_rand_idx: Optional[int] = None
    prev_pad_notes: List[int] = []

    for bar in range(bars):
        bar_chords = resolve_bar_chords(progression, bar)

        # PAD MODE: one chord per segment, voice-led, long notes
        if mode == "pad":
            for root_pc, qual, start_step, seg_len_steps in compute_pad_segments(bar_chords, steps_per_bar):
                chord_pcs = triad_for_chord(root_pc, qual)
                pad_notes = voice_lead_chord(prev_pad_notes, chord_pcs, center=center_key)

                t = (bar * beats_per_bar) + (start_step * beats_per_step)

                # Duration: segment length in beats times pad_legato
                dur_beats = (seg_len_steps * beats_per_step) * style.pad_legato
                vel = style.vel_base

                for note in pad_notes:
                    events.append((t, note, vel, dur_beats, channel))

                prev_pad_notes = pad_notes

            continue

        # ARP MODE: iterate 16th steps and emit note on pattern hits
        for step in range(steps_per_bar):
            # Loop the pattern safely across varying bar lengths
            pat_len = len(style.pattern_16)
            hit = style.pattern_16[step % pat_len] if style.pattern_16 else 0
            if not hit:
                continue

            root_pc, qual = chord_for_step(bar_chords, step, steps_per_bar)
            triad = triad_for_chord(root_pc, qual)

            # Build arp cycle (pattern_name controls special patterns like alberti)
            cycle = build_arp_cycle(
                triad,
                include_octave=style.include_octave,
                style=str(style.pattern_name)
            )

            # Pick next note in cycle
            deg_idx, arp_pos = pick_next_degree(
                cycle,
                arp_pos,
                motion=style.motion,
                rng=rng,
                last_idx=last_rand_idx,
            )

            # Track last random idx for no-repeat motion
            if (style.motion or "").lower() == "random_no_repeat":
                # Find position in cycle list
                try:
                    last_rand_idx = cycle.index(deg_idx)
                except ValueError:
                    last_rand_idx = None

            # Map pitch class to MIDI note
            # For cycle elements already pitch classes, choose octave based on whether it is in upper half
            # (if include_octave, cycle length doubled)
            octave_offset = 0
            if style.include_octave and len(cycle) > len(triad):
                # If cycle is doubled, degree in second half indicates +1 octave, but our cycle values are pcs,
                # so we infer octave by position in cycle list, not by pc value. Use arp_pos-1 as last position.
                idx_pos = (arp_pos - 1) % len(cycle)
                if idx_pos >= len(cycle) // 2:
                    octave_offset = 1

            note = pc_to_midi(deg_idx, base_octave + octave_offset)

            # Timing
            t = (bar * beats_per_bar) + (step * beats_per_step)

            # Velocity: accent on downbeats and mild jitter
            beat = step * beats_per_step
            is_downbeat = abs((beat % 1.0) - 0.0) < 1e-9
            vel = style.vel_accent if is_downbeat else style.vel_base
            vel += rng.randint(-style.vel_jitter, style.vel_jitter)
            vel = max(1, min(127, vel))

            # Duration
            dur_beats = beats_per_step * style.gate

            events.append((t, note, vel, dur_beats, channel))

    # Sort by time
    events.sort(key=lambda e: e[0])
    return events


# -----------------------------
# MIDI Writing
# -----------------------------

def write_midi(
    events: List[Tuple[float, int, int, float, int]],
    *,
    bpm: float,
    out_path: Path,
    program: int = 81,
    channel: int = 0,
) -> None:
    """Write events to a MIDI file."""
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Tempo meta
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    # Program change
    track.append(mido.Message("program_change", program=program, channel=channel, time=0))

    # Convert beats to ticks
    ticks_per_beat = mid.ticks_per_beat

    # Build note on/off messages with proper delta times
    # We'll convert each event into two messages: on and off.
    messages = []
    for t_beats, note, vel, dur_beats, ch in events:
        on_tick = int(round(t_beats * ticks_per_beat))
        off_tick = int(round((t_beats + dur_beats) * ticks_per_beat))

        messages.append((on_tick, 1, mido.Message("note_on", note=note, velocity=vel, channel=ch, time=0)))
        messages.append((off_tick, 0, mido.Message("note_off", note=note, velocity=0, channel=ch, time=0)))

    # Sort by tick then by type (off before on at same tick? we use priority)
    messages.sort(key=lambda x: (x[0], x[1]))

    last_tick = 0
    for tick, _, msg in messages:
        delta = max(0, tick - last_tick)
        msg.time = delta
        track.append(msg)
        last_tick = tick

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(out_path))


# -----------------------------
# CLI
# -----------------------------

def main() -> None:
    """Main entry point for CLI."""
    p = argparse.ArgumentParser(
        description="Rule-based Arpeggiator/Pad Generator v2.2"
    )

    # Required
    p.add_argument("--progression", required=True,
                   help='Chord progression, e.g., "Am | F | C | G"')

    # Output options
    p.add_argument("--bars", type=int, default=32,
                   help="Total bars to generate (default: 32)")
    p.add_argument("--bpm", type=float, default=120.0,
                   help="Tempo in BPM (default: 120)")
    p.add_argument("--time-signature", default="4/4",
                   help="Time signature, e.g., '4/4' or '3/4' (default: 4/4)")
    p.add_argument("--out", default="layer.mid",
                   help="Output MIDI file (default: layer.mid)")

    # Mode and style
    p.add_argument("--mode", choices=["arp", "pad"], default="arp",
                   help="Generation mode (default: arp)")
    p.add_argument("--style",
                   choices=["eighths", "sixteenths", "syncop", "pop_arp",
                            "alberti", "broken", "random_no_repeat"],
                   default="eighths",
                   help="Rhythm pattern (default: eighths)")
    p.add_argument("--motion",
                   choices=["up", "down", "updown", "random", "random_no_repeat"],
                   default="up",
                   help="Arp direction (default: up)")

    # Variation
    p.add_argument("--seed", type=int, default=None,
                   help="Random seed for reproducibility")

    # MIDI options
    p.add_argument("--program", type=int, default=81,
                   help="MIDI program number (default: 81 = Lead 2 Sawtooth)")
    p.add_argument("--channel", type=int, default=0,
                   help="MIDI channel 0-15 (default: 0)")

    # Voicing options
    p.add_argument("--octave", type=int, default=4,
                   help="Base octave for arp mode (default: 4 = around C4)")
    p.add_argument("--center-key", type=int, default=60,
                   help="Center key for pad voicing (default: 60=C4)")
    p.add_argument("--no-octave", action="store_true",
                   help="Disable upper octave extension for arp")

    # Note shaping
    p.add_argument("--gate", type=float, default=0.85,
                   help="Note duration as fraction of grid step (default: 0.85)")
    p.add_argument("--pad-legato", type=float, default=0.95,
                   help="Pad note duration factor (default: 0.95)")

    # Velocity shaping
    p.add_argument("--vel-base", type=int, default=75,
                   help="Base velocity (default: 75)")
    p.add_argument("--vel-accent", type=int, default=95,
                   help="Accent velocity on downbeats (default: 95)")
    p.add_argument("--vel-jitter", type=int, default=5,
                   help="Velocity jitter range (+/-) (default: 5)")

    # Logging
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable debug logging")

    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr
    )

    # Parse progression using shared parser
    try:
        progression = parse_progression(args.progression)
    except ValueError as e:
        log.error("Invalid progression: %s", e)
        raise SystemExit(2)

    # Parse time signature
    try:
        ts_num, ts_den = map(int, args.time_signature.strip().split('/'))
        ts = TimeSignature(numerator=ts_num, denominator=ts_den)
    except ValueError:
        log.error("Invalid time signature format. Use 'numerator/denominator' e.g. '4/4'")
        raise SystemExit(2)

    # Create style
    if args.mode == "pad":
        # Pad mode: ignore pattern, use voice leading
        style = ArpStyle(
            pattern_16=(1,) * 16,  # Dummy pattern (not used in pad mode)
            pattern_name="pad",
            gate=0.98,
            motion=args.motion,
            pad_legato=float(args.pad_legato)
        )
    else:
        # Arp mode: use selected pattern
        pat = pattern_for_style(args.style)
        style = ArpStyle(
            pattern_16=pat,
            pattern_name=str(args.style),
            gate=float(args.gate),
            vel_base=int(args.vel_base),
            vel_accent=int(args.vel_accent),
            vel_jitter=int(args.vel_jitter),
            motion=args.motion,
            include_octave=not args.no_octave,
            pad_legato=float(args.pad_legato)
        )

    # Generate events
    try:
        events = generate_events(
            progression,
            bars=int(args.bars),
            ts=ts,
            mode=args.mode,
            style=style,
            base_octave=int(args.octave),
            center_key=int(args.center_key),
            channel=int(args.channel),
            seed=args.seed,
        )
    except ValueError as e:
        log.error("Error generating events: %s", e)
        raise SystemExit(2)

    # Write MIDI
    out_path = Path(args.out).expanduser().resolve()
    write_midi(
        events,
        bpm=float(args.bpm),
        out_path=out_path,
        program=int(args.program),
        channel=int(args.channel),
    )

    log.info("Wrote MIDI: %s", out_path)


if __name__ == "__main__":
    main()
