from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from auto_research.video_pipeline import (
    PAPER_VISUAL_THEMES,
    _estimate_narration_duration,
    _apply_scene_entrance,
    build_scene_timeline,
    build_subtitles,
    choose_paper_visual_theme,
    _clean_display_text,
    _draw_generated_image,
    _image_generation_prompt,
    _image_retry_prompt,
    _metric_cards_from_items,
    _metric_card_focus,
    _merge_scene_beats,
    _normalize_slide,
    _scene_focus_index,
    _scene_item_detail,
    assign_paper_figures,
    generate_slide_images,
    plan_scene_directions,
)


def test_display_text_removes_ellipsis_without_cutting_content() -> None:
    text = _clean_display_text("Complete claim... with supporting evidence… and a conclusion.")

    assert "..." not in text
    assert "…" not in text
    assert "supporting evidence" in text
    assert text.endswith("conclusion.")


def test_process_focus_uses_the_matching_paper_explanation() -> None:
    slide = {
        "bullets": ["PresentQuiz tests knowledge retention via questions."],
        "speaker_note": (
            "PresentArena compares videos pairwise. "
            "PresentQuiz evaluates knowledge conveyance by asking questions derived from the paper."
        ),
        "purpose": "Explain the evaluation metrics.",
    }

    detail = _scene_item_detail(slide, "PresentQuiz: Knowledge Retention")

    assert detail.startswith("PresentQuiz evaluates knowledge conveyance")
    assert "questions derived from the paper" in detail


def test_scene_focus_follows_the_metric_named_by_narration() -> None:
    index = _scene_focus_index(
        "PresentArena uses VideoLLMs as proxy audiences for pairwise comparisons.",
        bullets=[
            "Meta Similarity measures alignment.",
            "PresentArena performs pairwise comparison.",
            "PresentQuiz tests retention.",
        ],
        visual_items=[
            "Meta Similarity: Alignment",
            "PresentArena: Pairwise Comparison",
            "PresentQuiz: Knowledge Retention",
            "IP Memory: Author Impact",
        ],
        fallback=2,
    )

    assert index == 1


def test_scene_focus_maps_spoken_number_to_numeric_speedup() -> None:
    index = _scene_focus_index(
        "This approach achieves a speedup of more than six times.",
        bullets=[
            "Cursor grounding aligns pointers with narration.",
            "Parallel slide generation achieves 6x speedup.",
            "WhisperX ensures temporal alignment.",
        ],
        visual_items=["6x Speedup", "Parallel Processing", "Temporal Alignment"],
        fallback=2,
    )

    assert index == 1


def test_multi_beat_metric_scene_keeps_each_explanation_visual() -> None:
    slide = {
        "index": 6,
        "title": "Alignment and Efficiency",
        "purpose": "Explain cursor grounding and parallelization.",
        "bullets": [
            "Cursor grounding aligns pointers with narration.",
            "Parallel slide generation achieves 6x speedup.",
            "WhisperX ensures precise temporal alignment.",
        ],
        "visual_kind": "metrics",
        "visual_items": ["6x Speedup", "Parallel Processing", "Temporal Alignment"],
        "scene_direction": {"layout": "comparison", "entrance": "fade_up", "emphasis": ""},
    }
    subtitles = [
        {"slide_index": 6, "start_sec": 0, "end_sec": 12, "text": "A GUI-grounding model generates cursor trajectories."},
        {"slide_index": 6, "start_sec": 12, "end_sec": 18, "text": "This helps viewers follow complex arguments."},
        {"slide_index": 6, "start_sec": 18, "end_sec": 28, "text": "We parallelize generation across slides."},
        {"slide_index": 6, "start_sec": 28, "end_sec": 40, "text": "This achieves a speedup of more than six times."},
    ]

    earlier_slides = [
        {
            "index": index,
            "title": f"Chapter {index}",
            "bullets": ["Context"],
            "speaker_note": "Context",
            "visual_kind": "image",
        }
        for index in range(1, 6)
    ]
    timeline = [
        shot
        for shot in build_scene_timeline({"title": "PaperTalker"}, [*earlier_slides, slide], subtitles)
        if shot["slide_index"] == 6
    ]

    assert [shot["shot_type"] for shot in timeline] == [
        "data_landscape",
        "data_focus",
        "data_detail",
        "data_conclusion",
    ]
    assert [shot["focus_index"] for shot in timeline] == [0, 0, 1, 1]


