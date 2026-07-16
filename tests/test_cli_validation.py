"""CLI boundary validation for the public MIDI tools (R34).

Invalid values must fail at argparse time (exit code 2, no traceback) and
must not create any output file.
"""

from pathlib import Path

import pytest

from bandleader.arp_generator import main as arp_main
from bandleader.bass_generator import main as bass_main
from bandleader.sidechain_trigger import main as sidechain_main

BASS_BAD_ARGS = [
    ["--bars", "0"],
    ["--bars", "-4"],
    ["--bpm", "0"],
    ["--bpm", "-120"],
    ["--channel", "16"],
    ["--program", "128"],
    ["--legato", "1.5"],
    ["--weak-prob", "2"],
]

ARP_BAD_ARGS = [
    ["--bars", "0"],
    ["--bpm", "0"],
    ["--octave", "9"],
    ["--channel", "-1"],
    ["--program", "200"],
    ["--center-key", "128"],
    ["--vel-base", "0"],
    ["--vel-accent", "128"],
    ["--gate", "1.5"],
]

SIDECHAIN_BAD_ARGS = [
    ["--kick-note", "128"],
    ["--trigger-note", "-1"],
    ["--trigger-velocity", "0"],
    ["--trigger-length-ticks", "0"],
    ["--audio-gain", "11"],
]


def _run_expecting_argparse_error(monkeypatch, main, argv, out_path: Path):
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not out_path.exists()


@pytest.mark.parametrize("bad", BASS_BAD_ARGS, ids=lambda a: " ".join(a))
def test_bass_rejects_out_of_range_values(monkeypatch, tmp_path: Path, bad):
    out = tmp_path / "bass.mid"
    argv = ["bandleader-bass", "--progression", "C", "--out", str(out), *bad]
    _run_expecting_argparse_error(monkeypatch, bass_main, argv, out)


@pytest.mark.parametrize("bad", ARP_BAD_ARGS, ids=lambda a: " ".join(a))
def test_arp_rejects_out_of_range_values(monkeypatch, tmp_path: Path, bad):
    out = tmp_path / "arp.mid"
    argv = ["bandleader-arp", "--progression", "C", "--out", str(out), *bad]
    _run_expecting_argparse_error(monkeypatch, arp_main, argv, out)


@pytest.mark.parametrize("bad", SIDECHAIN_BAD_ARGS, ids=lambda a: " ".join(a))
def test_sidechain_rejects_out_of_range_values(monkeypatch, tmp_path: Path, bad):
    out = tmp_path / "trigger.mid"
    argv = [
        "bandleader-sidechain",
        "--input-midi", str(tmp_path / "drums.mid"),
        "--output-midi", str(out),
        *bad,
    ]
    _run_expecting_argparse_error(monkeypatch, sidechain_main, argv, out)


def test_bass_and_arp_valid_boundaries_still_work(monkeypatch, tmp_path: Path):
    bass_out = tmp_path / "bass.mid"
    monkeypatch.setattr("sys.argv", [
        "bandleader-bass", "--progression", "C", "--out", str(bass_out),
        "--bars", "1", "--bpm", "4", "--channel", "15", "--program", "127", "--seed", "1",
    ])
    bass_main()
    assert bass_out.exists()

    arp_out = tmp_path / "arp.mid"
    monkeypatch.setattr("sys.argv", [
        "bandleader-arp", "--progression", "C", "--out", str(arp_out),
        "--bars", "1", "--octave", "8", "--vel-base", "1", "--vel-accent", "127", "--seed", "1",
    ])
    arp_main()
    assert arp_out.exists()
