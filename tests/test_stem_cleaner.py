from pathlib import Path

from bandleader.stem_cleaner import PRESETS, build_loudnorm_filter, build_wet_chain, run_ffmpeg


def test_build_loudnorm_filter_uses_explicit_targets():
    filt = build_loudnorm_filter(target_lufs=-16.0, target_true_peak=-1.0, target_lra=9.0)
    assert filt == "loudnorm=I=-16.0:TP=-1.0:LRA=9.0"


def test_deesser_filter_params_are_valid():
    # Regression: deesser once used f=5500 (Hz), but ffmpeg's f is a 0-1
    # fraction and s is an enum (i/o/e) — invalid values fail the whole
    # filter graph and silently drop de-essing via the retry path.
    chain = build_wet_chain(PRESETS["vocal"]["medium"], enable_deess=True, force_lpf=None)
    deess = [p for p in chain.split(",") if p.startswith("deesser")]
    assert len(deess) == 1
    params = dict(kv.split("=") for kv in deess[0].split("=", 1)[1].split(":"))
    assert 0.0 <= float(params["i"]) <= 1.0
    assert 0.0 <= float(params["f"]) <= 1.0
    assert params["s"] in ("i", "o", "e")
    if "m" in params:
        assert 0.0 <= float(params["m"]) <= 1.0


def test_run_ffmpeg_audit_log_includes_metadata(monkeypatch, tmp_path: Path):
    input_file = tmp_path / "in.wav"
    output_file = tmp_path / "out.wav"
    log_file = tmp_path / "out.ffmpeg.txt"
    input_file.write_text("dummy", encoding="utf-8")

    class _Proc:
        returncode = 0
        stderr = ""

    def fake_run(_cmd, capture_output=True, text=True):
        output_file.write_text("rendered", encoding="utf-8")
        return _Proc()

    monkeypatch.setattr("subprocess.run", fake_run)

    run_ffmpeg(
        input_path=input_file,
        output_path=output_file,
        audio_filter="anull",
        sample_rate=None,
        bit_depth=24,
        overwrite=True,
        log_path=log_file,
        audit_metadata={"normalize": True, "target_lufs": -18.0},
    )

    text = log_file.read_text(encoding="utf-8")
    assert "# normalize: True" in text
    assert "# target_lufs: -18.0" in text
    assert "ffmpeg -y" in text