def test_scene_beats_merge_without_dropping_subtitle_time_or_text() -> None:
    subtitles = [
        {"start_sec": index * 2, "end_sec": (index + 1) * 2, "text": f"Sentence {index + 1}."}
        for index in range(6)
    ]

    beats = _merge_scene_beats(subtitles, max_beats=4)

    assert len(beats) == 4
    assert beats[0]["start_sec"] == 0
    assert beats[-1]["end_sec"] == 12
    merged_text = " ".join(beat["text"] for beat in beats)
    assert all(f"Sentence {index}." in merged_text for index in range(1, 7))


def test_core_flow_starts_with_the_method_diagram_instead_of_an_empty_section_card() -> None:
    slides = [
        {"index": 1, "title": "Motivation", "bullets": ["Problem."], "visual_kind": "image"},
        {
            "index": 2,
            "title": "Core Method",
            "bullets": ["PaperTalker coordinates specialized agents."],
            "visual_kind": "flow",
            "visual_items": ["Paper", "Slides", "Alignment", "Speech", "Video"],
        },
    ]
    subtitles = [
        {"slide_index": 2, "start_sec": index * 5, "end_sec": (index + 1) * 5, "text": f"Method beat {index + 1}."}
        for index in range(4)
    ]

    shots = [shot for shot in build_scene_timeline({"title": "Demo"}, slides, subtitles) if shot["slide_index"] == 2]

    assert [shot["shot_type"] for shot in shots] == ["process_map", "process_trace", "process_trace", "synthesis"]


def test_duplicate_placeholder_table_is_replaced_with_grounded_rows() -> None:
    slide = _normalize_slide(
        1,
        {
            "title": "Parallel Generation Speed",
            "purpose": "Highlight the efficiency gain.",
            "bullets": ["Parallel generation achieves a 6x speedup."],
            "visual_kind": "metrics",
            "visual_items": ["Sequential time", "Parallel time", "6x speedup"],
            "visual_table": [
                ["Aspect", "Focus", "Why it matters"],
                ["Architecture", "Architecture", "Keeps the demo grounded"],
            ],
        },
    )

    assert slide["visual_table"][1][0] == "Point 1"
    assert "6x speedup" in slide["visual_table"][1][1]
    assert "Architecture" not in " ".join(slide["visual_table"][1])


def test_metric_parser_recognizes_speedup_factor() -> None:
    cards = _metric_cards_from_items(["PaperTalker achieves a 6x speedup over sequential generation."])

    assert cards[0][0].lower() == "6x"


def test_metric_parser_preserves_minute_second_duration() -> None:
    cards = _metric_cards_from_items(["6:15 Average Video Duration"])

    assert cards == [("6:15", "Average video duration")]


def test_metric_card_focus_uses_named_method_over_generic_words() -> None:
    cards = _metric_cards_from_items(
        ["Sequential Generation Time", "PaperTalker Parallel Time", "6x Speedup Indicator"]
    )

    focus = _metric_card_focus(
        cards,
        "PaperTalker parallelizes generation across slides.",
        fallback=0,
    )

    assert cards[focus][1] == "PaperTalker Parallel Time"


