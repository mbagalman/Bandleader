#!/usr/bin/env python3
"""
Phase alignment helpers.

G2 scope:
- Deterministic lag estimation using normalized cross-correlation.
- Bounded lag search by max shift (ms).
- Confidence scoring for apply/skip gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate as _sp_correlate


@dataclass(frozen=True)
class LagEstimate:
    """Lag estimate where positive lag means target is later than reference."""

    lag_samples: int
    lag_ms: float
    confidence: float
    peak_correlation: float
    # True when a negative correlation peak is stronger than the best positive
    # one — a time shift cannot fix that (likely polarity inversion).
    polarity_suspect: bool = False


@dataclass(frozen=True)
class AlignmentResult:
    """Result of aligning a target wav to a reference wav."""

    applied: bool
    reason: str
    lag_samples: int
    lag_ms: float
    confidence: float
    peak_correlation: float
    output_path: str | None = None


def _to_mono_float32(signal: np.ndarray | list[float]) -> np.ndarray:
    """Convert mono/stereo-like inputs to a 1D float32 array."""
    arr = np.asarray(signal, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        if arr.shape[0] == 0:
            return np.asarray([], dtype=np.float32)
        # Average channels; supports shapes [samples, channels] and [channels, samples].
        if arr.shape[0] < arr.shape[1]:
            return arr.mean(axis=0, dtype=np.float32)
        return arr.mean(axis=1, dtype=np.float32)
    raise ValueError(f"Signal must be 1D or 2D, got shape {arr.shape}.")


def _shift_signal(signal: np.ndarray, lag_samples: int) -> np.ndarray:
    """
    Shift signal to compensate estimated lag while preserving length.

    Positive lag means signal is later -> shift earlier.
    Negative lag means signal is earlier -> shift later.
    """
    out = np.zeros_like(signal)
    n = signal.shape[0]
    if lag_samples > 0:
        if lag_samples >= n:
            return out
        out[: n - lag_samples] = signal[lag_samples:]
        return out
    if lag_samples < 0:
        shift = -lag_samples
        if shift >= n:
            return out
        out[shift:] = signal[: n - shift]
        return out
    return signal.copy()


def _to_float32(signal: np.ndarray) -> np.ndarray:
    if np.issubdtype(signal.dtype, np.floating):
        return signal.astype(np.float32, copy=False)
    if np.issubdtype(signal.dtype, np.integer):
        info = np.iinfo(signal.dtype)
        if np.issubdtype(signal.dtype, np.unsignedinteger):
            midpoint = float(info.max + 1) / 2.0
            return (signal.astype(np.float32) - midpoint) / midpoint
        scale = max(abs(info.min), abs(info.max))
        return signal.astype(np.float32) / float(scale)
    raise ValueError(f"Unsupported audio dtype: {signal.dtype}")


def _from_float32(signal: np.ndarray, dtype: np.dtype) -> np.ndarray:
    if np.issubdtype(dtype, np.floating):
        return signal.astype(dtype)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        clipped = np.clip(signal, -1.0, 1.0)
        if np.issubdtype(dtype, np.unsignedinteger):
            midpoint = float(info.max + 1) / 2.0
            scaled = np.round((clipped * midpoint) + midpoint)
            return np.clip(scaled, info.min, info.max).astype(dtype)

        # Preserve signed full-scale endpoints without overflowing positive peaks.
        scaled = np.where(
            clipped >= 0,
            clipped * float(info.max),
            clipped * float(abs(info.min)),
        )
        return np.clip(np.round(scaled), info.min, info.max).astype(dtype)
    raise ValueError(f"Unsupported audio dtype: {dtype}")


def estimate_lag(
    reference_signal: np.ndarray | list[float],
    target_signal: np.ndarray | list[float],
    *,
    sample_rate: int,
    max_shift_ms: float,
) -> LagEstimate:
    """
    Estimate relative lag between two signals using bounded normalized xcorr.

    Convention:
    - Positive lag: target occurs later than reference (shift target earlier to align).
    - Negative lag: target occurs earlier than reference.
    """
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError(f"sample_rate must be a positive integer, got {sample_rate!r}.")
    if not isinstance(max_shift_ms, (int, float)) or float(max_shift_ms) <= 0:
        raise ValueError(f"max_shift_ms must be a positive number, got {max_shift_ms!r}.")

    ref = _to_mono_float32(reference_signal)
    tgt = _to_mono_float32(target_signal)

    n = min(len(ref), len(tgt))
    if n < 2:
        return LagEstimate(lag_samples=0, lag_ms=0.0, confidence=0.0, peak_correlation=0.0)

    ref = ref[:n].astype(np.float32, copy=False)
    tgt = tgt[:n].astype(np.float32, copy=False)

    # Remove DC before correlation.
    ref = ref - float(ref.mean())
    tgt = tgt - float(tgt.mean())

    ref_rms = float(np.sqrt(np.mean(ref * ref)))
    tgt_rms = float(np.sqrt(np.mean(tgt * tgt)))
    if ref_rms < 1e-8 or tgt_rms < 1e-8:
        return LagEstimate(lag_samples=0, lag_ms=0.0, confidence=0.0, peak_correlation=0.0)

    # Windowing makes edge truncation more stable for deterministic lag picks.
    win = np.hanning(n).astype(np.float32) if n >= 8 else np.ones(n, dtype=np.float32)
    ref_w = ref * win
    tgt_w = tgt * win

    denom = float(np.linalg.norm(ref_w) * np.linalg.norm(tgt_w))
    if denom < 1e-8:
        return LagEstimate(lag_samples=0, lag_ms=0.0, confidence=0.0, peak_correlation=0.0)

    # FFT-based correlation: O(N log N) instead of O(N^2), which makes
    # full-length stems (minutes of 48 kHz audio) practical. Values match
    # direct correlation up to float rounding.
    corr = _sp_correlate(tgt_w, ref_w, mode="full", method="fft") / denom
    lags = np.arange(-n + 1, n, dtype=np.int32)

    max_shift_samples = int(round(float(max_shift_ms) * sample_rate / 1000.0))
    max_shift_samples = max(1, min(max_shift_samples, n - 1))
    in_bounds = np.abs(lags) <= max_shift_samples
    bounded_corr = corr[in_bounds]
    bounded_lags = lags[in_bounds]
    if bounded_corr.size == 0:
        return LagEstimate(lag_samples=0, lag_ms=0.0, confidence=0.0, peak_correlation=0.0)

    # Polarity policy: only POSITIVE correlation peaks are alignment
    # candidates. Time-shifting cannot fix an inverted-polarity target, and a
    # strong negative peak (e.g. target == -reference) must not be reported
    # as a confident match — it would shift periodic material toward
    # cancellation instead of coherence.
    pos_corr = np.maximum(bounded_corr, 0.0)
    best_idx = int(np.argmax(pos_corr))
    best_corr = float(pos_corr[best_idx])
    strongest_negative = float(max(0.0, -float(np.min(bounded_corr))))
    polarity_suspect = strongest_negative > best_corr

    if best_corr <= 1e-12:
        # No positively-correlated lag in bounds. Report the strongest peak
        # by magnitude (likely negative) for diagnostics, with zero
        # confidence so the apply gate always skips.
        mag_idx = int(np.argmax(np.abs(bounded_corr)))
        mag_lag = int(bounded_lags[mag_idx])
        return LagEstimate(
            lag_samples=mag_lag,
            lag_ms=(mag_lag * 1000.0) / sample_rate,
            confidence=0.0,
            peak_correlation=float(bounded_corr[mag_idx]),
            polarity_suspect=polarity_suspect,
        )

    best_lag = int(bounded_lags[best_idx])

    if pos_corr.size > 1:
        # Exclude a small neighborhood around the winning lag so the
        # "uniqueness" term compares against genuinely different lags, not
        # the adjacent samples of the same smooth correlation peak (which
        # would make the contrast term always ~0).
        exclusion = max(1, pos_corr.size // 20)
        masked = pos_corr.copy()
        lo = max(0, best_idx - exclusion)
        hi = min(pos_corr.size, best_idx + exclusion + 1)
        masked[lo:hi] = 0.0
        second_best = float(masked.max())
    else:
        second_best = 0.0
    peak_contrast = max(0.0, (best_corr - second_best) / (best_corr + 1e-12))

    # Confidence blends positive match strength with uniqueness of the winning lag.
    confidence = float(np.clip((0.75 * best_corr) + (0.25 * peak_contrast), 0.0, 1.0))
    lag_ms = (best_lag * 1000.0) / sample_rate

    return LagEstimate(
        lag_samples=best_lag,
        lag_ms=lag_ms,
        confidence=confidence,
        peak_correlation=best_corr,
        polarity_suspect=polarity_suspect,
    )


def align_wav_to_reference(
    reference_wav: Path,
    target_wav: Path,
    output_wav: Path,
    *,
    max_shift_ms: float,
    min_confidence: float,
) -> AlignmentResult:
    """Align target wav timing to reference wav using estimator + confidence gate."""
    ref_sr, ref_raw = wavfile.read(str(reference_wav))
    tgt_sr, tgt_raw = wavfile.read(str(target_wav))
    if int(ref_sr) != int(tgt_sr):
        return AlignmentResult(
            applied=False,
            reason=f"sample-rate mismatch ({ref_sr} vs {tgt_sr})",
            lag_samples=0,
            lag_ms=0.0,
            confidence=0.0,
            peak_correlation=0.0,
            output_path=None,
        )

    ref = _to_float32(np.asarray(ref_raw))
    tgt = _to_float32(np.asarray(tgt_raw))

    estimate = estimate_lag(
        _to_mono_float32(ref),
        _to_mono_float32(tgt),
        sample_rate=int(ref_sr),
        max_shift_ms=float(max_shift_ms),
    )
    if estimate.confidence < float(min_confidence):
        if estimate.polarity_suspect:
            reason = (
                f"low confidence ({estimate.confidence:.3f} < {float(min_confidence):.3f}); "
                "a negative correlation peak dominates — possible polarity inversion, "
                "which a time shift cannot fix"
            )
        else:
            reason = f"low confidence ({estimate.confidence:.3f} < {float(min_confidence):.3f})"
        return AlignmentResult(
            applied=False,
            reason=reason,
            lag_samples=estimate.lag_samples,
            lag_ms=estimate.lag_ms,
            confidence=estimate.confidence,
            peak_correlation=estimate.peak_correlation,
            output_path=None,
        )

    shifted = _shift_signal(tgt, estimate.lag_samples)
    out = _from_float32(shifted, np.asarray(tgt_raw).dtype)
    wavfile.write(str(output_wav), int(ref_sr), out)

    return AlignmentResult(
        applied=True,
        reason="applied",
        lag_samples=estimate.lag_samples,
        lag_ms=estimate.lag_ms,
        confidence=estimate.confidence,
        peak_correlation=estimate.peak_correlation,
        output_path=str(output_wav),
    )
