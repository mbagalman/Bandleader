from bandleader.chord_parser import (
    parse_bass_pc,
    parse_progression_full,
    parse_quality,
    parse_root_pc,
    triad_pcs,
)


def test_parse_root_pc_handles_sharp_and_flat_accidentals():
    assert parse_root_pc("C#") == 1
    assert parse_root_pc("Db") == 1


def test_parse_quality_ignores_slash_bass_and_detects_minor():
    assert parse_quality("Am/C") == "min"


def test_parse_progression_full_returns_bass_pc_for_slash_chord():
    out = parse_progression_full("C/G | Am")
    assert out[0][0] == (0, "maj", 7)
    assert out[1][0] == (9, "min", None)


def test_triad_pcs_supports_dim_quality():
    assert triad_pcs(11, "dim") == [11, 2, 5]


def test_parse_bass_pc_returns_none_without_slash():
    assert parse_bass_pc("Fmaj7") is None
