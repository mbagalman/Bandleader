#!/usr/bin/env python3
"""
Safe stem cleaner (FFmpeg-based, 80/20, do-no-harm defaults).

Philosophy:
- Improve common "fuzzy stem" issues (rumble, hiss/fizz, uneven level) without changing musical intent.
- NO pitch correction, NO timing changes, NO aggressive gating, NO heavy denoise by default.

Approach:
- Chain: High-pass -> (optional LPF) -> (optional De-ess) -> Gentle Comp -> Limiter -> Dry/Wet Mix -> Final Loudness Norm

Requirements:
- ffmpeg installed and on PATH

Examples:
  bandleader-stems input.wav --stem vocal
  bandleader-stems input.wav --stem vocal --mix 0.8 --normalize
  bandleader-stems input.mp3 --stem bass --strength medium

Batch processing (bash):
  for f in *.wav; do bandleader-stems "$f" --stem vocal --overwrite; done
"""

import argparse
import logging
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


# Presets: store compressor values in dB for readability; convert to linear in build_wet_chain().
PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "vocal": {
        "low": {
            "hpf_hz": 90,
            "lpf_hz": 16000,
            "use_lpf": True,
            "comp_threshold_db": -22,
            "comp_ratio": 2.0,
            "comp_attack_ms": 15,
            "comp_release_ms": 200,
            "comp_makeup_db": 2.5,
            "limiter_ceiling": 0.98,
        },
        "medium": {
            "hpf_hz": 110,
            "lpf_hz": 16000,
            "use_lpf": True,
            "comp_threshold_db": -24,
            "comp_ratio": 2.5,
            "comp_attack_ms": 12,
            "comp_release_ms": 250,
            "comp_makeup_db": 3.5,
            "limiter_ceiling": 0.98,
        },
        "high": {
            "hpf_hz": 120,
            "lpf_hz": 16000,
            "use_lpf": True,
            "comp_threshold_db": -28,
            "comp_ratio": 3.0,
            "comp_attack_ms": 10,
            "comp_release_ms": 300,
            "comp_makeup_db": 4.0,
            "limiter_ceiling": 0.97,
        },
    },
    "guitar": {
        "low": {
            "hpf_hz": 90,
            "lpf_hz": 14000,
            "use_lpf": True,
            "comp_threshold_db": -22,
            "comp_ratio": 2.0,
            "comp_attack_ms": 20,
            "comp_release_ms": 250,
            "comp_makeup_db": 2.0,
            "limiter_ceiling": 0.98,
        },
        "medium": {
            "hpf_hz": 110,
            "lpf_hz": 14000,
            "use_lpf": True,
            "comp_threshold_db": -24,
            "comp_ratio": 2.3,
            "comp_attack_ms": 18,
            "comp_release_ms": 300,
            "comp_makeup_db": 3.0,
            "limiter_ceiling": 0.98,
        },
        "high": {
            "hpf_hz": 120,
            "lpf_hz": 14000,
            "use_lpf": True,
            "comp_threshold_db": -28,
            "comp_ratio": 2.8,
            "comp_attack_ms": 15,
            "comp_release_ms": 300,
            "comp_makeup_db": 4.0,
            "limiter_ceiling": 0.97,
        },
    },
    "bass": {
        "low": {
            "hpf_hz": 35,
            "lpf_hz": 14000,
            "use_lpf": False,
            "comp_threshold_db": -20,
            "comp_ratio": 2.0,
            "comp_attack_ms": 25,
            "comp_release_ms": 200,
            "comp_makeup_db": 2.0,
            "limiter_ceiling": 0.98,
        },
        "medium": {
            "hpf_hz": 40,
            "lpf_hz": 12000,
            "use_lpf": False,
            "comp_threshold_db": -22,
            "comp_ratio": 2.5,
            "comp_attack_ms": 20,
            "comp_release_ms": 220,
            "comp_makeup_db": 3.0,
            "limiter_ceiling": 0.98,
        },
        "high": {
            "hpf_hz": 45,
            "lpf_hz": 12000,
            "use_lpf": False,
            "comp_threshold_db": -26,
            "comp_ratio": 3.0,
            "comp_attack_ms": 15,
            "comp_release_ms": 260,
            "comp_makeup_db": 4.0,
            "limiter_ceiling": 0.97,
        },
    },
    "other": {
        "low": {
            "hpf_hz": 60,
            "lpf_hz": 14000,
            "use_lpf": True,
            "comp_threshold_db": -22,
            "comp_ratio": 2.0,
            "comp_attack_ms": 20,
            "comp_release_ms": 250,
            "comp_makeup_db": 2.0,
            "limiter_ceiling": 0.98,
        },
        "medium": {
            "hpf_hz": 80,
            "lpf_hz": 12000,
            "use_lpf": True,
            "comp_threshold_db": -24,
            "comp_ratio": 2.3,
            "comp_attack_ms": 18,
            "comp_release_ms": 280,
            "comp_makeup_db": 3.0,
            "limiter_ceiling": 0.98,
        },
        "high": {
            "hpf_hz": 90,
            "lpf_hz": 12000,
            "use_lpf": True,
            "comp_threshold_db": -28,
            "comp_ratio": 2.8,
            "comp_attack_ms": 15,
            "comp_release_ms": 300,
            "comp_makeup_db": 4.0,
            "limiter_ceiling": 0.97,
        },
    },
}


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH. Install ffmpeg and try again.")


