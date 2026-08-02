from __future__ import annotations

import json
import subprocess
from pathlib import Path

import auto_research.video_pipeline as video_pipeline
from auto_research.video_pipeline import (
    _clean_vision_response_content,
    _text_model_provider,
    build_slides,
    media_duration_seconds,
    synthesize_tts_segments,
)


def test_video_pipeline_prefers_deepseek_provider(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert _text_model_provider() == "deepseek"


def test_video_pipeline_can_force_deepseek_when_lumid_is_also_loaded(monkeypatch) -> None:
    monkeypatch.setenv("LUM_API_KEY", "lumid-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("AUTO_VIDEO_TEXT_PROVIDER", "deepseek")

    assert _text_model_provider() == "deepseek"


def test_vision_response_removes_generated_audio_payload() -> None:
    value = "The image contains six panels.\n\n[generated audio](data:audio/mpeg;base64,AAAA)"

    assert _clean_vision_response_content(value) == "The image contains six panels."
    assert _clean_vision_response_content("(qwen-omni error: 500 Internal Server Error)") is None


def test_segment_tts_uses_measured_audio_and_post_speech_hold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LUM_API_KEY", "test-key")
    monkeypatch.setenv("AUTO_VIDEO_TTS_TEMPO", "1.0")
    monkeypatch.setenv("AUTO_VIDEO_PRE_SPEECH_HOLD_SEC", "0.2")
    monkeypatch.setenv("AUTO_VIDEO_POST_SPEECH_HOLD_SEC", "0.8")
    monkeypatch.setenv("AUTO_VIDEO_TTS_WORKERS", "1")

    def fake_tts_clip(_text: str, out: Path) -> tuple[bool, str]:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", "1.0", "-c:a", "libmp3lame", str(out),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode == 0 and out.is_file(), ""

    monkeypatch.setattr(video_pipeline, "_synthesize_tts_clip", fake_tts_clip)
    subtitles = [
        {"slide_index": 1, "start_sec": 0, "end_sec": 5, "text": "First sentence."},
        {"slide_index": 1, "start_sec": 5, "end_sec": 10, "text": "Second sentence."},
    ]

    result, synced = synthesize_tts_segments(subtitles, tmp_path, use_tts=True)

    assert result["ok"] is True
    assert synced[1]["start_sec"] == synced[0]["end_sec"]
    assert synced[0]["speech_start_sec"] >= synced[0]["start_sec"] + 0.19
    assert synced[0]["end_sec"] >= synced[0]["speech_end_sec"] + 0.74
    total_audio = media_duration_seconds(Path(result["path"]))
    assert total_audio is not None
    assert abs(total_audio - synced[-1]["end_sec"]) < 0.15


def test_video_slide_builder_adds_rich_visual_types() -> None:
    source = {
        "kind": "paper",
        "title": "Rich Visual Demo",
        "source_path": "demo.md",
        "text": (
            "This project creates screenshots, evidence tables, cursor plans, talker inputs, "
            "judge feedback, and rendered video artifacts. The workflow ingests source material, "
            "builds a storyboard, reviews coverage, revises weak modules, and renders an MP4 demo."
        ),
        "files": [],
    }

    slides = build_slides(source, max_slides=5, use_api=False)

    assert [slide["visual_kind"] for slide in slides] == [
        "image",
        "flow",
        "table",
        "metrics",
        "image",
    ]
    assert all(slide["visual_caption"] for slide in slides)
    assert slides[2]["visual_table"][0] == ["Aspect", "Focus", "Why it matters"]


def test_video_build_cli_writes_artifacts(tmp_path: Path) -> None:
    from auto_research.cli import app
    from typer.testing import CliRunner

    source = tmp_path / "sample.md"
    source.write_text(
        """
        # Test Paper Video

        This project studies a builder workflow for turning research papers into video artifacts.
        The method creates slides, subtitles, cursor plans, talker inputs, and judge feedback.
        The judge agent reviews coverage, length, and visual synchronization before rendering.
        """.strip(),
        encoding="utf-8",
    )
    out_dir = tmp_path / "video_out"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "video",
            "build",
            "--cwd",
            str(tmp_path),
            "--input",
            str(source),
            "--kind",
            "paper",
            "--out-dir",
            str(out_dir),
            "--fps",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "preview.html").is_file()
    assert (out_dir / "storyboard.json").is_file()
    assert (out_dir / "judge_feedback.json").is_file()
    assert (out_dir / "revision_history.json").is_file()
    assert (out_dir / "iterations" / "round_0" / "judge_feedback.json").is_file()
    assert (out_dir / "iterations" / "round_1" / "judge_feedback.json").is_file()
    assert (out_dir / "flowmesh_spec.json").is_file()
    assert (out_dir / "metrics.json").is_file()
    assert (out_dir / "video.mp4").is_file()
    assert "Video preview:" in result.output
    assert "MP4 video:" in result.output

    history = json.loads((out_dir / "revision_history.json").read_text(encoding="utf-8"))
    assert history[0]["rerun_modules"] == [
        "slide_builder",
        "subtitle_builder",
        "cursor_builder",
        "talker_builder",
    ]
    assert "rerun_modules_next" in history[0]
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "module_scores" in metrics
    assert "failed_modules" in metrics
