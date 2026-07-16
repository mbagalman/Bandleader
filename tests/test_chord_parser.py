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


def test_parse_quality_diminished_variants():
    # Regression: "Co7" once parsed as major because the dim regex required a
    # word boundary after 'o', which "o7" does not have.
    assert parse_quality("Co") == "dim"
    assert parse_quality("Co7") == "dim"
    assert parse_quality("C°7") == "dim"
    assert parse_quality("Cdim") == "dim"
    assert parse_quality("Cdim7") == "dim"


def test_parse_quality_common_variants():
    assert parse_quality("C") == "maj"
    assert parse_quality("Cmaj7") == "maj"
    assert parse_quality("Cm") == "min"
    assert parse_quality("C-") == "min"
    assert parse_quality("Cmin7") == "min"
    assert parse_quality("Caug") == "aug"
    assert parse_quality("C+") == "aug"
    assert parse_quality("Csus2") == "sus2"
    assert parse_quality("Csus4") == "sus4"
    assert parse_quality("Csus") == "sus4"
