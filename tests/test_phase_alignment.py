import numpy as np
from scipy.io import wavfile

from bandleader.phase_alignment import align_wav_to_reference, estimate_lag


def test_estimate_lag_detects_positive_delay():
    sr = 48_000
    delay = 24
    rng = np.random.default_rng(123)
    reference = rng.normal(0.0, 1.0, size=4096).astype(np.float32)
    target = np.concatenate([np.zeros(delay, dtype=np.float32), reference[:-delay]])

    result = estimate_lag(reference, target, sample_rate=sr, max_shift_ms=5.0)

    assert result.lag_samples == delay
    assert result.confidence > 0.7


def test_estimate_lag_detects_negative_delay():
    sr = 48_000
    advance = 17
    rng = np.random.default_rng(321)
    reference = rng.normal(0.0, 1.0, size=4096).astype(np.float32)
    target = np.concatenate([reference[advance:], np.zeros(advance, dtype=np.float32)])

    result = estimate_lag(reference, target, sample_rate=sr, max_shift_ms=5.0)

    assert result.lag_samples == -advance
    assert result.confidence > 0.7


def test_estimate_lag_returns_zero_confidence_for_silence():
    sr = 48_000
    reference = np.zeros(2048, dtype=np.float32)
    target = np.zeros(2048, dtype=np.float32)

    result = estimate_lag(reference, target, sample_rate=sr, max_shift_ms=5.0)

    assert result.lag_samples == 0
    assert result.lag_ms == 0.0
    assert result.confidence == 0.0
    assert result.peak_correlation == 0.0


def test_estimate_lag_is_low_confidence_for_unrelated_noise():
    sr = 48_000
    rng = np.random.default_rng(7)
    reference = rng.normal(0.0, 1.0, size=4096).astype(np.float32)
    target = rng.normal(0.0, 1.0, size=4096).astype(np.float32)

    result = estimate_lag(reference, target, sample_rate=sr, max_shift_ms=5.0)

    assert result.confidence < 0.35


def test_estimate_lag_respects_max_shift_bound():
    sr = 48_000
    true_delay = 96
    max_shift_ms = 1.0  # 48 samples at 48kHz
    rng = np.random.default_rng(99)
    reference = rng.normal(0.0, 1.0, size=4096).astype(np.float32)
    target = np.concatenate([np.zeros(true_delay, dtype=np.float32), reference[:-true_delay]])

    result = estimate_lag(reference, target, sample_rate=sr, max_shift_ms=max_shift_ms)

    assert abs(result.lag_samples) <= 48


def test_align_wav_to_reference_applies_and_writes_output(tmp_path):
    sr = 48_000
    delay = 20
    rng = np.random.default_rng(2026)
    reference = rng.normal(0.0, 0.3, size=4096).astype(np.float32)
    target = np.concatenate([np.zeros(delay, dtype=np.float32), reference[:-delay]])

    ref_path = tmp_path / "ref.wav"
    tgt_path = tmp_path / "tgt.wav"
    out_path = tmp_path / "aligned.wav"
    wavfile.write(ref_path, sr, reference)
    wavfile.write(tgt_path, sr, target)

    result = align_wav_to_reference(
        ref_path,
        tgt_path,
        out_path,
        max_shift_ms=5.0,
        min_confidence=0.3,
    )

    assert result.applied is True
    assert out_path.exists()
    assert result.output_path == str(out_path)
    assert abs(result.lag_samples - delay) <= 1


def test_align_wav_to_reference_skips_on_low_confidence(tmp_path):
    sr = 48_000
    rng = np.random.default_rng(2027)
    reference = rng.normal(0.0, 0.3, size=4096).astype(np.float32)
    target = rng.normal(0.0, 0.3, size=4096).astype(np.float32)

    ref_path = tmp_path / "ref.wav"
    tgt_path = tmp_path / "tgt.wav"
    out_path = tmp_path / "aligned.wav"
    wavfile.write(ref_path, sr, reference)
    wavfile.write(tgt_path, sr, target)

    result = align_wav_to_reference(
        ref_path,
        tgt_path,
        out_path,
        max_shift_ms=5.0,
        min_confidence=0.95,
    )

    assert result.applied is False
    assert "low confidence" in result.reason
    assert not out_path.exists()


def test_align_wav_to_reference_preserves_int16_peaks_without_wrap(tmp_path):
    sr = 48_000
    reference = np.array([32767, -32768, 20000, -20000] * 256, dtype=np.int16)
    target = reference.copy()

    ref_path = tmp_path / "ref_i16.wav"
    tgt_path = tmp_path / "tgt_i16.wav"
    out_path = tmp_path / "aligned_i16.wav"
    wavfile.write(ref_path, sr, reference)
    wavfile.write(tgt_path, sr, target)

    result = align_wav_to_reference(
        ref_path,
        tgt_path,
        out_path,
        max_shift_ms=5.0,
        min_confidence=0.1,
    )
    assert result.applied is True
    out_sr, out_audio = wavfile.read(out_path)
    assert out_sr == sr
    assert out_audio.dtype == np.int16
    assert int(np.max(out_audio)) > 0


def test_align_wav_to_reference_handles_uint8_roundtrip(tmp_path):
    sr = 48_000
    # Unsigned 8-bit PCM, centered near 128.
    base = np.array([0, 64, 128, 192, 255] * 512, dtype=np.uint8)
    reference = base
    target = base.copy()

    ref_path = tmp_path / "ref_u8.wav"
    tgt_path = tmp_path / "tgt_u8.wav"
    out_path = tmp_path / "aligned_u8.wav"
    wavfile.write(ref_path, sr, reference)
    wavfile.write(tgt_path, sr, target)

    result = align_wav_to_reference(
        ref_path,
        tgt_path,
        out_path,
        max_shift_ms=5.0,
        min_confidence=0.1,
    )
    assert result.applied is True
    out_sr, out_audio = wavfile.read(out_path)
    assert out_sr == sr
    assert out_audio.dtype == np.uint8
