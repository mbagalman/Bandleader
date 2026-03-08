import types

import pytest


def _load_orchestrator_namespace():
    """
    Load bandleader/bandleader.py under Python 3.9 by injecting postponed annotations.
    This keeps tests runnable in this sandbox while project runtime target remains >=3.10.
    """
    with open("bandleader/bandleader.py", "r", encoding="utf-8") as f:
        source = f.read()

    source = "from __future__ import annotations\n" + source
    namespace = {"__name__": "bandleader.bandleader"}
    fake_yaml = types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {})
    namespace["yaml"] = fake_yaml

    import sys

    sys.modules.setdefault("yaml", fake_yaml)
    exec(compile(source, "bandleader/bandleader.py", "exec"), namespace)
    return namespace


def test_find_file_prefers_exact_wav_and_skips_generated(tmp_path):
    ns = _load_orchestrator_namespace()
    find_file = ns["find_file"]

    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "drums.wav").write_text("x", encoding="utf-8")
    (tmp_path / "drums_take.mp3").write_text("x", encoding="utf-8")
    (tmp_path / "drums.wav").write_text("x", encoding="utf-8")

    match = find_file(tmp_path, "drums")
    assert match is not None
    assert match.name == "drums.wav"
    assert "generated" not in match.parts


def test_get_soundfont_resolves_relative_path(tmp_path):
    ns = _load_orchestrator_namespace()
    get_soundfont = ns["get_soundfont"]

    sf_dir = tmp_path / "assets"
    sf_dir.mkdir()
    sf = sf_dir / "drums.sf2"
    sf.write_text("dummy", encoding="utf-8")

    config = {"soundfonts": {"drums": "assets/drums.sf2"}}
    resolved = get_soundfont(config, tmp_path, "drums")

    assert resolved == str(sf)


def test_validate_config_accepts_minimum_valid_shape():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    config = {
        "song": {
            "bpm": 120,
            "progression": "Am | F | C | G",
            "bars": 16,
        }
    }

    normalized = validate_config(config)
    assert normalized["song"]["time_signature"] == "4/4"
    assert normalized["stems"]["drums"] == "drums"
    assert normalized["pipeline"]["generate_bass"]["enabled"] is False


def test_validate_config_exits_on_missing_song_section():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    with pytest.raises(SystemExit):
        validate_config({})


def test_validate_config_rejects_invalid_pipeline_style():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {
            "generate_bass": {"enabled": True, "style": "not_a_style"},
        },
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_applies_generate_bass_ducking_defaults():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    cfg = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {"generate_bass": {"enabled": True, "style": "two_feel"}},
    }
    normalized = validate_config(cfg)
    bass = normalized["pipeline"]["generate_bass"]
    assert bass["sidechain_ducking"] is False
    assert bass["ducking_depth"] == 0.35
    assert bass["ducking_attack_ms"] == 10.0
    assert bass["ducking_release_ms"] == 120.0


def test_validate_config_rejects_invalid_generate_bass_ducking_values():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {
            "generate_bass": {
                "enabled": True,
                "style": "two_feel",
                "sidechain_ducking": "yes",
                "ducking_depth": 1.2,
                "ducking_attack_ms": 0,
                "ducking_release_ms": -10,
            }
        },
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_rejects_invalid_time_signature_format():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8, "time_signature": "bad-format"},
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_applies_clean_vocals_normalization_defaults():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    cfg = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {"clean_vocals": {"enabled": True}},
    }
    normalized = validate_config(cfg)
    vocals = normalized["pipeline"]["clean_vocals"]
    assert vocals["normalize"] is False
    assert vocals["target_lufs"] == -18.0
    assert vocals["target_true_peak"] == -1.5
    assert vocals["target_lra"] == 11.0


def test_validate_config_rejects_invalid_clean_vocals_target_type():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {
            "clean_vocals": {
                "enabled": True,
                "normalize": True,
                "target_lufs": "loud",
            }
        },
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_applies_clean_drums_sidechain_default():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    cfg = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {"clean_drums": {"enabled": True}},
    }
    normalized = validate_config(cfg)
    assert normalized["pipeline"]["clean_drums"]["export_sidechain_trigger"] is False


def test_validate_config_rejects_invalid_clean_drums_sidechain_type():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {"clean_drums": {"enabled": True, "export_sidechain_trigger": "yes"}},
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_applies_phase_align_defaults():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    cfg = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {"phase_align": {"enabled": True}},
    }
    normalized = validate_config(cfg)
    phase_align = normalized["pipeline"]["phase_align"]
    assert phase_align["enabled"] is True
    assert phase_align["max_shift_ms"] == 12.0
    assert phase_align["min_confidence"] == 0.35
    assert phase_align["pair_kick_bass"] is True
    assert phase_align["pair_snare_overheads"] is False
    assert phase_align["pair_bass_guitars"] is False