def get_input_info(path: Path) -> Optional[str]:
    """Get basic audio format info via ffprobe."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate",
                "-of", "csv=p=0", str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        parts = result.stdout.strip().split(",")
        if len(parts) >= 3:
            codec = parts[0]
            sample_rate = parts[1]
            channels = parts[2]
            bit_rate = parts[3] if len(parts) > 3 and parts[3] else "unknown"
            ch_label = "mono" if channels == "1" else f"{channels}ch"
            br_label = f"{int(bit_rate)//1000}kbps" if bit_rate.isdigit() else ""
            return f"{codec}, {sample_rate} Hz, {ch_label}" + (f", {br_label}" if br_label else "")
        return result.stdout.strip() or None
    except Exception:
        return None


def ffmpeg_supports_filter(filter_name: str) -> bool:
    """Best-effort detection check."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True, text=True, check=True,
        )
        return filter_name in proc.stdout
    except Exception:
        return False


def db_to_linear(db: float) -> float:
    """Convert decibels to linear amplitude multiplier."""
    return 10.0 ** (float(db) / 20.0)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def build_wet_chain(
    preset: Dict[str, Any],
    *,
    enable_deess: bool,
    force_lpf: Optional[bool],
) -> str:
    """
    Build the processing chain (EQ -> Comp -> Limit).
    NO mixing or normalization happens here.
    """
    parts = []

    # High-pass
    hpf_hz = int(preset["hpf_hz"])
    parts.append(f"highpass=f={hpf_hz}")

    # Low-pass (optional)
    use_lpf = bool(preset.get("use_lpf", True))
    if force_lpf is not None:
        use_lpf = bool(force_lpf)
    if use_lpf:
        lpf_hz = int(preset["lpf_hz"])
        parts.append(f"lowpass=f={lpf_hz}")

    # De-ess (optional)
    # ffmpeg deesser params: i = intensity (0-1), f = frequency as a fraction
    # of the sibilance band (0-1, NOT Hz), s = output source enum (i/o/e).
    if enable_deess:
        parts.append("deesser=i=0.2:f=0.5:s=o")

    # Compressor
    # Convert dB presets to LINEAR for FFmpeg acompressor
    raw_thresh_linear = db_to_linear(float(preset["comp_threshold_db"]))
    thresh_linear = clamp(raw_thresh_linear, 0.001, 1.0)

    raw_makeup_linear = db_to_linear(float(preset["comp_makeup_db"]))
    makeup_linear = clamp(raw_makeup_linear, 1.0, 3.0)

    # Debug warnings for clamped values
    if abs(thresh_linear - raw_thresh_linear) > 1e-12:
        log.debug("Comp threshold clamped %.4f -> %.4f", raw_thresh_linear, thresh_linear)
    if abs(makeup_linear - raw_makeup_linear) > 1e-12:
        log.debug("Comp makeup clamped %.3f -> %.3f", raw_makeup_linear, makeup_linear)

    comp = (
        "acompressor="
        f"threshold={thresh_linear:.6f}:"
        f"ratio={float(preset['comp_ratio'])}:"
        f"attack={int(preset['comp_attack_ms'])}:"
        f"release={int(preset['comp_release_ms'])}:"
        f"makeup={makeup_linear:.6f}"
    )
    parts.append(comp)

    # Safety limiter
    parts.append(f"alimiter=limit={float(preset['limiter_ceiling'])}")

    return ",".join(parts)