def test_scene_director_fallback_varies_layouts_and_entrances() -> None:
    slides, report = plan_scene_directions(
        {"title": "Director Test"},
        [
            {"index": 1, "title": "Mechanism", "purpose": "Explain modules", "bullets": ["A module."], "visual_kind": "flow"},
            {"index": 2, "title": "Speed", "purpose": "Compare speed", "bullets": ["A 6x speedup."], "visual_kind": "metrics"},
            {"index": 3, "title": "Evidence", "purpose": "Show results", "bullets": ["An experiment."], "visual_kind": "table"},
        ],
        use_api=False,
    )

    assert report["mode"] == "deterministic_fallback"
    assert len({slide["scene_direction"]["layout"] for slide in slides}) == 3
    assert len({slide["scene_direction"]["entrance"] for slide in slides}) == 3


def test_scene_entrances_produce_distinct_intermediate_frames() -> None:
    layer = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle((10, 10, 50, 50), fill=(255, 255, 255, 255))

    frames = [_apply_scene_entrance(layer, entrance, 0.5) for entrance in ("fade_up", "slide_left", "slide_right", "scale_in", "wipe")]

    assert len({frame.tobytes() for frame in frames}) == 5


def test_image_generation_creates_multiple_assets_for_non_image_slides(tmp_path: Path, monkeypatch) -> None:
    calls: list[Path] = []

    def fake_image_api(_prompt: str, out: Path) -> tuple[bool, str]:
        Image.new("RGB", (640, 360), (20 + len(calls), 40, 60)).save(out)
        calls.append(out)
        return True, ""

    monkeypatch.setenv("AUTO_VIDEO_IMAGE_MODE", "all")
    monkeypatch.setenv("AUTO_VIDEO_IMAGES_PER_SLIDE", "2")
    monkeypatch.setenv("AUTO_VIDEO_IMAGE_VALIDATE", "0")
    monkeypatch.setattr("auto_research.video_pipeline._call_lumid_image", fake_image_api)
    slides = [
        {
            "index": 1,
            "title": "Parallel pipeline",
            "purpose": "Explain the mechanism.",
            "bullets": ["Independent tasks run in parallel.", "The method reports a 6x speedup."],
            "visual_kind": "flow",
            "visual_items": ["Input", "Parallel workers", "Output"],
        }
    ]

    results = generate_slide_images(slides, tmp_path, use_image_api=True)

    assert len(calls) == 2
    assert len(slides[0]["generated_image_paths"]) == 2
    assert len(slides[0]["visual_asset_paths"]) == 2
    assert all(item["ok"] for item in results)


def test_image_retry_prompt_uses_validator_feedback() -> None:
    prompt = _image_retry_prompt(
        "Create one illustration.",
        {
            "reasons": [
                "The image contains garbled text.",
                "It appears to be a screenshot of a presentation slide.",
            ]
        },
        attempt=2,
    )

    assert "previous image was rejected" in prompt.casefold()
    assert "no glyphs" in prompt.casefold()
    assert "borderless physical scene" in prompt.casefold()


