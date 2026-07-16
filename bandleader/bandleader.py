#!/usr/bin/env python3
"""
Bandleader pipeline orchestrator.

Reads a single 'song_config.yaml' source of truth, processes existing stems,
generates new layers, and renders a preview mix in one pass.

Usage:
  bandleader ./my_song_folder
  python -m bandleader ./my_song_folder
"""

import logging
import os
import sys
import copy
import re
import json
import yaml
import shlex
import subprocess
import argparse
import shutil
from pathlib import Path
from bandleader.phase_alignment import AlignmentResult, align_wav_to_reference

log = logging.getLogger(__name__)

# --- Configuration Template ---
EXAMPLE_CONFIG = """
song:
  bpm: 120
  time_signature: 4/4
  progression: "Am G | F | C G"
  bars: 32
  seed: 0

stems:
  drums: "drums"
  vocals: "vocals"
  synth: "synth"
  overheads: "overheads"
  guitars: "guitars"

soundfonts:
  drums: "/path/to/drums.sf2"
  bass: "/path/to/bass.sf2"
  arp: "/path/to/arp.sf2"
  synth: "/path/to/synth.sf2"

pipeline:
  clean_drums:
    enabled: true
    export_sidechain_trigger: false

  clean_vocals:
    enabled: true
    normalize: false
    target_lufs: -18.0
    target_true_peak: -1.5
    target_lra: 11.0

  generate_bass:
    enabled: true
    style: "two_feel"
    sidechain_ducking: false
    ducking_depth: 0.35
    ducking_attack_ms: 10.0
    ducking_release_ms: 120.0

  generate_arp:
    enabled: false
    style: "eighths"
    motion: "updown"

  phase_align:
    enabled: false
    max_shift_ms: 12.0
    min_confidence: 0.35
    pair_kick_bass: true
    pair_snare_overheads: false
    pair_bass_guitars: false

  clean_synth:
    enabled: false
"""

# --- Helpers ---

PIPELINE_DEFAULTS = {
    "clean_drums": {"enabled": False, "export_sidechain_trigger": False},
    "clean_vocals": {
        "enabled": False,
        "normalize": False,
        "target_lufs": -18.0,
        "target_true_peak": -1.5,
        "target_lra": 11.0,
    },
    "generate_bass": {
        "enabled": False,
        "style": "two_feel",
        "sidechain_ducking": False,
        "ducking_depth": 0.35,
        "ducking_attack_ms": 10.0,
        "ducking_release_ms": 120.0,
    },
    "generate_arp": {"enabled": False, "style": "eighths", "motion": "updown"},
    "phase_align": {
        "enabled": False,
        "max_shift_ms": 12.0,
        "min_confidence": 0.35,
        "pair_kick_bass": True,
        "pair_snare_overheads": False,
        "pair_bass_guitars": False,
    },
    "clean_synth": {"enabled": False},
}

STEM_DEFAULTS = {"drums": "drums", "vocals": "vocals", "synth": "synth"}
OPTIONAL_STEM_DEFAULTS = {"overheads": "overheads", "guitars": "guitars"}
SOUNDFONT_KEYS = {"drums", "bass", "arp", "synth"}

BASS_STYLES = {"two_feel", "four_on_floor", "eighths", "disco"}
ARP_STYLES = {"eighths", "sixteenths", "syncop", "pop_arp", "alberti", "broken", "random_no_repeat"}
ARP_MOTIONS = {"up", "down", "updown", "random", "random_no_repeat"}
TIME_SIGNATURE_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def load_config(folder: Path) -> dict:
    config_path = folder / "song_config.yaml"
    if not config_path.exists():
        log.error("Missing song_config.yaml in %s", folder)
        log.info("Example config:\n%s", EXAMPLE_CONFIG.strip())
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            log.error("Config error: %s is not valid YAML.", config_path)
            log.error("%s", e)
            log.error("Fix the YAML syntax (check indentation and quoting) and re-run.")
            sys.exit(1)
    return config


