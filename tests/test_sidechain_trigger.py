from pathlib import Path

import mido
import pytest

from bandleader.sidechain_trigger import export_trigger_midi, main


def _write_format1_midi(path: Path, *, kick_ticks, kick_note=36, tempo_change=None):
    """Write a format-1 MIDI: track 0 holds tempo, track 1 holds the notes."""
    mid = mido.MidiFile(ticks_per_beat=480)

    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    if tempo_change is not None:
        change_tick, change_bpm = tempo_change
        meta.append(
            mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(change_bpm), time=change_tick)
        )
    mid.tracks.append(meta)

    notes = mido.MidiTrack()
    last = 0
    for tick in kick_ticks:
        notes.append(mido.Message("note_on", note=kick_note, velocity=100, channel=9, time=tick - last))
        notes.append(mido.Message("note_off", note=kick_note, velocity=0, channel=9, time=10))
        last = tick + 10
    mid.tracks.append(notes)

    mid.save(str(path))


def _trigger_abs_ticks(path: Path):
    mid = mido.MidiFile(str(path))
    abs_tick = 0
    ons = []
    tempos = []
    for msg in mid.tracks[0]:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            ons.append(abs_tick)
        if msg.is_meta and msg.type == "set_tempo":
            tempos.append((abs_tick, msg.tempo))
    return ons, tempos


def test_kicks_in_secondary_track_are_found(tmp_path: Path):
    # Regression: only mid.tracks[0] was scanned, so format-1 MIDI with notes
    # in track 1+ produced an empty trigger file with no error.
    src = tmp_path / "drums.mid"
    out = tmp_path / "trigger.mid"
    _write_format1_midi(src, kick_ticks=[0, 480, 960])

    count = export_trigger_midi(input_midi=src, output_midi=out)

    assert count == 3
    ons, _ = _trigger_abs_ticks(out)
    assert ons == [0, 480, 960]


def test_mid_song_tempo_change_keeps_its_position(tmp_path: Path):
    # Regression: tempo messages were collapsed to tick 0, drifting the
    # rendered trigger WAV against the drums after any tempo change.
    src = tmp_path / "drums.mid"
    out = tmp_path / "trigger.mid"
    _write_format1_midi(src, kick_ticks=[0, 960], tempo_change=(480, 90))

    export_trigger_midi(input_midi=src, output_midi=out)

    _, tempos = _trigger_abs_ticks(out)
    assert (0, mido.bpm2tempo(120)) in tempos
    assert (480, mido.bpm2tempo(90)) in tempos


def test_cli_exits_nonzero_when_no_kicks_found(tmp_path: Path, monkeypatch):
    src = tmp_path / "drums.mid"
    out = tmp_path / "trigger.mid"
    # Only snare hits (note 38) — no kicks at the default kick note 36.
    _write_format1_midi(src, kick_ticks=[0, 480], kick_note=38)

    monkeypatch.setattr(
        "sys.argv",
        ["bandleader-sidechain", "--input-midi", str(src), "--output-midi", str(out)],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    # Regression (R32): the empty trigger file used to be written before the
    # zero-kick check, leaving a useless artifact behind on failure.
    assert not out.exists()
