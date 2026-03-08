import types


def _load_module(path: str, name: str):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    fake_mido = types.SimpleNamespace(
        bpm2tempo=lambda bpm: int(round(60_000_000 / bpm)),
        MidiFile=object,
        MidiTrack=list,
        Message=object,
        MetaMessage=object,
    )

    import sys

    sys.modules.setdefault("mido", fake_mido)
    module = types.ModuleType(name)
    module.__file__ = path
    sys.modules[name] = module
    exec(compile(source, path, "exec"), module.__dict__)
    return module.__dict__


def test_bass_time_signature_steps_cover_expected_values():
    bass = _load_module("bandleader/bass_generator.py", "bandleader.bass_generator")
    ts_cls = bass["TimeSignature"]

    assert ts_cls(4, 4).steps_per_bar == 16
    assert ts_cls(3, 4).steps_per_bar == 12
    assert ts_cls(6, 8).steps_per_bar == 12


def test_bass_event_generation_is_deterministic_with_seed():
    bass = _load_module("bandleader/bass_generator.py", "bandleader.bass_generator")
    ts_cls = bass["TimeSignature"]
    style_cls = bass["BassStyle"]
    gen = bass["generate_bass_events"]

    progression = [[(9, "min"), (7, "maj")]]
    style = style_cls(pattern_16=(1,) * 16)

    events_a = gen(progression, total_bars=4, ts=ts_cls(4, 4), style=style, seed=123)
    events_b = gen(progression, total_bars=4, ts=ts_cls(4, 4), style=style, seed=123)

    assert events_a == events_b


def test_arp_pad_segments_cover_entire_bar_without_zero_lengths():
    arp = _load_module("bandleader/arp_generator.py", "bandleader.arp_generator")
    compute_pad_segments = arp["compute_pad_segments"]

    bar_chords = [(0, "maj"), (2, "min"), (4, "maj"), (5, "maj"), (7, "maj")]
    segments = compute_pad_segments(bar_chords, 4)

    assert segments
    assert all(seg_len > 0 for _, _, _, seg_len in segments)
    assert sum(seg_len for _, _, _, seg_len in segments) == 4


def test_arp_generate_events_pad_mode_handles_dense_chords():
    arp = _load_module("bandleader/arp_generator.py", "bandleader.arp_generator")
    ts_cls = arp["TimeSignature"]
    style_cls = arp["ArpStyle"]
    generate_events = arp["generate_events"]

    progression = [[(0, "maj"), (2, "min"), (4, "maj"), (5, "maj"), (7, "maj")]]
    style = style_cls(pattern_16=(1,) * 16)

    events = generate_events(
        progression,
        bars=1,
        ts=ts_cls(3, 4),
        mode="pad",
        style=style,
        seed=42,
    )

    assert events
    # duration_beats at index 3
    assert all(e[3] > 0 for e in events)


def test_arp_event_generation_is_deterministic_with_seed():
    arp = _load_module("bandleader/arp_generator.py", "bandleader.arp_generator")
    ts_cls = arp["TimeSignature"]
    style_cls = arp["ArpStyle"]
    generate_events = arp["generate_events"]
    pattern_for_style = arp["pattern_for_style"]

    progression = [[(9, "min"), (5, "maj")]]
    style = style_cls(pattern_16=pattern_for_style("eighths"), motion="random_no_repeat", pattern_name="eighths")

    events_a = generate_events(progression, bars=2, ts=ts_cls(6, 8), mode="arp", style=style, seed=99)
    events_b = generate_events(progression, bars=2, ts=ts_cls(6, 8), mode="arp", style=style, seed=99)

    assert events_a == events_b