def _is_number(value) -> bool:
    """True for int/float but not bool (bool is an int subclass in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_config(config: dict) -> dict:
    """Validate and normalize config with user-friendly, key-level errors."""
    errors: list[str] = []

    def add_error(path: str, msg: str) -> None:
        errors.append(f"{path}: {msg}")

    def require_dict(node: dict, key: str, *, default: dict | None = None) -> dict:
        if key not in node:
            if default is not None:
                node[key] = copy.deepcopy(default)
            else:
                add_error(key, "section is required.")
                node[key] = {}
        val = node.get(key)
        if not isinstance(val, dict):
            add_error(key, f"must be a mapping/object, got {type(val).__name__}.")
            node[key] = {}
        return node[key]

    if not isinstance(config, dict):
        log.error("Config error: song_config.yaml is empty or not valid YAML.")
        sys.exit(1)

    normalized = copy.deepcopy(config)
    allowed_top_level = {"song", "stems", "soundfonts", "pipeline"}
    for key in normalized.keys():
        if key not in allowed_top_level:
            log.warning("Unknown top-level config key ignored: %s", key)

    song = require_dict(normalized, "song")
    stems = require_dict(normalized, "stems", default=STEM_DEFAULTS)
    soundfonts = require_dict(normalized, "soundfonts", default={})
    pipeline = require_dict(normalized, "pipeline", default=PIPELINE_DEFAULTS)

    if "bpm" not in song:
        add_error("song.bpm", "is required and must be a positive number (e.g. 120).")
    elif not (_is_number(song["bpm"]) and song["bpm"] > 0):
        add_error("song.bpm", f"must be a positive number, got {song['bpm']!r}.")

    if "progression" not in song:
        add_error("song.progression", 'is required and must be a non-empty string (e.g. "Am G | F | C").')
    elif not (isinstance(song["progression"], str) and song["progression"].strip()):
        add_error("song.progression", f"must be a non-empty string, got {song['progression']!r}.")

    if "bars" not in song:
        add_error("song.bars", "is required and must be a positive integer (e.g. 32).")
    elif not (isinstance(song["bars"], int) and not isinstance(song["bars"], bool) and song["bars"] > 0):
        add_error("song.bars", f"must be a positive integer, got {song['bars']!r}.")

    seed = song.get("seed", 0)
    if not (isinstance(seed, int) and not isinstance(seed, bool)):
        add_error("song.seed", f"must be an integer, got {seed!r}.")
        seed = 0
    song["seed"] = seed

    ts = str(song.get("time_signature", "4/4")).strip()
    song["time_signature"] = ts
    m = TIME_SIGNATURE_RE.match(ts)
    if not m:
        add_error("song.time_signature", f"must match 'numerator/denominator', got {ts!r}.")
    else:
        num, den = int(m.group(1)), int(m.group(2))
        if num <= 0 or den <= 0:
            add_error("song.time_signature", "numerator and denominator must be positive integers.")

    for stem_key, default_keyword in STEM_DEFAULTS.items():
        val = stems.get(stem_key, default_keyword)
        if not isinstance(val, str) or not val.strip():
            add_error(f"stems.{stem_key}", f"must be a non-empty string keyword, got {val!r}.")
        stems[stem_key] = val if isinstance(val, str) and val.strip() else default_keyword
    for stem_key, default_keyword in OPTIONAL_STEM_DEFAULTS.items():
        if stem_key not in stems:
            continue
        val = stems.get(stem_key, default_keyword)
        if not isinstance(val, str) or not val.strip():
            add_error(f"stems.{stem_key}", f"must be a non-empty string keyword, got {val!r}.")
            stems[stem_key] = default_keyword

    for key, val in list(soundfonts.items()):
        if key not in SOUNDFONT_KEYS:
            log.warning("Ignoring unknown soundfont key: %s", key)
            soundfonts.pop(key, None)
            continue
        if not isinstance(val, str) or not val.strip():
            add_error(f"soundfonts.{key}", f"must be a non-empty path string, got {val!r}.")

    for step, defaults in PIPELINE_DEFAULTS.items():
        raw_step = pipeline.get(step, copy.deepcopy(defaults))
        if not isinstance(raw_step, dict):
            add_error(f"pipeline.{step}", f"must be a mapping/object, got {type(raw_step).__name__}.")
            raw_step = copy.deepcopy(defaults)

        merged = copy.deepcopy(defaults)
        merged.update(raw_step)

        if not isinstance(merged.get("enabled"), bool):
            add_error(f"pipeline.{step}.enabled", f"must be true/false, got {merged.get('enabled')!r}.")
            merged["enabled"] = bool(defaults["enabled"])

        if step == "clean_drums":
            if not isinstance(merged.get("export_sidechain_trigger"), bool):
                add_error(
                    "pipeline.clean_drums.export_sidechain_trigger",
                    f"must be true/false, got {merged.get('export_sidechain_trigger')!r}.",
                )
                merged["export_sidechain_trigger"] = defaults["export_sidechain_trigger"]
        elif step == "clean_vocals":
            if not isinstance(merged.get("normalize"), bool):
                add_error(
                    "pipeline.clean_vocals.normalize",
                    f"must be true/false, got {merged.get('normalize')!r}.",
                )
                merged["normalize"] = defaults["normalize"]
            for key in ("target_lufs", "target_true_peak", "target_lra"):
                val = merged.get(key, defaults[key])
                if not _is_number(val):
                    add_error(
                        f"pipeline.clean_vocals.{key}",
                        f"must be a number, got {val!r}.",
                    )
                    merged[key] = defaults[key]
                else:
                    merged[key] = float(val)
        elif step == "generate_bass":
            style = merged.get("style", defaults["style"])
            if style not in BASS_STYLES:
                add_error(
                    "pipeline.generate_bass.style",
                    f"must be one of {sorted(BASS_STYLES)}, got {style!r}.",
                )
                merged["style"] = defaults["style"]
            if not isinstance(merged.get("sidechain_ducking"), bool):
                add_error(
                    "pipeline.generate_bass.sidechain_ducking",
                    f"must be true/false, got {merged.get('sidechain_ducking')!r}.",
                )
                merged["sidechain_ducking"] = defaults["sidechain_ducking"]

            ducking_depth = merged.get("ducking_depth", defaults["ducking_depth"])
            if not _is_number(ducking_depth) or not (0.0 <= float(ducking_depth) <= 1.0):
                add_error(
                    "pipeline.generate_bass.ducking_depth",
                    f"must be a number between 0.0 and 1.0, got {ducking_depth!r}.",
                )
                merged["ducking_depth"] = defaults["ducking_depth"]
            else:
                merged["ducking_depth"] = float(ducking_depth)

            for key in ("ducking_attack_ms", "ducking_release_ms"):
                value = merged.get(key, defaults[key])
                if not _is_number(value) or float(value) <= 0:
                    add_error(
                        f"pipeline.generate_bass.{key}",
                        f"must be a positive number, got {value!r}.",
                    )
                    merged[key] = defaults[key]
                else:
                    merged[key] = float(value)
        elif step == "generate_arp":
            style = merged.get("style", defaults["style"])
            motion = merged.get("motion", defaults["motion"])
            if style not in ARP_STYLES:
                add_error(
                    "pipeline.generate_arp.style",
                    f"must be one of {sorted(ARP_STYLES)}, got {style!r}.",
                )
                merged["style"] = defaults["style"]
            if motion not in ARP_MOTIONS:
                add_error(
                    "pipeline.generate_arp.motion",
                    f"must be one of {sorted(ARP_MOTIONS)}, got {motion!r}.",
                )
                merged["motion"] = defaults["motion"]
        elif step == "phase_align":
            max_shift_ms = merged.get("max_shift_ms", defaults["max_shift_ms"])
            if not _is_number(max_shift_ms) or float(max_shift_ms) <= 0:
                add_error(
                    "pipeline.phase_align.max_shift_ms",
                    f"must be a positive number, got {max_shift_ms!r}.",
                )
                merged["max_shift_ms"] = defaults["max_shift_ms"]
            else:
                merged["max_shift_ms"] = float(max_shift_ms)

            min_confidence = merged.get("min_confidence", defaults["min_confidence"])
            if not _is_number(min_confidence) or not (0.0 <= float(min_confidence) <= 1.0):
                add_error(
                    "pipeline.phase_align.min_confidence",
                    f"must be a number between 0.0 and 1.0, got {min_confidence!r}.",
                )
                merged["min_confidence"] = defaults["min_confidence"]
            else:
                merged["min_confidence"] = float(min_confidence)

            for key in ("pair_kick_bass", "pair_snare_overheads", "pair_bass_guitars"):
                if not isinstance(merged.get(key), bool):
                    add_error(
                        f"pipeline.phase_align.{key}",
                        f"must be true/false, got {merged.get(key)!r}.",
                    )
                    merged[key] = defaults[key]

        pipeline[step] = merged

    for step in list(pipeline.keys()):
        if step not in PIPELINE_DEFAULTS:
            log.warning("Unknown pipeline step ignored: pipeline.%s", step)
            pipeline.pop(step, None)

    enabled_steps = [k for k, v in pipeline.items() if isinstance(v, dict) and v.get("enabled")]
    if not enabled_steps:
        log.warning("No pipeline steps are enabled; nothing will be processed.")

    if errors:
        log.error("Config validation failed with %d issue(s):", len(errors))
        for err in errors:
            log.error("  - %s", err)
        log.info("Example config:\n%s", EXAMPLE_CONFIG.strip())
        sys.exit(1)

    return normalized


def ensure_tools_for_enabled_steps(pipe: dict) -> None:
    """
    Validate external tools for enabled steps only.
    This avoids blocking partial pipelines that do not require all tools.
    """
    tool_requirements = {
        "ffmpeg": ["clean_vocals"],
        "fluidsynth": ["clean_drums", "generate_bass", "generate_arp", "clean_synth"],
    }
    if pipe.get("generate_bass", {}).get("enabled") and pipe.get("generate_bass", {}).get("sidechain_ducking"):
        tool_requirements["ffmpeg"].append("generate_bass")
    missing_by_tool: dict[str, list[str]] = {}
    for tool, steps in tool_requirements.items():
        enabled_steps = [step for step in steps if pipe.get(step, {}).get("enabled")]
        if enabled_steps and not shutil.which(tool):
            missing_by_tool[tool] = enabled_steps

    if not missing_by_tool:
        return

    for tool, steps in missing_by_tool.items():
        log.error(
            "Missing required tool '%s' for enabled step(s): %s",
            tool,
            ", ".join(steps),
        )
    log.error("Please install missing tools and ensure they are on your PATH.")
    sys.exit(1)


def get_soundfont(config: dict, folder: Path, key: str) -> str | None:
    """Resolve soundfont path from config, relative to the song folder if needed.

    Logs the specific failure cause (not configured vs configured-but-missing)
    so callers only need a generic skip/abort message.
    """
    sf_path_str = config.get("soundfonts", {}).get(key)
    if not sf_path_str:
        log.warning("No '%s' soundfont configured (set soundfonts.%s in song_config.yaml).", key, key)
        return None
    sf_path = Path(sf_path_str)
    if not sf_path.is_absolute():
        sf_path = folder / sf_path
    if sf_path.exists():
        return str(sf_path)
    log.error("Configured '%s' soundfont does not exist: %s", key, sf_path)
    return None


def _subprocess_env() -> dict:
    """
    Ensure subprocesses can import `bandleader` when invoked via `python -m ...`.
    Only injects the project root to PYTHONPATH if running directly from the source tree.
    """
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parent.parent
    
    if (repo_root / "pyproject.toml").exists():
        env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    
    return env


def find_file(folder: Path, keyword: str) -> Path | None:
    """
    Deterministic fuzzy filename search within the song folder tree recursively.
    Uses case-insensitive python matching to avoid glob OS-differences.
    """
    kw = (keyword or "").strip().lower()
    if not kw:
        return None

    candidates = []
    for f in folder.rglob("*"):
        # Explicitly skip generated files to prevent recursion loops
        if "generated" in f.parts:
            continue
        if f.suffix.lower() not in (".wav", ".mp3"):
            continue
            
        name = f.stem.lower()

        if name == kw:
            match_rank = 0
        elif name.startswith(kw):
            match_rank = 1
        elif kw in name:
            match_rank = 2
        else:
            continue  # Must at least contain the keyword

        suffix_rank = 0 if f.suffix.lower() == ".wav" else 1
        candidates.append((match_rank, suffix_rank, len(f.name), f.name.lower(), f))

    if not candidates:
        return None

    ranked = sorted(candidates, key=lambda t: (*t[:4], str(t[4]).lower()))
    best = ranked[0]
    tied = [c for c in ranked if c[:4] == best[:4]]
    if len(tied) > 1:
        sample = ", ".join(str(c[4].relative_to(folder)) for c in tied[:3])
        log.warning(
            "Ambiguous stem match for keyword=%r. Using %s (other equivalent matches: %s).",
            kw,
            best[4].relative_to(folder),
            sample,
        )
    return best[4]


def run_command(cmd_parts: list, *, env: dict | None = None) -> bool:
    """Execute a subprocess command."""
    cmd_str = shlex.join(str(p) for p in cmd_parts)
    log.info("Executing: %s", cmd_str)
    try:
        completed = subprocess.run(
            cmd_parts,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        if completed.stdout:
            log.debug("stdout:\n%s", completed.stdout.rstrip())
        if completed.stderr:
            log.debug("stderr:\n%s", completed.stderr.rstrip())
        return True
    except FileNotFoundError:
        log.error("Command not found while executing: %s", cmd_str)
        return False
    except subprocess.CalledProcessError as e:
        stdout = (e.stdout or "").rstrip()
        stderr = (e.stderr or "").rstrip()
        if stderr:
            log.error("Command failed (stderr):\n%s", stderr)
        else:
            log.error("Command failed with no stderr output.")
        if stdout:
            log.debug("Command failed (stdout):\n%s", stdout)
        return False


def build_preview_mix_filter(num_inputs: int) -> str:
    """Build a robust ffmpeg filter graph for preview mixing."""
    if num_inputs <= 0:
        raise ValueError("num_inputs must be >= 1")
    normalized_inputs = []
    for i in range(num_inputs):
        normalized_inputs.append(
            f"[{i}:a]aresample=async=1,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
            f"[a{i}]"
        )
    mix_inputs = "".join(f"[a{i}]" for i in range(num_inputs))
    return (
        ";".join(normalized_inputs)
        + ";"
        + f"{mix_inputs}amix=inputs={num_inputs}:duration=longest:dropout_transition=0,"
        "alimiter=limit=0.95[mix]"
    )


def build_stem_cleaner_cmd(input_path: Path, output_path: Path, step_cfg: dict) -> list[str]:
    """Build stem_cleaner subprocess args from validated config."""
    cmd = [
        sys.executable,
        "-m",
        "bandleader.stem_cleaner",
        str(input_path),
        "--output",
        str(output_path),
        "--stem",
        "vocal",
        "--overwrite",
    ]
    if step_cfg.get("normalize"):
        cmd.extend(
            [
                "--normalize",
                "--target-lufs",
                str(step_cfg.get("target_lufs", -18.0)),
                "--target-true-peak",
                str(step_cfg.get("target_true_peak", -1.5)),
                "--target-lra",
                str(step_cfg.get("target_lra", 11.0)),
            ]
        )
    return cmd


def build_sidechain_trigger_cmd(
    source_midi: Path,
    output_midi: Path,
    output_wav: Path,
    soundfont: str,
) -> list[str]:
    """Build sidechain trigger export command args."""
    return [
        sys.executable,
        "-m",
        "bandleader.sidechain_trigger",
        "--input-midi",
        str(source_midi),
        "--output-midi",
        str(output_midi),
        "--render-audio",
        str(output_wav),
        "--soundfont",
        str(soundfont),
    ]


def build_bass_ducking_cmd(
    bass_wav: Path,
    key_wav: Path,
    output_wav: Path,
    bass_cfg: dict,
) -> list[str]:
    """Build ffmpeg sidechain-compression command args for bass ducking."""
    depth = float(bass_cfg.get("ducking_depth", 0.35))
    attack_ms = float(bass_cfg.get("ducking_attack_ms", 10.0))
    release_ms = float(bass_cfg.get("ducking_release_ms", 120.0))

    # Depth controls ratio/threshold with conservative defaults to reduce pumping risk.
    ratio = 1.5 + (depth * 5.0)
    threshold = 0.12 - (depth * 0.06)

    filter_complex = (
        "[0:a][1:a]sidechaincompress="
        f"threshold={threshold:.3f}:"
        f"ratio={ratio:.2f}:"
        f"attack={attack_ms:.1f}:"
        f"release={release_ms:.1f}:"
        "knee=2.5:makeup=1[ducked]"
    )

    return [
        "ffmpeg",
        "-y",
        "-i",
        str(bass_wav),
        "-i",
        str(key_wav),
        "-filter_complex",
        filter_complex,
        "-map",
        "[ducked]",
        str(output_wav),
    ]


def run_phase_alignment_pair(
    pair_label: str,
    reference_audio: Path | None,
    target_audio: Path | None,
    output_audio: Path,
    phase_cfg: dict,
) -> AlignmentResult:
    """Run one phase-alignment pair with isolated failure handling."""
    if not reference_audio or not reference_audio.exists():
        log.warning("%s alignment skipped: reference source missing.", pair_label)
        return AlignmentResult(
            applied=False,
            reason="reference source missing",
            lag_samples=0,
            lag_ms=0.0,
            confidence=0.0,
            peak_correlation=0.0,
            output_path=None,
        )
    if not target_audio or not target_audio.exists():
        log.warning("%s alignment skipped: target source missing.", pair_label)
        return AlignmentResult(
            applied=False,
            reason="target source missing",
            lag_samples=0,
            lag_ms=0.0,
            confidence=0.0,
            peak_correlation=0.0,
            output_path=None,
        )
    not_wav = next(
        (p for p in (reference_audio, target_audio) if p.suffix.lower() != ".wav"),
        None,
    )
    if not_wav is not None:
        log.warning(
            "%s alignment skipped: %s is not a WAV file (phase alignment requires WAV input).",
            pair_label,
            not_wav.name,
        )
        return AlignmentResult(
            applied=False,
            reason=f"not a WAV file: {not_wav.name}",
            lag_samples=0,
            lag_ms=0.0,
            confidence=0.0,
            peak_correlation=0.0,
            output_path=None,
        )
    try:
        alignment = align_wav_to_reference(
            reference_audio,
            target_audio,
            output_audio,
            max_shift_ms=float(phase_cfg.get("max_shift_ms", 12.0)),
            min_confidence=float(phase_cfg.get("min_confidence", 0.35)),
        )
    except Exception as e:
        log.warning("%s alignment failed: %s", pair_label, e)
        return AlignmentResult(
            applied=False,
            reason=f"exception: {e}",
            lag_samples=0,
            lag_ms=0.0,
            confidence=0.0,
            peak_correlation=0.0,
            output_path=None,
        )

    if alignment.applied and output_audio.exists():
        log.info(
            "%s alignment applied: lag=%d samples (%.2f ms), confidence=%.3f -> %s",
            pair_label,
            alignment.lag_samples,
            alignment.lag_ms,
            alignment.confidence,
            output_audio.name,
        )
        return alignment

    log.warning(
        "%s alignment skipped: %s (lag=%d, confidence=%.3f).",
        pair_label,
        alignment.reason,
        alignment.lag_samples,
        alignment.confidence,
    )
    return alignment


def select_alignment_preview_source(
    alignment: AlignmentResult,
    aligned_output: Path,
    dry_target: Path | None,
) -> Path | None:
    """Pick the preview-mix source for an alignment pair.

    The aligned output is preferred only when alignment was actually applied;
    on any skip or failure the dry target is used, so enabling an alignment
    pair never removes an available stem from the preview.
    """
    if alignment.applied and aligned_output.exists():
        return aligned_output
    if dry_target is not None and dry_target.exists():
        return dry_target
    return None


def build_phase_alignment_report_entry(
    pair: str,
    reference_audio: Path | None,
    target_audio: Path | None,
    result: AlignmentResult,
) -> dict:
    """Build one alignment report entry."""
    return {
        "pair": pair,
        "reference": str(reference_audio) if reference_audio else None,
        "target": str(target_audio) if target_audio else None,
        "applied": bool(result.applied),
        "reason": result.reason,
        "lag_samples": int(result.lag_samples),
        "lag_ms": float(result.lag_ms),
        "confidence": float(result.confidence),
        "peak_correlation": float(result.peak_correlation),
        "output": result.output_path,
    }


def write_phase_alignment_report(gen_dir: Path, entries: list[dict]) -> Path | None:
    """Write alignment report JSON when alignment pairs were attempted."""
    if not entries:
        return None
    report_path = gen_dir / "phase_alignment_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"attempted_pairs": entries}, f, indent=2)
    return report_path


# --- Pipeline ---


def main() -> None:
    parser = argparse.ArgumentParser(description="The Bandleader: Audio Pipeline Orchestrator")
    parser.add_argument("folder", help="Folder containing stems and song_config.yaml")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )

    folder = Path(args.folder).resolve()
    if not folder.exists():
        log.error("Folder not found: %s", folder)
        sys.exit(1)

    log.info("--- The Bandleader: Auditioning %s ---", folder.name)
    config = validate_config(load_config(folder))

    song = config["song"]
    pipe = config.get("pipeline", {})
    ensure_tools_for_enabled_steps(pipe)

    gen_dir = folder / "generated"
    gen_dir.mkdir(exist_ok=True)

    generated_audio = []
    sidechain_key_audio: Path | None = None
    drums_reference_audio: Path | None = None
    dry_bass_audio: Path | None = None
    phase_alignment_entries: list[dict] = []
    env = _subprocess_env()

    # 1. DRUMS (Clean)
    if pipe.get("clean_drums", {}).get("enabled"):
        drum_keyword = config.get("stems", {}).get("drums", "drums")
        drum_file = find_file(folder, drum_keyword)
        if not drum_file:
            log.error("Drum stem not found (keyword=%r).", drum_keyword)
            sys.exit(1)

        sf2_drums = get_soundfont(config, folder, "drums")
        if not sf2_drums:
            log.error("Cannot run drum cleaning without a usable 'drums' soundfont. Aborting.")
            sys.exit(1)

        log.info("[*] Cleaning Drums: %s", drum_file.name)
        drum_cfg = pipe["clean_drums"]
        cleaned_path = gen_dir / f"gen_{drum_file.stem}_clean.wav"
        midi_out_path = gen_dir / f"gen_{drum_file.stem}_drums.mid"
        
        cmd = [
            sys.executable, "-m", "bandleader.drum_cleaner",
            str(drum_file),
            "--soundfont", sf2_drums,
            "--output", str(cleaned_path),
            "--tempo", str(song["bpm"]),
            "--midi-output", str(midi_out_path)
        ]

        if not run_command(cmd, env=env):
            log.error("Drum cleaning failed; aborting.")
            sys.exit(1)

        if drum_cfg.get("export_sidechain_trigger"):
            trigger_midi = gen_dir / "gen_sidechain_trigger.mid"
            trigger_wav = gen_dir / "gen_sidechain_trigger.wav"
            sidechain_cmd = build_sidechain_trigger_cmd(midi_out_path, trigger_midi, trigger_wav, sf2_drums)
            if run_command(sidechain_cmd, env=env):
                log.info("Sidechain trigger exported: %s and %s", trigger_midi.name, trigger_wav.name)
                if trigger_wav.exists():
                    sidechain_key_audio = trigger_wav
            else:
                log.warning("Sidechain trigger export failed. Continuing pipeline.")

        if cleaned_path.exists():
            generated_audio.append(cleaned_path)
            drums_reference_audio = cleaned_path
            if sidechain_key_audio is None:
                sidechain_key_audio = cleaned_path

    # 2. VOCALS (Stem Clean)
    if pipe.get("clean_vocals", {}).get("enabled"):
        vocals_keyword = config.get("stems", {}).get("vocals", "vocals")
        vocal_file = find_file(folder, vocals_keyword)
        if not vocal_file:
            log.error("Vocal stem not found (keyword=%r).", vocals_keyword)
            sys.exit(1)

        log.info("[*] Cleaning Vocals: %s", vocal_file.name)
        cleaned_path = gen_dir / f"gen_{vocal_file.stem}_clean.wav"
        cmd = build_stem_cleaner_cmd(vocal_file, cleaned_path, pipe["clean_vocals"])
        if not run_command(cmd, env=env):
            log.error("Vocal cleaning failed; aborting.")
            sys.exit(1)

        if cleaned_path.exists():
            generated_audio.append(cleaned_path)

    # 3. BASS (Generate & Render)
    if pipe.get("generate_bass", {}).get("enabled"):
        log.info("[*] Generating Bass...")
        sf2_bass = get_soundfont(config, folder, "bass")
        if not sf2_bass:
            log.warning("Bass layer skipped: no usable 'bass' soundfont.")
        else:
            bass_cfg = pipe["generate_bass"]
            midi_out = gen_dir / "gen_bass.mid"
            wav_out = gen_dir / "gen_bass.wav"
            
            cmd = [
                sys.executable, "-m", "bandleader.bass_generator",
                "--bpm", str(song["bpm"]),
                "--time-signature", str(song.get("time_signature", "4/4")),
                "--progression", str(song["progression"]),
                "--bars", str(song["bars"]),
                "--out", str(midi_out),
                "--style", str(bass_cfg.get("style", "two_feel")),
                "--seed", str(song.get("seed", 0))
            ]
            if run_command(cmd, env=env) and midi_out.exists():
                log.info("[*] Rendering Bass MIDI to WAV...")
                fs_cmd = ["fluidsynth", "-ni", "-g", "0.5", "-T", "wav", "-F", str(wav_out), sf2_bass, str(midi_out)]
                if run_command(fs_cmd, env=env) and wav_out.exists():
                    generated_audio.append(wav_out)
                    dry_bass_audio = wav_out

                    phase_cfg = pipe.get("phase_align", {})
                    if phase_cfg.get("enabled") and phase_cfg.get("pair_kick_bass"):
                        aligned_out = gen_dir / "gen_bass_aligned.wav"
                        alignment = run_phase_alignment_pair(
                            "Kick-bass",
                            sidechain_key_audio,
                            dry_bass_audio,
                            aligned_out,
                            phase_cfg,
                        )
                        phase_alignment_entries.append(
                            build_phase_alignment_report_entry(
                                "kick_bass",
                                sidechain_key_audio,
                                dry_bass_audio,
                                alignment,
                            )
                        )
                        selected = select_alignment_preview_source(alignment, aligned_out, dry_bass_audio)
                        if selected is not None:
                            generated_audio[-1] = selected

                    if bass_cfg.get("sidechain_ducking"):
                        ducked_out = gen_dir / "gen_bass_ducked.wav"
                        if sidechain_key_audio and sidechain_key_audio.exists():
                            bass_duck_source = generated_audio[-1]
                            duck_cmd = build_bass_ducking_cmd(
                                bass_duck_source,
                                sidechain_key_audio,
                                ducked_out,
                                bass_cfg,
                            )
                            if run_command(duck_cmd, env=env) and ducked_out.exists():
                                generated_audio[-1] = ducked_out
                                log.info("Generated sidechain-ducked bass stem: %s", ducked_out.name)
                            else:
                                log.warning("Bass ducking failed; keeping dry bass only.")
                        else:
                            log.warning("Bass ducking enabled but no sidechain key source found; keeping dry bass only.")
                else:
                    log.warning("FluidSynth rendering failed for Bass.")
            else:
                log.warning("Bass generation failed. Continuing pipeline.")

    # 4. ARP (Generate & Render)
    if pipe.get("generate_arp", {}).get("enabled"):
        log.info("[*] Generating Arp...")
        sf2_arp = get_soundfont(config, folder, "arp")
        if not sf2_arp:
            log.warning("Arp layer skipped: no usable 'arp' soundfont.")
        else:
            arp_cfg = pipe["generate_arp"]
            midi_out = gen_dir / "gen_arp.mid"
            wav_out = gen_dir / "gen_arp.wav"

            cmd = [
                sys.executable, "-m", "bandleader.arp_generator",
                "--bpm", str(song["bpm"]),
                "--time-signature", str(song.get("time_signature", "4/4")),
                "--progression", str(song["progression"]),
                "--bars", str(song["bars"]),
                "--out", str(midi_out),
                "--style", str(arp_cfg.get("style", "eighths")),
                "--motion", str(arp_cfg.get("motion", "updown")),
                "--seed", str(song.get("seed", 0))
            ]
            if run_command(cmd, env=env) and midi_out.exists():
                log.info("[*] Rendering Arp MIDI to WAV...")
                fs_cmd = ["fluidsynth", "-ni", "-g", "0.5", "-T", "wav", "-F", str(wav_out), sf2_arp, str(midi_out)]
                if run_command(fs_cmd, env=env) and wav_out.exists():
                    generated_audio.append(wav_out)
                else:
                    log.warning("FluidSynth rendering failed for Arp.")
            else:
                log.warning("Arp generation failed. Continuing pipeline.")

    # 5. SYNTH (Clean)
    if pipe.get("clean_synth", {}).get("enabled"):
        synth_keyword = config.get("stems", {}).get("synth", "synth")
        synth_file = find_file(folder, synth_keyword)
        sf2_synth = get_soundfont(config, folder, "synth")

        if not synth_file:
            log.warning("Synth stem not found. Skipping synth layer.")
        elif not sf2_synth:
            log.warning("Synth layer skipped: no usable 'synth' soundfont.")
        else:
            log.info("[*] Cleaning Synth: %s", synth_file.name)
            cleaned_path = gen_dir / f"gen_{synth_file.stem}_clean.wav"
            cmd = [
                sys.executable, "-m", "bandleader.synth_cleaner",
                str(synth_file),
                "--soundfont", sf2_synth,
                "--output", str(cleaned_path),
                "--tempo", str(song["bpm"])
            ]
            if run_command(cmd, env=env) and cleaned_path.exists():
                generated_audio.append(cleaned_path)
            else:
                log.warning("Synth cleaning failed. Continuing pipeline.")

    # 5.5 PHASE ALIGNMENT (Secondary Pairs)
    phase_cfg = pipe.get("phase_align", {})
    if phase_cfg.get("enabled"):
        if phase_cfg.get("pair_snare_overheads"):
            overheads_keyword = config.get("stems", {}).get("overheads", "overheads")
            overheads_file = find_file(folder, overheads_keyword)
            if not overheads_file:
                log.warning(
                    "Snare-overheads alignment enabled but overheads stem not found (keyword=%r).",
                    overheads_keyword,
                )
                phase_alignment_entries.append(
                    build_phase_alignment_report_entry(
                        "snare_overheads",
                        drums_reference_audio,
                        None,
                        AlignmentResult(
                            applied=False,
                            reason=f"target stem not found (keyword={overheads_keyword!r})",
                            lag_samples=0,
                            lag_ms=0.0,
                            confidence=0.0,
                            peak_correlation=0.0,
                            output_path=None,
                        ),
                    )
                )
            else:
                overheads_out = gen_dir / f"gen_{overheads_file.stem}_aligned.wav"
                # Use dry cleaned drums as snare proxy to avoid chained drift.
                alignment = run_phase_alignment_pair(
                    "Snare-overheads",
                    drums_reference_audio,
                    overheads_file,
                    overheads_out,
                    phase_cfg,
                )
                phase_alignment_entries.append(
                    build_phase_alignment_report_entry(
                        "snare_overheads",
                        drums_reference_audio,
                        overheads_file,
                        alignment,
                    )
                )
                preview_source = select_alignment_preview_source(alignment, overheads_out, overheads_file)
                if preview_source is not None:
                    generated_audio.append(preview_source)

        if phase_cfg.get("pair_bass_guitars"):
            guitars_keyword = config.get("stems", {}).get("guitars", "guitars")
            guitars_file = find_file(folder, guitars_keyword)
            if not guitars_file:
                log.warning(
                    "Bass-guitars alignment enabled but guitars stem not found (keyword=%r).",
                    guitars_keyword,
                )
                phase_alignment_entries.append(
                    build_phase_alignment_report_entry(
                        "bass_guitars",
                        dry_bass_audio,
                        None,
                        AlignmentResult(
                            applied=False,
                            reason=f"target stem not found (keyword={guitars_keyword!r})",
                            lag_samples=0,
                            lag_ms=0.0,
                            confidence=0.0,
                            peak_correlation=0.0,
                            output_path=None,
                        ),
                    )
                )
            else:
                guitars_out = gen_dir / f"gen_{guitars_file.stem}_aligned.wav"
                # Reference dry bass to prevent compounded drift from prior aligned passes.
                alignment = run_phase_alignment_pair(
                    "Bass-guitars",
                    dry_bass_audio,
                    guitars_file,
                    guitars_out,
                    phase_cfg,
                )
                phase_alignment_entries.append(
                    build_phase_alignment_report_entry(
                        "bass_guitars",
                        dry_bass_audio,
                        guitars_file,
                        alignment,
                    )
                )
                preview_source = select_alignment_preview_source(alignment, guitars_out, guitars_file)
                if preview_source is not None:
                    generated_audio.append(preview_source)

        report_path = write_phase_alignment_report(gen_dir, phase_alignment_entries)
        if report_path:
            log.info("Phase alignment report: %s", report_path)

    # 6. MIX PREVIEW
    if generated_audio:
        log.info("[*] Mixing Preview...")
        if not shutil.which("ffmpeg"):
            log.warning("Skipping preview mix: ffmpeg is not available on PATH.")
            log.info("  Stems:   %s", gen_dir / "gen_*.wav")
            log.info("  Folder:  %s", gen_dir)
            return
        inputs = []
        for audio in generated_audio:
            inputs.extend(["-i", str(audio)])
        filter_complex = build_preview_mix_filter(len(generated_audio))

        def try_preview(preview_path: Path) -> bool:
            cmd = [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                filter_complex,
                "-map",
                "[mix]",
                str(preview_path),
            ]
            return run_command(cmd, env=env) and preview_path.exists()

        # MP3 needs an encoder (libmp3lame) that not every ffmpeg build ships;
        # fall back to WAV so the preview step never fails on encoder support.
        preview_path = gen_dir / "preview_mix.mp3"
        ok = try_preview(preview_path)
        if not ok:
            log.warning("MP3 preview failed; retrying as WAV.")
            preview_path = gen_dir / "preview_mix.wav"
            ok = try_preview(preview_path)
        if ok:
            log.info("Workflow Complete.")
            log.info("  Preview: %s", preview_path)
        else:
            log.warning("Workflow Complete (with warnings). Preview mix was not created.")
        log.info("  Stems:   %s", gen_dir / "gen_*.wav")
        log.info("  Folder:  %s", gen_dir)
    else:
        log.warning("No generated audio to mix. Nothing to preview.")


if __name__ == "__main__":
    main()