def test_required_image_failure_stops_before_later_slides(tmp_path: Path, monkeypatch) -> None:
    calls = 0
    monkeypatch.setenv("AUTO_VIDEO_IMAGE_MODE", "image_only")
    monkeypatch.setenv("AUTO_VIDEO_IMAGES_PER_SLIDE", "1")
    monkeypatch.setenv("AUTO_VIDEO_IMAGE_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("AUTO_VIDEO_REQUIRE_MODEL_IMAGES", "1")
    monkeypatch.setenv("AUTO_VIDEO_FAIL_FAST_REQUIRED_IMAGES", "1")

    def failed_image_api(_prompt: str, _out: Path) -> tuple[bool, str]:
        nonlocal calls
        calls += 1
        return False, "provider unavailable"

    monkeypatch.setattr("auto_research.video_pipeline._call_lumid_image", failed_image_api)
    slides = [
        {"index": 1, "title": "Required scene", "visual_kind": "image", "bullets": ["Claim"]},
        {"index": 2, "title": "Later scene", "visual_kind": "image", "bullets": ["Claim"]},
    ]

    with pytest.raises(RuntimeError, match="Stopping immediately"):
        generate_slide_images(slides, tmp_path, use_image_api=True)

    assert calls == 1


def test_rejected_image_continues_with_explicit_structured_scene_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUTO_VIDEO_IMAGE_MODE", "image_only")
    monkeypatch.setenv("AUTO_VIDEO_IMAGES_PER_SLIDE", "1")
    monkeypatch.setenv("AUTO_VIDEO_IMAGE_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("AUTO_VIDEO_REQUIRE_MODEL_IMAGES", "0")
    monkeypatch.setenv("AUTO_VIDEO_FAIL_FAST_REQUIRED_IMAGES", "0")

    def fake_image_api(_prompt: str, out: Path) -> tuple[bool, str]:
        Image.new("RGB", (640, 360), "white").save(out)
        return True, ""

    monkeypatch.setattr("auto_research.video_pipeline._call_lumid_image", fake_image_api)
    monkeypatch.setattr(
        "auto_research.video_pipeline._validate_generated_slide_image",
        lambda _slide, _path: {
            "accepted": False,
            "relevance_score": 4,
            "complete_frame": True,
            "no_screenshot_or_document_crop": False,
            "no_readable_text": False,
            "reasons": ["Browser chrome and garbled text."],
        },
    )
    slide = {"index": 1, "title": "Challenge", "visual_kind": "image", "bullets": ["Claim"]}

    results = generate_slide_images([slide], tmp_path, use_image_api=True)

    assert results[0]["ok"] is False
    assert slide["visual_asset_paths"] == []
    assert slide["visual_asset_mode"] == "structured_scene_fallback"
    assert "Browser chrome" in slide["visual_generation_error"]


def test_normalize_slide_routes_diagrams_and_charts_to_structured_scenes() -> None:
    flow = _normalize_slide(
        1,
        {
            "title": "Tree Search",
            "visual_kind": "image",
            "visual_prompt": "Diagram showing tree search process selecting the best layout.",
        },
    )
    metrics = _normalize_slide(
        2,
        {
            "title": "Results",
            "visual_kind": "image",
            "visual_prompt": "Bar chart comparing performance against baselines.",
        },
    )

    assert flow["visual_kind"] == "flow"
    assert metrics["visual_kind"] == "metrics"


def test_scene_timeline_rotates_visual_assets_between_image_shots(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (640, 360), "red").save(first)
    Image.new("RGB", (640, 360), "blue").save(second)
    slide = {
        "index": 1,
        "title": "Visual mechanism",
        "purpose": "Show distinct visual beats.",
        "bullets": ["Problem", "Mechanism", "Result"],
        "visual_kind": "image",
        "visual_asset_paths": [str(first), str(second)],
    }
    subtitles = [
        {"slide_index": 1, "start_sec": i * 6, "end_sec": (i + 1) * 6, "text": f"Beat {i + 1}"}
        for i in range(4)
    ]

    timeline = build_scene_timeline({"title": "Assets"}, [slide], subtitles)
    image_shots = [shot for shot in timeline if shot["visual_asset_path"]]

    assert [shot["visual_asset_path"] for shot in image_shots] == [str(first), str(second)]


def test_paper_figures_are_assigned_by_page_text_without_reuse(tmp_path: Path) -> None:
    figure_a = tmp_path / "dataset.png"
    figure_b = tmp_path / "architecture.png"
    Image.new("RGB", (640, 360), "white").save(figure_a)
    Image.new("RGB", (640, 360), "black").save(figure_b)
    figures = [
        {"path": str(figure_a), "page_text": "benchmark dataset contains paired papers and author videos", "width": 640, "height": 360},
        {"path": str(figure_b), "page_text": "multi agent architecture coordinates slide speech and cursor modules", "width": 640, "height": 360},
    ]
    slides = [
        {"title": "Benchmark Dataset", "purpose": "Explain paired papers", "bullets": ["Author videos form the dataset."]},
        {"title": "Agent Architecture", "purpose": "Explain coordinated modules", "bullets": ["Agents coordinate speech and cursor."]},
    ]

    assign_paper_figures(slides, figures)

    assert slides[0]["paper_figure_paths"] == [str(figure_a)]
    assert slides[1]["paper_figure_paths"] == [str(figure_b)]


def test_image_prompt_is_specific_and_requires_complete_framing() -> None:
    prompt = _image_generation_prompt(
        {
            "title": "Cross-modal alignment",
            "purpose": "Synchronize narration with the current slide.",
            "bullets": [
                "The cursor follows the evidence currently being narrated.",
                "Subtitle timing is derived from the narration track.",
            ],
            "visual_caption": "Narration, cursor, and slide evidence move together.",
            "visual_prompt": "A synchronized three-lane timeline.",
        }
    )

    assert "synchronized three-lane timeline" in prompt
    assert "Cross-modal alignment" not in prompt
    assert "eight percent empty safe margin" in prompt
    assert "Keep every important object fully visible" in prompt
    assert "Full-bleed editorial vector illustration" in prompt
    assert "no nested canvas" in prompt
    assert "Synchronize narration with the current slide" not in prompt


def test_generated_image_uses_contain_instead_of_crop(tmp_path: Path) -> None:
    source = tmp_path / "wide.png"
    raw = Image.new("RGB", (400, 100), (240, 240, 240))
    source_draw = ImageDraw.Draw(raw)
    source_draw.rectangle((0, 0, 399, 99), outline=(255, 0, 0), width=8)
    raw.save(source)

    canvas = Image.new("RGB", (240, 240), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    slide = {"generated_image_path": str(source)}

    assert _draw_generated_image(draw, slide, (20, 20, 220, 220))

    pixels = canvas.load()
    red_pixels = sum(
        1
        for y in range(20, 220)
        for x in range(20, 220)
        if pixels[x, y][0] > 220 and pixels[x, y][1] < 40
    )
    assert red_pixels > 500


def test_paper_theme_tracks_domain_and_stays_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("AUTO_VIDEO_THEME", raising=False)

    medical = choose_paper_visual_theme(
        {"title": "Clinical Protein Response", "text": "A patient study of cellular protein response."}
    )
    physics = choose_paper_visual_theme(
        {"title": "Quantum Geometry", "text": "A mathematical theorem for quantum particle dynamics."}
    )
    unknown_source = {"title": "Unclassified Research Artifact", "text": "A deliberately neutral abstract."}

    assert medical == "bio"
    assert physics == "orbit"
    assert choose_paper_visual_theme(unknown_source) == choose_paper_visual_theme(unknown_source)
    assert choose_paper_visual_theme(unknown_source) in PAPER_VISUAL_THEMES


def test_scene_timeline_splits_slides_into_video_shots() -> None:
    source = {"title": "Scene Test", "text": "A compact research explanation."}
    slides = [
        {
            "index": 1,
            "title": "Research Question",
            "purpose": "Establish the problem.",
            "bullets": ["Static slides do not use temporal visual storytelling."],
            "visual_kind": "image",
        },
        {
            "index": 2,
            "title": "Method",
            "purpose": "Explain the pipeline.",
            "bullets": ["Parse evidence.", "Plan shots.", "Render motion."],
            "visual_kind": "flow",
            "visual_items": ["Evidence", "Shots", "Motion"],
        },
    ]
    subtitles = [
        {"slide_index": 1, "start_sec": 0, "speech_start_sec": 0.3, "speech_end_sec": 5.0, "end_sec": 6, "text": "The project begins with one research question."},
        {"slide_index": 2, "start_sec": 6, "end_sec": 11, "text": "First parse the evidence."},
        {"slide_index": 2, "start_sec": 11, "end_sec": 16, "text": "Then animate the planned shots."},
    ]

    timeline = build_scene_timeline(source, slides, subtitles)

    assert len(timeline) == 3
    assert timeline[0]["shot_type"] == "opener"
    assert timeline[0]["speech_start_sec"] == 0.3
    assert timeline[0]["speech_end_sec"] == 5.0
    assert timeline[1]["shot_type"] == "process_map"
    assert timeline[-1]["shot_type"] == "synthesis"
    assert timeline[-1]["motion"] == "takeaway_stack"
    assert all(shot["end_sec"] > shot["start_sec"] for shot in timeline)
    assert all(shot["hold_sec"] >= 1.5 for shot in timeline)


def test_four_beat_sections_use_distinct_video_compositions() -> None:
    source = {"title": "Variety Test"}
    slides = [
        {
            "index": 1,
            "title": "Pipeline",
            "purpose": "Explain the method.",
            "bullets": ["Input", "Reason", "Generate"],
            "visual_kind": "flow",
            "visual_items": ["Input", "Reason", "Generate"],
        }
    ]
    subtitles = [
        {"slide_index": 1, "start_sec": i * 6, "end_sec": (i + 1) * 6, "text": f"Beat {i + 1}"}
        for i in range(4)
    ]

    timeline = build_scene_timeline(source, slides, subtitles)

    assert [shot["shot_type"] for shot in timeline] == [
        "opener",
        "process_map",
        "process_trace",
        "synthesis",
    ]
    assert len({shot["background_stage"] for shot in timeline}) >= 2


def test_generated_media_uses_establishing_and_closeup_video_framing(tmp_path: Path) -> None:
    visual = tmp_path / "visual.png"
    Image.new("RGB", (1280, 720), "navy").save(visual)
    slide = {
        "index": 2,
        "title": "System overview",
        "purpose": "Explain the mechanism visually.",
        "bullets": ["Problem", "Architecture", "Result", "Takeaway"],
        "visual_kind": "image",
        "visual_asset_paths": [str(visual), str(visual)],
    }
    subtitles = [
        {"slide_index": 2, "start_sec": i * 6, "end_sec": (i + 1) * 6, "text": f"Beat {i + 1}."}
        for i in range(4)
    ]

    shots = build_scene_timeline({"title": "Demo"}, [slide], subtitles)

    assert [shot["shot_type"] for shot in shots] == [
        "media_establish",
        "media_detail",
        "key_claim",
        "synthesis",
    ]
    assert [shot["framing"] for shot in shots[:2]] == ["full_frame", "close_up"]
    assert all(shot["background_stage"] == "immersive" for shot in shots[:2])


def test_long_single_narration_can_split_without_short_shots() -> None:
    timeline = build_scene_timeline(
        {"title": "Long Beat"},
        [
            {
                "index": 1,
                "title": "Long Research Question",
                "purpose": "Introduce the paper.",
                "bullets": ["One complete claim."],
                "visual_kind": "image",
            }
        ],
        [{"slide_index": 1, "start_sec": 0, "end_sec": 14, "text": "A deliberately long narration beat."}],
    )

    assert len(timeline) == 2
    assert all(shot["duration_sec"] >= 5 for shot in timeline)
    assert all(shot["hold_sec"] >= 1.5 for shot in timeline)


def test_narration_pacing_uses_language_and_visual_type_bounds() -> None:
    assert _estimate_narration_duration("Short.") == 5
    assert _estimate_narration_duration("这是一个用于解释研究问题的较长中文旁白句子。") >= 5

    subtitles = build_subtitles(
        [
            {
                "index": 1,
                "speaker_note": "We begin with the research question.",
                "visual_kind": "image",
            },
            {
                "index": 2,
                "speaker_note": "First collect evidence. Then plan each scene.",
                "visual_kind": "flow",
            },
        ],
        seconds_per_slide=20,
    )

    assert subtitles[0]["end_sec"] - subtitles[0]["start_sec"] >= 6
    assert subtitles[1]["end_sec"] - subtitles[1]["start_sec"] >= 8
