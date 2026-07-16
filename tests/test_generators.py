from bandleader.arp_generator import (
    ArpStyle,
    TimeSignature as ArpTimeSignature,
    compute_pad_segments,
    generate_events,
    pattern_for_style,
)
from bandleader.bass_generator import (
    BassStyle,
    TimeSignature as BassTimeSignature,
    generate_bass_events,
)


def test_bass_time_signature_steps_cover_expected_values():
    assert BassTimeSignature(4, 4).steps_per_bar == 16
    assert BassTimeSignature(3, 4).steps_per_bar == 12
    assert BassTimeSignature(6, 8).steps_per_bar == 12


def test_bass_event_generation_is_deterministic_with_seed():
    progression = [[(9, "min"), (7, "maj")]]
    style = BassStyle(pattern_16=(1,) * 16)

    events_a = generate_bass_events(progression, total_bars=4, ts=BassTimeSignature(4, 4), style=style, seed=123)
    events_b = generate_bass_events(progression, total_bars=4, ts=BassTimeSignature(4, 4), style=style, seed=123)

    assert events_a == events_b


def test_arp_pad_segments_cover_entire_bar_without_zero_lengths():
    bar_chords = [(0, "maj"), (2, "min"), (4, "maj"), (5, "maj"), (7, "maj")]
    segments = compute_pad_segments(bar_chords, 4)

    assert segments
    assert all(seg_len > 0 for _, _, _, seg_len in segments)
    assert sum(seg_len for _, _, _, seg_len in segments) == 4


def test_arp_generate_events_pad_mode_handles_dense_chords():
    progression = [[(0, "maj"), (2, "min"), (4, "maj"), (5, "maj"), (7, "maj")]]
    style = ArpStyle(pattern_16=(1,) * 16)

    events = generate_events(
        progression,
        bars=1,
        ts=ArpTimeSignature(3, 4),
        mode="pad",
        style=style,
        seed=42,
    )

    assert events
    # duration_beats at index 3
    assert all(e[3] > 0 for e in events)


def test_arp_event_generation_is_deterministic_with_seed():
    progression = [[(9, "min"), (5, "maj")]]
    style = ArpStyle(pattern_16=pattern_for_style("eighths"), motion="random_no_repeat", pattern_name="eighths")

    events_a = generate_events(progression, bars=2, ts=ArpTimeSignature(6, 8), mode="arp", style=style, seed=99)
    events_b = generate_events(progression, bars=2, ts=ArpTimeSignature(6, 8), mode="arp", style=style, seed=99)

    assert events_a == events_b


def _arp_notes(motion: str, *, bars: int = 1, seed: int = 7) -> list[int]:
    """Generate one bar of C-major sixteenths and return the MIDI note sequence."""
    progression = [[(0, "maj")]]
    style = ArpStyle(
        pattern_16=pattern_for_style("sixteenths"),
        pattern_name="sixteenths",
        motion=motion,
    )
    events = generate_events(
        progression, bars=bars, ts=ArpTimeSignature(4, 4), mode="arp", style=style, seed=seed
    )
    return [e[1] for e in sorted(events, key=lambda e: e[0])]


def test_arp_up_motion_ascends_through_both_octaves():
    # Octave-doubled C major cycle from octave 4: C4 E4 G4 C5 E5 G5, repeating.
    assert _arp_notes("up")[:6] == [60, 64, 67, 72, 76, 79]


def test_arp_down_motion_descends_from_the_top_octave():
    # Regression: octave offsets were applied by position counter, not by the
    # selected cycle index, so "down" ascended in register.
    notes = _arp_notes("down")[:6]
    assert notes == [79, 76, 72, 67, 64, 60]
    assert notes == sorted(notes, reverse=True)


def test_arp_updown_motion_bounces_without_octave_glitches():
    # Cycle of 6 -> bounce period 10: indices 0..5 then 4..1.
    notes = _arp_notes("updown", bars=1)
    assert notes[:10] == [60, 64, 67, 72, 76, 79, 76, 72, 67, 64]


def test_arp_random_motions_stay_in_range_and_no_repeat_holds():
    for motion in ("random", "random_no_repeat"):
        notes = _arp_notes(motion, bars=4)
        assert all(0 <= n <= 127 for n in notes)
    no_repeat = _arp_notes("random_no_repeat", bars=4)
    # Regression: index tracking by pitch-class value allowed the same audible
    # note (same pc AND same octave) to repeat back-to-back.
    assert all(a != b for a, b in zip(no_repeat, no_repeat[1:]))


def test_arp_gate_zero_does_not_produce_zero_duration_events():
    style = ArpStyle(
        pattern_16=pattern_for_style("eighths"),
        pattern_name="eighths",
        gate=0.0,
    )
    events = generate_events(
        [[(0, "maj")]], bars=1, ts=ArpTimeSignature(4, 4), mode="arp", style=style, seed=1
    )
    assert events
    # write_midi enforces a 1-tick minimum; the event durations themselves may
    # be zero, which is what that guard exists for.
    from bandleader.arp_generator import write_midi
    import mido
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "gate0.mid"
        write_midi(events, bpm=120.0, out_path=out)
        mid = mido.MidiFile(str(out))
        ons = sum(1 for m in mid.tracks[0] if m.type == "note_on")
        offs = sum(1 for m in mid.tracks[0] if m.type == "note_off")
        assert ons == offs
        # Every note_off must come strictly after its note_on (no stuck notes).
        open_notes = set()
        for msg in mid.tracks[0]:
            if msg.type == "note_on":
                open_notes.add(msg.note)
            elif msg.type == "note_off":
                assert msg.time > 0 or msg.note in open_notes
                open_notes.discard(msg.note)
        assert not open_notes


def _pad_velocities(*, vel_base=75, vel_accent=95, vel_jitter=0, seed=3) -> list[int]:
    """One bar, two chords -> one downbeat segment and one mid-bar segment."""
    style = ArpStyle(
        pattern_16=(1,) * 16,
        pattern_name="pad",
        vel_base=vel_base,
        vel_accent=vel_accent,
        vel_jitter=vel_jitter,
    )
    events = generate_events(
        [[(0, "maj"), (7, "maj")]],
        bars=1,
        ts=ArpTimeSignature(4, 4),
        mode="pad",
        style=style,
        seed=seed,
    )
    by_time: dict[float, int] = {}
    for t, _note, vel, _dur, _ch in events:
        by_time[t] = vel
    return [by_time[t] for t in sorted(by_time)]


def test_pad_mode_honors_vel_base_and_accent():
    # Regression (R33): pad events used only vel_base; vel_accent and
    # vel_jitter were copied into ArpStyle but dead.
    downbeat, midbar = _pad_velocities(vel_base=60, vel_accent=110, vel_jitter=0)
    assert downbeat == 110
    assert midbar == 60


def test_pad_mode_jitter_is_seeded_and_alive():
    flat = _pad_velocities(vel_base=64, vel_accent=64, vel_jitter=0)
    jittered_a = _pad_velocities(vel_base=64, vel_accent=64, vel_jitter=20, seed=11)
    jittered_b = _pad_velocities(vel_base=64, vel_accent=64, vel_jitter=20, seed=11)

    assert jittered_a == jittered_b  # deterministic under a fixed seed
    assert jittered_a != flat  # jitter actually changes output
    assert all(1 <= v <= 127 for v in jittered_a)