def test_validate_config_rejects_invalid_phase_align_values():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {
            "phase_align": {
                "enabled": True,
                "max_shift_ms": 0,
                "min_confidence": 1.2,
                "pair_kick_bass": "yes",
            }
        },
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_rejects_phase_align_confidence_below_zero():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {"phase_align": {"enabled": True, "min_confidence": -0.1}},
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_rejects_invalid_phase_align_secondary_pair_types():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "pipeline": {
            "phase_align": {
                "enabled": True,
                "pair_snare_overheads": "true",
                "pair_bass_guitars": 1,
            }
        },
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_validate_config_rejects_invalid_optional_stem_keywords():
    ns = _load_orchestrator_namespace()
    validate_config = ns["validate_config"]

    bad = {
        "song": {"bpm": 120, "progression": "Am | F", "bars": 8},
        "stems": {"drums": "drums", "vocals": "vocals", "synth": "synth", "overheads": 42, "guitars": None},
    }
    with pytest.raises(SystemExit):
        validate_config(bad)


def test_build_stem_cleaner_cmd_adds_normalization_flags_when_enabled(tmp_path):
    ns = _load_orchestrator_namespace()
    build_stem_cleaner_cmd = ns["build_stem_cleaner_cmd"]

    cmd = build_stem_cleaner_cmd(
        tmp_path / "vocals.wav",
        tmp_path / "out.wav",
        {"normalize": True, "target_lufs": -16.0, "target_true_peak": -1.0, "target_lra": 9.0},
    )
    cmd_str = " ".join(str(x) for x in cmd)
    assert "--normalize" in cmd_str
    assert "--target-lufs -16.0" in cmd_str
    assert "--target-true-peak -1.0" in cmd_str
    assert "--target-lra 9.0" in cmd_str


def test_build_stem_cleaner_cmd_omits_normalization_flags_when_disabled(tmp_path):
    ns = _load_orchestrator_namespace()
    build_stem_cleaner_cmd = ns["build_stem_cleaner_cmd"]

    cmd = build_stem_cleaner_cmd(tmp_path / "vocals.wav", tmp_path / "out.wav", {"normalize": False})
    cmd_str = " ".join(str(x) for x in cmd)
    assert "--normalize" not in cmd_str
    assert "--target-lufs" not in cmd_str


def test_build_sidechain_trigger_cmd_contains_expected_args(tmp_path):
    ns = _load_orchestrator_namespace()
    build_sidechain_trigger_cmd = ns["build_sidechain_trigger_cmd"]

    cmd = build_sidechain_trigger_cmd(
        tmp_path / "drums.mid",
        tmp_path / "gen_sidechain_trigger.mid",
        tmp_path / "gen_sidechain_trigger.wav",
        "/tmp/drums.sf2",
    )
    cmd_str = " ".join(str(x) for x in cmd)
    assert "bandleader.sidechain_trigger" in cmd_str
    assert "--input-midi" in cmd_str
    assert "--output-midi" in cmd_str
    assert "--render-audio" in cmd_str
    assert "--soundfont /tmp/drums.sf2" in cmd_str


def test_build_bass_ducking_cmd_contains_expected_args(tmp_path):
    ns = _load_orchestrator_namespace()
    build_bass_ducking_cmd = ns["build_bass_ducking_cmd"]

    cmd = build_bass_ducking_cmd(
        tmp_path / "gen_bass.wav",
        tmp_path / "gen_sidechain_trigger.wav",
        tmp_path / "gen_bass_ducked.wav",
        {"ducking_depth": 0.4, "ducking_attack_ms": 12.0, "ducking_release_ms": 140.0},
    )
    cmd_str = " ".join(str(x) for x in cmd)
    assert cmd[0] == "ffmpeg"
    assert "-filter_complex" in cmd_str
    assert "sidechaincompress=" in cmd_str
    assert "attack=12.0" in cmd_str
    assert "release=140.0" in cmd_str
    assert str(tmp_path / "gen_bass_ducked.wav") in cmd_str


def test_run_phase_alignment_pair_writes_output_for_valid_pair(tmp_path):
    import numpy as np
    from scipy.io import wavfile

    ns = _load_orchestrator_namespace()
    run_phase_alignment_pair = ns["run_phase_alignment_pair"]

    sr = 48_000
    delay = 16
    rng = np.random.default_rng(11)
    reference = rng.normal(0.0, 0.25, size=4096).astype(np.float32)
    target = np.concatenate([np.zeros(delay, dtype=np.float32), reference[:-delay]])
    ref_path = tmp_path / "ref.wav"
    tgt_path = tmp_path / "tgt.wav"
    out_path = tmp_path / "aligned.wav"
    wavfile.write(ref_path, sr, reference)
    wavfile.write(tgt_path, sr, target)

    result = run_phase_alignment_pair(
        "TestPair",
        ref_path,
        tgt_path,
        out_path,
        {"max_shift_ms": 5.0, "min_confidence": 0.3},
    )
    assert result.applied is True
    assert result.output_path == str(out_path)
    assert out_path.exists()