def build_final_filter(
    wet_chain: str,
    *,
    mix: float,
) -> str:
    """
    Combine dry + wet paths via amix.
    CRITICAL: Uses :normalize=0 to prevent 6dB volume drop.
    """
    mix = clamp(float(mix), 0.0, 1.0)
    if mix >= 0.999999:
        return wet_chain
    if mix <= 0.000001:
        return "anull"

    dry_weight = 1.0 - mix
    wet_weight = mix

    return (
        f"asplit=2[dry][wet];"
        f"[wet]{wet_chain}[wetp];"
        f"[dry]volume={dry_weight:.6f}[dryw];"
        f"[wetp]volume={wet_weight:.6f}[wetw];"
        f"[dryw][wetw]amix=inputs=2:duration=longest:weights=1 1:normalize=0"
    )


def build_loudnorm_filter(*, target_lufs: float, target_true_peak: float, target_lra: float) -> str:
    """Build a loudnorm filter string from explicit target parameters."""
    return f"loudnorm=I={float(target_lufs)}:TP={float(target_true_peak)}:LRA={float(target_lra)}"


def run_ffmpeg(
    input_path: Path,
    output_path: Path,
    audio_filter: str,
    *,
    sample_rate: Optional[int],
    bit_depth: int,
    overwrite: bool,
    log_path: Optional[Path] = None,
    audit_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Execute ffmpeg.

    Args:
        log_path: If provided, write the exact ffmpeg command to this file
                  for reproducibility/audit trail.
    """
    if bit_depth not in (16, 24, 32):
        raise ValueError("bit_depth must be one of: 16, 24, 32")

    pcm_codec = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}[bit_depth]

    cmd = ["ffmpeg"]
    cmd.append("-y" if overwrite else "-n")
    cmd += [
        "-hide_banner", "-loglevel", "error",
        "-i", str(input_path),
        "-vn",
        "-af", audio_filter,
        "-c:a", pcm_codec,
    ]

    if sample_rate:
        cmd += ["-ar", str(sample_rate)]

    # Resolve to an absolute path so a filename starting with '-' cannot be
    # parsed as an ffmpeg option (the output is a bare positional argument).
    cmd.append(str(Path(output_path).resolve()))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip() or "Unknown ffmpeg error"
        raise RuntimeError(err)

    # Write command + settings to the audit file only after ffmpeg succeeds,
    # so a leftover audit log always reflects a run that actually produced
    # the output. shlex quoting keeps paths with spaces replayable.
    if log_path is not None:
        try:
            lines = []
            if audit_metadata:
                for key, val in audit_metadata.items():
                    lines.append(f"# {key}: {val}")
            lines.append(shlex.join(cmd))
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log.debug("ffmpeg command written to: %s", log_path)
        except OSError as e:
            log.debug("Could not write ffmpeg log file: %s", e)


def main() -> None:
    """Console-script entry point: run with friendly fatal-error reporting."""
    try:
        _run_cli()
    except Exception as e:
        log.error("Error: %s", e)
        sys.exit(1)


def _run_cli() -> None:
    parser = argparse.ArgumentParser(description="Safe stem cleaner using ffmpeg with conservative presets.")
    parser.add_argument("input_file", help="Input audio file")
    parser.add_argument("--stem", choices=["vocal", "guitar", "bass", "other"], default="other")
    parser.add_argument("--strength", choices=["low", "medium", "high"], default="low")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--overwrite", action="store_true")

    # UX
    parser.add_argument("--preview", action="store_true", help="Show filter chain only")
    parser.add_argument("--mix", type=float, default=1.0, help="Dry/wet mix 0.0-1.0")

    # Options
    parser.add_argument("--deess", action="store_true", help="Enable light de-essing")
    parser.add_argument("--normalize", action="store_true", help="Enable loudness normalization")
    parser.add_argument("--target-lufs", "--lufs", dest="target_lufs", type=float, default=-18.0)
    parser.add_argument("--target-true-peak", "--true-peak", dest="target_true_peak", type=float, default=-1.5)
    parser.add_argument("--target-lra", "--lra", dest="target_lra", type=float, default=11.0)

    # Format
    parser.add_argument("--sample-rate", type=int, default=None)
    parser.add_argument("--bit-depth", type=int, default=24)
    parser.add_argument(
        "--wav", action="store_true",
        help="Force WAV output (ensures .wav extension even if --output specifies another extension)"
    )

    # LPF
    lpf_group = parser.add_mutually_exclusive_group()
    lpf_group.add_argument("--no-lpf", action="store_true")
    lpf_group.add_argument("--force-lpf", action="store_true")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    check_ffmpeg()

    input_path = Path(args.input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_clean.wav")

    # --wav flag: force .wav extension on output
    if args.wav:
        output_path = output_path.with_suffix(".wav")

    preset = PRESETS[args.stem][args.strength]

    # De-ess Check
    enable_deess = bool(args.deess)
    if enable_deess:
        if args.stem != "vocal":
            log.info("--deess is usually only appropriate for vocals.")
        if ffmpeg_supports_filter("deesser") is False:
            log.warning("`deesser` filter not found. If execution fails, try without --deess.")

    force_lpf = False if args.no_lpf else (True if args.force_lpf else None)

    # 1. Build Wet Processing Chain
    wet_chain = build_wet_chain(
        preset,
        enable_deess=enable_deess,
        force_lpf=force_lpf,
    )

    # 2. Combine with Dry (Parallel Mix)
    audio_filter = build_final_filter(wet_chain, mix=float(args.mix))

    # 3. Apply Global Normalization (Post-Mix)
    if args.normalize:
        lufs_filter = build_loudnorm_filter(
            target_lufs=float(args.target_lufs),
            target_true_peak=float(args.target_true_peak),
            target_lra=float(args.target_lra),
        )
        audio_filter += f",{lufs_filter}"

    # Info & Preview
    log.info("Input : %s", input_path)
    info = get_input_info(input_path)
    if info:
        log.info("Info  : %s", info)
    log.info("Output: %s", output_path)
    log.info("Preset: %s / %s / Mix: %s", args.stem, args.strength, args.mix)
    if args.normalize:
        log.info(
            "Norm  : enabled (target LUFS=%s, true peak=%s dBTP, LRA=%s)",
            args.target_lufs,
            args.target_true_peak,
            args.target_lra,
        )
    log.debug("Chain : %s", audio_filter)

    if args.preview:
        # In preview mode, print the chain to stdout so callers can inspect it
        print(audio_filter)
        return

    # Determine log file path (named after output stem for uniqueness)
    ffmpeg_log_path = output_path.with_suffix(".ffmpeg.txt")
    audit_metadata = {
        "stem": args.stem,
        "strength": args.strength,
        "mix": args.mix,
        "normalize": args.normalize,
        "target_lufs": args.target_lufs,
        "target_true_peak": args.target_true_peak,
        "target_lra": args.target_lra,
        "sample_rate": args.sample_rate,
        "bit_depth": args.bit_depth,
    }

    # Execution (with De-ess Retry)
    try:
        run_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            audio_filter=audio_filter,
            sample_rate=args.sample_rate,
            bit_depth=int(args.bit_depth),
            overwrite=bool(args.overwrite),
            log_path=ffmpeg_log_path,
            audit_metadata=audit_metadata,
        )
    except RuntimeError as e:
        msg = str(e)
        if enable_deess and ("deesser" in msg or "No such filter" in msg or "not found" in msg):
            log.warning(
                "FFmpeg failed with the deesser filter (likely missing from this "
                "ffmpeg build). Retrying WITHOUT de-essing — output will not be "
                "de-essed. FFmpeg error was: %s",
                msg,
            )
            # Rebuild without deess
            wet_retry = build_wet_chain(preset, enable_deess=False, force_lpf=force_lpf)
            filter_retry = build_final_filter(wet_retry, mix=float(args.mix))
            if args.normalize:
                filter_retry += "," + build_loudnorm_filter(
                    target_lufs=float(args.target_lufs),
                    target_true_peak=float(args.target_true_peak),
                    target_lra=float(args.target_lra),
                )

            run_ffmpeg(
                input_path=input_path,
                output_path=output_path,
                audio_filter=filter_retry,
                sample_rate=args.sample_rate,
                bit_depth=int(args.bit_depth),
                overwrite=bool(args.overwrite),
                log_path=ffmpeg_log_path,
                audit_metadata=audit_metadata,
            )
        else:
            raise

    log.info("Done.")


if __name__ == "__main__":
    main()
