from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import auto_research.video_pipeline as video_pipeline
from auto_research.video_pipeline import (
    _clean_vision_response_content,
    _call_json_model,
    _call_text_model,
    _enforce_source_storyboard_coverage,
    _enrich_short_speaker_notes,
    _image_model_config,
    _build_model_slides_in_batches,
    _model_slide_payload_issues,
    _normalize_slide,
    _scene_asset_manifest,
    _scene_media_split_layout,
    _text_model_provider,
    _write_pipeline_checkpoint,
    build_scene_timeline,
    build_slides,
    load_source,
    media_duration_seconds,
    mux_audio_into_video,
    revise_slides,
    sanitize_public_slides,
    synthesize_tts_segments,
)


def test_scene_media_split_layout_keeps_text_off_the_image() -> None:
    for media_left in (True, False):
        media, text = _scene_media_split_layout(1280, 720, media_left=media_left)
        mx1, my1, mx2, my2 = media
        tx1, ty1, tx2, ty2 = text

        assert mx2 <= tx1 or tx2 <= mx1
        assert my1 >= 0 and my2 <= 720 - 146
        assert ty1 >= 0 and ty2 <= 720 - 146
        assert abs(((mx2 - mx1) / (my2 - my1)) - (16 / 9)) < 0.03


def test_model_storyboard_batches_large_outputs(monkeypatch) -> None:
    calls: list[str] = []

    def fake_json_model(prompt: str):
        calls.append(prompt)
        if '"outline"' in prompt:
            return {
                "outline": [
                    {"index": i, "title": f"Topic {i}", "purpose": f"Job {i}", "visual_kind": "image"}
                    for i in range(1, 8)
                ]
            }
        marker = "Produce exactly "
        count = int(prompt.split(marker, 1)[1].split(" slides", 1)[0])
        start = int(prompt.split("Write slides ", 1)[1].split(" through", 1)[0])
        return {
            "slides": [
                {
                    "index": i,
                    "title": f"Topic {i}",
                    "purpose": f"Explain source fact {i}",
                    "bullets": [f"Claim {i} is grounded in the source.", f"Evidence {i} explains its consequence."],
                    "speaker_note": f"Explanation {i}",
                    "visual_prompt": f"Show the mechanism for source fact {i}",
                    "visual_kind": "image",
                    "visual_caption": f"Source fact {i} and its consequence",
                    "visual_items": [f"Source state {i}", f"Result state {i}"],
                    "visual_table": [],
                    "animation_labels": {
                        "primary": f"Source state {i}",
                        "secondary": f"Transformation {i}",
                        "result": f"Result {i}",
                    },
                    "scene_direction": {
                        "layout": "editorial",
                        "entrance": "fade_up",
                        "emphasis": f"Source fact {i}",
                    },
                }
                for i in range(start, start + count)
            ]
        }

    monkeypatch.setattr(video_pipeline, "_call_json_model", fake_json_model)
    slides = _build_model_slides_in_batches(
        {"kind": "paper", "title": "Test", "text": "Source facts"},
        target_slides=7,
        batch_size=3,
    )

    assert slides is not None
    assert [slide["index"] for slide in slides] == list(range(1, 8))
    assert len(calls) == 4


def test_model_only_normalization_never_builds_a_default_table() -> None:
    slide = _normalize_slide(
        1,
        {
            "title": "Grounded claim",
            "purpose": "Explain one source claim",
            "bullets": ["The source states the claim.", "The evidence explains its impact."],
            "speaker_note": "The source states the claim and explains why it matters.",
            "visual_prompt": "Show the claim and its consequence",
            "visual_kind": "image",
            "visual_caption": "The claim changes the final outcome",
            "visual_items": ["Source claim", "Observed outcome"],
            "visual_table": [],
            "animation_labels": {
                "primary": "Source claim",
                "secondary": "Evidence connection",
                "result": "Observed outcome",
            },
            "scene_direction": {"layout": "editorial", "entrance": "fade_up", "emphasis": "Source claim"},
        },
        model_text_only=True,
    )

    assert slide["visual_table"] == []
    assert slide["text_provenance"]["visual_table"] == "model_not_requested"