def test_run_phase_alignment_pair_skips_missing_target_without_raising(tmp_path):
    import numpy as np
    from scipy.io import wavfile

    ns = _load_orchestrator_namespace()
    run_phase_alignment_pair = ns["run_phase_alignment_pair"]

    sr = 48_000
    reference = np.zeros(1024, dtype=np.float32)
    ref_path = tmp_path / "ref.wav"
    wavfile.write(ref_path, sr, reference)

    result = run_phase_alignment_pair(
        "TestPair",
        ref_path,
        tmp_path / "missing.wav",
        tmp_path / "aligned.wav",
        {"max_shift_ms": 5.0, "min_confidence": 0.3},
    )
    assert result.applied is False
    assert result.reason == "target source missing"


def test_build_phase_alignment_report_entry_contains_expected_fields(tmp_path):
    ns = _load_orchestrator_namespace()
    build_phase_alignment_report_entry = ns["build_phase_alignment_report_entry"]
    AlignmentResult = ns["AlignmentResult"]

    result = AlignmentResult(
        applied=True,
        reason="applied",
        lag_samples=24,
        lag_ms=0.5,
        confidence=0.8,
        peak_correlation=0.9,
        output_path=str(tmp_path / "out.wav"),
    )
    entry = build_phase_alignment_report_entry(
        "kick_bass",
        tmp_path / "ref.wav",
        tmp_path / "target.wav",
        result,
    )
    assert entry["pair"] == "kick_bass"
    assert entry["applied"] is True
    assert entry["lag_samples"] == 24
    assert entry["reason"] == "applied"


def test_write_phase_alignment_report_writes_json(tmp_path):
    ns = _load_orchestrator_namespace()
    write_phase_alignment_report = ns["write_phase_alignment_report"]

    out = write_phase_alignment_report(
        tmp_path,
        [{"pair": "kick_bass", "applied": True, "reason": "applied"}],
    )
    assert out is not None
    assert out.exists()


def test_write_phase_alignment_report_skips_empty_entries(tmp_path):
    ns = _load_orchestrator_namespace()
    write_phase_alignment_report = ns["write_phase_alignment_report"]

    out = write_phase_alignment_report(tmp_path, [])
    assert out is None


def test_ensure_tools_for_enabled_steps_allows_unneeded_tools(monkeypatch):
    ns = _load_orchestrator_namespace()
    ensure_tools_for_enabled_steps = ns["ensure_tools_for_enabled_steps"]

    monkeypatch.setattr(ns["shutil"], "which", lambda _tool: None)
    ensure_tools_for_enabled_steps({"generate_bass": {"enabled": False}})


def test_ensure_tools_for_enabled_steps_fails_with_step_specific_error(monkeypatch):
    ns = _load_orchestrator_namespace()
    ensure_tools_for_enabled_steps = ns["ensure_tools_for_enabled_steps"]

    monkeypatch.setattr(ns["shutil"], "which", lambda _tool: None)
    with pytest.raises(SystemExit):
        ensure_tools_for_enabled_steps({"generate_bass": {"enabled": True}})


def test_ensure_tools_for_enabled_steps_requires_ffmpeg_for_bass_ducking(monkeypatch):
    ns = _load_orchestrator_namespace()
    ensure_tools_for_enabled_steps = ns["ensure_tools_for_enabled_steps"]

    def fake_which(tool):
        if tool == "fluidsynth":
            return "/usr/bin/fluidsynth"
        return None

    monkeypatch.setattr(ns["shutil"], "which", fake_which)
    with pytest.raises(SystemExit):
        ensure_tools_for_enabled_steps({"generate_bass": {"enabled": True, "sidechain_ducking": True}})


def test_ensure_tools_for_enabled_steps_does_not_require_ffmpeg_for_dry_bass(monkeypatch):
    ns = _load_orchestrator_namespace()
    ensure_tools_for_enabled_steps = ns["ensure_tools_for_enabled_steps"]

    def fake_which(tool):
        if tool == "fluidsynth":
            return "/usr/bin/fluidsynth"
        return None

    monkeypatch.setattr(ns["shutil"], "which", fake_which)
    ensure_tools_for_enabled_steps({"generate_bass": {"enabled": True, "sidechain_ducking": False}})


def test_find_file_is_deterministic_for_equivalent_names(tmp_path):
    ns = _load_orchestrator_namespace()
    find_file = ns["find_file"]

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "drums.wav").write_text("x", encoding="utf-8")
    (tmp_path / "b" / "drums.wav").write_text("x", encoding="utf-8")

    first = find_file(tmp_path, "drums")
    second = find_file(tmp_path, "drums")
    assert first is not None
    assert second is not None
    assert first == second


def test_build_preview_mix_filter_normalizes_channels():
    ns = _load_orchestrator_namespace()
    build_preview_mix_filter = ns["build_preview_mix_filter"]

    filter_graph = build_preview_mix_filter(2)
    assert "channel_layouts=stereo" in filter_graph
    assert "amix=inputs=2" in filter_graph
    assert filter_graph.endswith("[mix]")


def test_build_preview_mix_filter_rejects_zero_inputs():
    ns = _load_orchestrator_namespace()
    build_preview_mix_filter = ns["build_preview_mix_filter"]

    with pytest.raises(ValueError):
        build_preview_mix_filter(0)
