"""Regression tests for temp-file handling in the audio cleaners.

convert_to_wav() once signaled "temp file we created" by the .temp.wav name
suffix alone, so an *input* literally named foo.temp.wav (e.g. leftover from
a previously killed run) was deleted by the caller's cleanup block.
"""

from pathlib import Path

import pytest

from bandleader import drum_cleaner, synth_cleaner


@pytest.mark.parametrize("module", [drum_cleaner, synth_cleaner])
def test_wav_input_is_never_flagged_as_temp(module, tmp_path: Path):
    wav_input = tmp_path / "stems.wav"
    wav_input.write_bytes(b"RIFF")

    path, created_temp = module.convert_to_wav(str(wav_input))

    assert Path(path) == wav_input
    assert created_temp is False


@pytest.mark.parametrize("module", [drum_cleaner, synth_cleaner])
def test_input_named_temp_wav_is_never_flagged_as_temp(module, tmp_path: Path):
    # The suffix-collision case: a user input that happens to match the
    # temp naming convention must not be marked for deletion.
    wav_input = tmp_path / "drums.temp.wav"
    wav_input.write_bytes(b"RIFF")

    path, created_temp = module.convert_to_wav(str(wav_input))

    assert Path(path) == wav_input
    assert created_temp is False
    assert wav_input.exists()


class _FakeAudio:
    """Stands in for pydub.AudioSegment so tests do not need ffmpeg."""

    def export(self, path, format):
        Path(path).write_bytes(b"converted-audio")


@pytest.mark.parametrize("module", [drum_cleaner, synth_cleaner])
def test_conversion_never_overwrites_existing_file(module, tmp_path: Path, monkeypatch):
    # Regression (R30): conversion used the fixed sibling path
    # <stem>.temp.wav, overwriting any pre-existing file there and then
    # deleting it during cleanup.
    monkeypatch.setattr(module, "PYDUB_AVAILABLE", True)
    monkeypatch.setattr(
        module, "AudioSegment", type("FakeSegment", (), {"from_file": staticmethod(lambda f: _FakeAudio())})
    )
    mp3_input = tmp_path / "song.mp3"
    mp3_input.write_bytes(b"ID3fake")
    preexisting = tmp_path / "song.temp.wav"
    preexisting.write_bytes(b"precious user data")

    path, created_temp = module.convert_to_wav(str(mp3_input))

    assert created_temp is True
    assert Path(path) != preexisting
    assert preexisting.read_bytes() == b"precious user data"
    assert Path(path).read_bytes() == b"converted-audio"


@pytest.mark.parametrize("module", [drum_cleaner, synth_cleaner])
def test_concurrent_conversions_use_distinct_temp_paths(module, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(module, "PYDUB_AVAILABLE", True)
    monkeypatch.setattr(
        module, "AudioSegment", type("FakeSegment", (), {"from_file": staticmethod(lambda f: _FakeAudio())})
    )
    mp3_input = tmp_path / "song.mp3"
    mp3_input.write_bytes(b"ID3fake")

    path_a, _ = module.convert_to_wav(str(mp3_input))
    path_b, _ = module.convert_to_wav(str(mp3_input))

    assert path_a != path_b
    assert Path(path_a).exists() and Path(path_b).exists()