def test_repeated_model_table_roles_are_rejected() -> None:
    issues = _model_slide_payload_issues(
        [
            {
                "index": 1,
                "title": "Evidence",
                "purpose": "Compare source evidence",
                "bullets": ["First finding is supported.", "Second finding is supported."],
                "speaker_note": "The paper reports two findings with different implications.",
                "visual_prompt": "Compare both findings",
                "visual_kind": "table",
                "visual_caption": "Two findings play different roles",
                "visual_items": ["First finding", "Second finding"],
                "visual_table": [
                    ["Claim", "Evidence", "Role"],
                    ["First", "Result A", "Supports the current explanation"],
                    ["Second", "Result B", "Supports the current explanation"],
                ],
                "animation_labels": {"primary": "Claims", "secondary": "Evidence", "result": "Implications"},
                "scene_direction": {"layout": "evidence_grid", "entrance": "fade_up", "emphasis": "Result A"},
            }
        ],
        expected_count=1,
    )

    assert any("repeats the same text" in issue for issue in issues)
    assert any("forbidden template text" in issue for issue in issues)


def test_model_narration_must_preserve_exact_factual_numbers() -> None:
    issues = _model_slide_payload_issues(
        [
            {
                "index": 1,
                "title": "Benchmark of 101 paired papers",
                "purpose": "Describe the benchmark scale",
                "bullets": ["The benchmark contains 101 papers.", "Each paper has a paired video."],
                "speaker_note": "The benchmark contains one hundred papers paired with presentation videos.",
                "visual_prompt": "Show paired paper and video records",
                "visual_kind": "image",
                "visual_caption": "Paired benchmark records",
                "visual_items": ["Research papers", "Presentation videos"],
                "visual_table": [],
                "animation_labels": {
                    "primary": "Research papers",
                    "secondary": "Pairing process",
                    "result": "Benchmark records",
                },
                "scene_direction": {
                    "layout": "data_wall",
                    "entrance": "fade_up",
                    "emphasis": "101 paired papers",
                },
            }
        ],
        expected_count=1,
    )

    assert any("preserve exact factual numbers: 101" in issue for issue in issues)


def test_model_only_sanitizer_raises_instead_of_writing_placeholder_text() -> None:
    with pytest.raises(RuntimeError, match="lost required text fields"):
        sanitize_public_slides([{"index": 1, "text_generation_mode": "model_only"}])


def test_short_narration_is_enriched_with_source_grounded_model_output(monkeypatch) -> None:
    calls = 0

    def fake_json_model(_prompt: str):
        nonlocal calls
        calls += 1
        assert "exactly 5 complete sentences" in _prompt
        return {
            "slides": [
                {
                    "index": 1,
                    "speaker_note": (
                        "The system coordinates four specialized builders around one shared plan. "
                        "The slide builder converts paper evidence into a visual structure, while the subtitle builder turns the explanation into timed segments. "
                        "A grounding component then links each spoken claim to a visible region. "
                        "This coordination matters because independently correct outputs can still produce an incoherent video when their timing and focus disagree."
                    ),
                }
            ]
        }

    monkeypatch.setattr(video_pipeline, "_call_json_model", fake_json_model)
    slides = _enrich_short_speaker_notes(
        {"title": "PaperTalker", "text": "The source describes coordinated builders and temporal grounding."},
        [{"index": 1, "title": "Architecture", "speaker_note": "Four builders work together."}],
        min_words=55,
        max_words=90,
    )

    assert calls == 1
    assert slides[0]["narration_depth_mode"] == "model_enriched"
    assert slides[0]["narration_depth_words"] >= 55


def test_sufficient_narration_does_not_call_enrichment_model(monkeypatch) -> None:
    monkeypatch.setattr(
        video_pipeline,
        "_call_json_model",
        lambda _prompt: pytest.fail("enrichment model should not be called"),
    )
    note = " ".join(f"word{i}" for i in range(70))

    slides = _enrich_short_speaker_notes(
        {"title": "Paper", "text": "Source"},
        [{"index": 1, "speaker_note": note}],
        min_words=70,
        max_words=95,
    )

    assert slides[0]["speaker_note"] == note


def test_last_narration_attempt_accepts_meaningful_soft_improvement(monkeypatch) -> None:
    monkeypatch.setenv("AUTO_VIDEO_NARRATION_ENRICH_ATTEMPTS", "1")
    candidate = " ".join(f"detail{i}" for i in range(60))
    monkeypatch.setattr(
        video_pipeline,
        "_call_json_model",
        lambda _prompt: {"slides": [{"index": 1, "speaker_note": candidate}]},
    )

    slides = _enrich_short_speaker_notes(
        {"title": "Paper", "text": "Source evidence"},
        [{"index": 1, "speaker_note": "Short original note with little detail."}],
        min_words=70,
        max_words=95,
    )

    assert slides[0]["narration_depth_mode"] == "model_enriched_soft"
    assert slides[0]["narration_depth_words"] == 60


def test_video_pipeline_prefers_deepseek_provider(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert _text_model_provider() == "deepseek"


def test_video_pipeline_can_force_deepseek_when_lumid_is_also_loaded(monkeypatch) -> None:
    monkeypatch.setenv("LUM_API_KEY", "lumid-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("AUTO_VIDEO_TEXT_PROVIDER", "deepseek")

    assert _text_model_provider() == "deepseek"


def test_dedicated_openai_image_provider_does_not_replace_lumid_text(monkeypatch) -> None:
    monkeypatch.setenv("LUM_API_KEY", "lumid-key")
    monkeypatch.setenv("LUMID_BASE_URL", "https://lumid.example/v1")
    monkeypatch.setenv("LUMID_MODEL", "qwen-text")
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "openai-image-key")
    monkeypatch.setenv("OPENAI_IMAGE_BASE_URL", "https://api.openai.example/v1")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-2")

    assert _text_model_provider() == "lumid"
    assert _image_model_config() == (
        "openai-image-key",
        "https://api.openai.example/v1",
        "gpt-image-2",
        "openai",
        "1536x864",
    )


def test_openai_image_request_uses_supported_fields(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "openai-image-key")
    monkeypatch.setenv("AUTO_VIDEO_IMAGE_ATTEMPTS", "1")

    def fake_post(url: str, key: str, body: dict, timeout: float):
        captured.update(url=url, key=key, body=body, timeout=timeout)
        return {}, json.dumps({"data": [{"b64_json": "aGVhbHRoeQ=="}]}).encode()

    monkeypatch.setattr(video_pipeline, "_post_bytes", fake_post)
    out = tmp_path / "generated.png"

    ok, error = video_pipeline._call_lumid_image("Generate an academic scene.", out)

    assert ok is True
    assert error == ""
    assert out.read_bytes() == b"healthy"
    assert captured["url"] == "https://api.openai.com/v1/images/generations"
    assert captured["key"] == "openai-image-key"
    assert captured["body"] == {
        "model": "gpt-image-2",
        "prompt": "Generate an academic scene.",
        "n": 1,
        "size": "1536x864",
        "quality": "medium",
        "output_format": "png",
    }


def test_text_model_retries_the_same_provider_before_fallback(monkeypatch) -> None:
    calls = 0
    monkeypatch.setenv("AUTO_VIDEO_TEXT_ATTEMPTS", "3")
    monkeypatch.setattr(video_pipeline, "_text_model_config", lambda: ("key", "https://example.test", "model", "lumid"))
    monkeypatch.setattr(video_pipeline.time, "sleep", lambda _seconds: None)

    def flaky_post(_url: str, _key: str, _body: dict, _timeout: float):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("provider still starting")
        return {}, json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()

    monkeypatch.setattr(video_pipeline, "_post_bytes", flaky_post)

    assert _call_text_model("Return JSON") == '{"ok": true}'
    assert calls == 2


def test_text_model_retries_when_json_was_truncated_by_token_limit(monkeypatch) -> None:
    calls = 0
    monkeypatch.setenv("AUTO_VIDEO_TEXT_ATTEMPTS", "2")
    monkeypatch.setenv("AUTO_VIDEO_TEXT_MAX_TOKENS", "6000")
    monkeypatch.setattr(video_pipeline, "_text_model_config", lambda: ("key", "https://example.test", "model", "lumid"))
    monkeypatch.setattr(video_pipeline.time, "sleep", lambda _seconds: None)

    def truncated_then_complete(_url: str, _key: str, body: dict, _timeout: float):
        nonlocal calls
        calls += 1
        assert body["max_tokens"] == 6000
        if calls == 1:
            response = {
                "choices": [{"finish_reason": "length", "message": {"content": '{"slides": ['}}],
                "usage": {"completion_tokens": 6000},
            }
        else:
            response = {
                "choices": [{"finish_reason": "stop", "message": {"content": '{"slides": []}'}}],
                "usage": {"completion_tokens": 8},
            }
        return {}, json.dumps(response).encode()

    monkeypatch.setattr(video_pipeline, "_post_bytes", truncated_then_complete)

    assert _call_text_model("Return JSON") == '{"slides": []}'
    assert calls == 2


def test_json_parser_accepts_fenced_json_and_ignores_trailing_text() -> None:
    assert video_pipeline._json_from_model('```json\n{"ok": true}\n```') == {"ok": True}
    assert video_pipeline._json_from_model('Result:\n{"ok": true}\nDone.') == {"ok": True}


def test_invalid_model_json_is_retried_instead_of_using_local_content(monkeypatch) -> None:
    responses = iter(["temporarily incomplete", '{"slides": [{"title": "Ready"}]}'])
    monkeypatch.setenv("AUTO_VIDEO_JSON_ATTEMPTS", "3")
    monkeypatch.setattr(video_pipeline.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(video_pipeline, "_call_openai_compatible", lambda _prompt: next(responses))

    data = _call_json_model("Return slides")

    assert data == {"slides": [{"title": "Ready"}]}


def test_asset_manifest_exposes_strategy_and_local_repair_targets() -> None:
    manifest = _scene_asset_manifest(
        [
            {
                "shot_id": "s01-01",
                "slide_index": 1,
                "visual_strategy": "generated_scene",
                "visual_strategy_reason": "Conceptual opening",
                "asset_source": "generated",
                "asset_status": "ready",
                "visual_asset_path": "/tmp/scene.png",
                "fallback_strategy": "kinetic_text",
                "repair_target": "none",
            },
            {
                "shot_id": "s01-02",
                "slide_index": 1,
                "visual_strategy": "kinetic_text",
                "visual_strategy_reason": "Rejected image fallback",
                "asset_source": "renderer",
                "asset_status": "structured",
                "visual_asset_path": "",
                "fallback_strategy": "kinetic_text",
                "repair_target": "visual_asset",
            },
        ]
    )

    assert manifest["strategy_counts"] == {"generated_scene": 1, "kinetic_text": 1}
    assert manifest["repairable_shots"] == ["s01-02"]


def test_pipeline_checkpoint_records_latest_completed_stage(tmp_path: Path) -> None:
    _write_pipeline_checkpoint(
        tmp_path,
        stage="assets_ready",
        source={"title": "Demo", "source_path": "/tmp/demo.pdf", "kind": "paper"},
        slides=[{"index": 1, "title": "Scene"}],
        subtitles=[{"slide_index": 1, "text": "Narration"}],
        cursor_plan=[],
        talker={"mode": "narration"},
        extra={"asset_manifest": {"shot_count": 1}},
    )

    checkpoint = json.loads((tmp_path / "pipeline_checkpoint.json").read_text())
    assert checkpoint["stage"] == "assets_ready"
    assert checkpoint["asset_manifest"]["shot_count"] == 1
    assert checkpoint["slides"][0]["title"] == "Scene"


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


def test_segment_tts_retries_a_transient_failed_sentence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LUM_API_KEY", "test-key")
    monkeypatch.setenv("AUTO_VIDEO_TTS_TEMPO", "1.0")
    monkeypatch.setenv("AUTO_VIDEO_TTS_WORKERS", "1")
    monkeypatch.setenv("AUTO_VIDEO_TTS_SEGMENT_RETRIES", "3")
    monkeypatch.setenv("AUTO_VIDEO_TTS_RECOVERY_DELAYS", "0")
    attempts = 0

    def flaky_tts_clip(_text: str, out: Path) -> tuple[bool, str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return False, "temporary provider failure"
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", "0.5", "-c:a", "libmp3lame", str(out),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return proc.returncode == 0 and out.is_file(), ""

    monkeypatch.setattr(video_pipeline, "_synthesize_tts_clip", flaky_tts_clip)
    subtitles = [{"slide_index": 1, "start_sec": 0, "end_sec": 5, "text": "Retry this sentence."}]

    result, synced = synthesize_tts_segments(subtitles, tmp_path, use_tts=True)

    assert attempts == 2
    assert result["ok"] is True
    assert result["timing_mode"] == "segment_exact"
    assert synced[0]["speech_start_sec"] > synced[0]["start_sec"]


def test_audio_mux_refuses_mismatched_track_duration(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "video.mp4"
    audio = tmp_path / "narration.mp3"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    monkeypatch.setattr(
        video_pipeline,
        "media_duration_seconds",
        lambda path: 10.0 if path == video else 14.0,
    )

    assert mux_audio_into_video(video, audio) is False
    assert not (tmp_path / "video_silent.mp4").exists()


def test_pdf_metadata_supplies_real_title_and_authors(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    pdf = tmp_path / "paper.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": "Grounded Paper Title", "/Author": "Ada Example; Lin Example"})
    with pdf.open("wb") as stream:
        writer.write(stream)

    source = load_source(pdf, kind="paper")

    assert source["title"] == "Grounded Paper Title"
    assert source["authors"] == "Ada Example; Lin Example"


def test_scene_timeline_adds_silent_title_card_before_first_speech() -> None:
    source = {"title": "Paper2Video", "authors": "Ada Example"}
    slides = [{"index": 1, "title": "Motivation", "bullets": ["A grounded claim."], "visual_kind": "image"}]
    subtitles = [
        {
            "slide_index": 1,
            "segment_start_sec": 0,
            "start_sec": 4,
            "speech_start_sec": 4,
            "speech_end_sec": 9,
            "end_sec": 10,
            "text": "A grounded claim.",
        }
    ]

    timeline = build_scene_timeline(source, slides, subtitles)

    assert timeline[0]["shot_type"] == "title_card"
    assert timeline[0]["headline"] == "Paper2Video"
    assert timeline[0]["end_sec"] == 4
    assert timeline[1]["start_sec"] == 4


def test_slide_revision_cannot_shrink_the_storyboard(monkeypatch) -> None:
    slides = [
        {"index": index, "title": f"Slide {index}", "bullets": [f"Claim {index}."], "visual_kind": "image"}
        for index in range(1, 5)
    ]
    monkeypatch.setattr(
        video_pipeline,
        "_call_openai_compatible",
        lambda _prompt: json.dumps({"slides": slides[:2]}),
    )

    revised = revise_slides(
        {"title": "Demo", "text": "Grounded source."},
        slides,
        {"revise_next": {"slide_builder": "Improve details."}},
        round_index=1,
        use_api=True,
    )

    assert len(revised) == 4
    assert revised[2]["title"] == "Slide 3"


def test_papertalker_core_method_cannot_collapse_to_parallel_speed_only() -> None:
    source = {
        "text": "PaperTalker uses Tree Search Visual Choice, cursor grounding, speech synthesis, and talking-head rendering.",
    }
    slides = [
        {"index": 1, "title": "Motivation", "bullets": ["Problem."], "visual_kind": "image"},
        {"index": 2, "title": "Core Method", "bullets": ["Parallel generation achieves 6x speedup."], "visual_kind": "metrics"},
    ]

    grounded = _enforce_source_storyboard_coverage(source, slides)
    core = grounded[1]

    assert core["visual_kind"] == "flow"
    assert "PaperTalker" in core["speaker_note"]
    assert "Tree Search Visual Choice" in core["speaker_note"]
    assert "cursor" in core["speaker_note"].casefold()


def test_paper2video_benchmark_metrics_are_source_verified() -> None:
    source = {
        "text": (
            "Paper2Video covers 101 paper-video pairs. Average 16.0 slides per video. "
            "Average 6:15 duration across 41 ML, 40 CV, and 20 NLP papers."
        )
    }
    slides = [
        {
            "index": 1,
            "title": "Paper2Video Benchmark",
            "bullets": ["A benchmark."],
            "visual_kind": "metrics",
            "visual_items": ["101", "3", "16 Slides", "6 Minutes"],
        }
    ]

    grounded = _enforce_source_storyboard_coverage(source, slides)

    assert grounded[0]["visual_items"] == [
        "101 Paper-Video Pairs",
        "16.0 Average Slides per Video",
        "6:15 Average Video Duration",
        "3 Research Fields: ML 41, CV 40, NLP 20",
    ]


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
    assert slides[2]["visual_table"][0] == ["Claim", "Paper evidence", "Presentation role"]
    assert all(len(set(row)) == len(row) for row in slides[2]["visual_table"][1:])


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
