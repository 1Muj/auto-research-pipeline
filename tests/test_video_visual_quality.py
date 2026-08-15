from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from auto_research.video_pipeline import (
    PAPER_VISUAL_THEMES,
    ANIMATION_EVENT_ACTIONS,
    _animated_metric_value,
    _animation_event_progress,
    _apply_hybrid_3d_camera,
    _estimate_narration_duration,
    _apply_scene_entrance,
    build_scene_timeline,
    build_subtitles,
    choose_paper_visual_theme,
    _clean_display_text,
    _draw_generated_image,
    _draw_scene_metric_wall,
    _image_generation_prompt,
    _paper_visual_context,
    _image_slide_eligible,
    _image_retry_prompt,
    _hybrid_3d_camera_state,
    _hybrid_3d_quad,
    _hybrid_project_point,
    _hybrid_metric_reveal_progress,
    _hybrid_metric_hero_copy,
    _hybrid_texture_layer,
    _is_summary_slide,
    _metric_cards_from_items,
    _metric_cards_are_qualitative,
    _metric_card_focus,
    _metric_scene_cards,
    _metric_scene_is_qualitative,
    _merge_scene_beats,
    _normalize_slide,
    _parse_page_visual_regions,
    _route_shot_visual_strategy,
    _scene_focus_index,
    _scene_cursor_target,
    _scene_item_detail,
    _scene_render_window,
    _should_draw_cursor_grounding_scene,
    _validate_generated_slide_image,
    assign_paper_figures,
    generate_slide_images,
    plan_scene_directions,
    select_slide_visual_assets,
)


def test_source_paper_figure_opens_relevant_section_before_generated_visuals() -> None:
    strategy, reason = _route_shot_visual_strategy(
        "The architecture runs slide generation in parallel for a six times speedup.",
        {
            "title": "Architecture",
            "purpose": "Explain the method",
            "visual_kind": "flow",
            "visual_asset_preference": "paper_figure",
        },
        beat_index=0,
        generated_assets=["generated.png"],
        paper_assets=["paper_figures/figure_4.png"],
    )

    assert strategy == "paper_figure"
    assert "visual comparison" in reason


def test_generated_visual_can_win_over_available_source_figure() -> None:
    strategy, reason = _route_shot_visual_strategy(
        "A researcher moves from manual editing to an automated workflow.",
        {
            "title": "Motivation",
            "purpose": "Explain the problem",
            "visual_kind": "image",
            "visual_asset_preference": "generated_scene",
        },
        beat_index=0,
        generated_assets=["generated.png"],
        paper_assets=["paper_figures/figure_1.png"],
    )

    assert strategy == "generated_scene"
    assert "visual comparison" in reason


def test_both_visual_candidates_are_sequenced_across_beats() -> None:
    strategy, _reason = _route_shot_visual_strategy(
        "The exact benchmark result is shown next.",
        {
            "title": "Results",
            "visual_kind": "image",
            "visual_asset_preference": "generated_scene",
            "visual_asset_comparison": {"winner": "both"},
        },
        beat_index=1,
        generated_assets=["generated.png"],
        paper_assets=["paper_figures/table_2.png"],
    )

    assert strategy == "paper_figure"


def test_visual_asset_selection_uses_available_candidate_without_comparison(tmp_path: Path) -> None:
    generated = tmp_path / "generated.png"
    Image.new("RGB", (320, 180), "white").save(generated)
    slides = [
        {
            "index": 1,
            "title": "Concept",
            "visual_kind": "image",
            "paper_figure_paths": [],
            "generated_image_paths": [str(generated)],
        }
    ]

    decisions = select_slide_visual_assets(slides, tmp_path, use_vlm=False)

    assert decisions[0]["winner"] == "generated"
    assert slides[0]["visual_asset_preference"] == "generated_scene"
    assert slides[0]["visual_asset_paths"] == [str(generated)]


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


def test_process_focus_matches_inflected_mechanism_terms() -> None:
    detail = _scene_item_detail(
        {
            "speaker_note": "Academic papers present dense text and complex figures that require precise alignment.",
            "bullets": ["Generation coordinates aligned speech, slides, and subtitles."],
            "purpose": "Explain multi-channel alignment complexity.",
        },
        "Dense paper text",
    )

    assert detail.startswith("Academic papers present dense text")


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


def test_structured_scene_cursor_uses_rendered_layout_coordinates() -> None:
    target = _scene_cursor_target(
        {"shot_type": "process_map", "focus_index": 2},
        planned_x=91,
        planned_y=16,
    )

    assert target == (59.0, 49.0)


def test_generic_grounding_word_does_not_trigger_cursor_diagram_in_conclusion() -> None:
    slide = {"title": "Conclusion and Future Work"}
    shot = {
        "shot_type": "data_conclusion",
        "narration": "Advanced visual search and grounding produces faithful presentations.",
    }

    assert not _should_draw_cursor_grounding_scene(slide, shot)


def test_explicit_cursor_grounding_still_uses_alignment_diagram() -> None:
    slide = {"title": "Precise Alignment and Grounding"}
    shot = {
        "shot_type": "data_focus",
        "narration": "Computer-use grounding models provide spatial-temporal cursor alignment.",
    }

    assert _should_draw_cursor_grounding_scene(slide, shot)


def test_story_image_mode_targets_concept_and_method_scenes() -> None:
    assert _image_slide_eligible("story", "image")
    assert _image_slide_eligible("story", "flow")
    assert not _image_slide_eligible("story", "metrics")
    assert not _image_slide_eligible("story", "table")
    assert _image_slide_eligible("compare", "metrics", has_source_candidate=True)
    assert not _image_slide_eligible("compare", "metrics", has_source_candidate=False)


def test_page_visual_region_parser_converts_percent_bbox_to_pixels() -> None:
    regions = _parse_page_visual_regions(
        '{"regions":[{"kind":"figure","label":"Figure 4","caption":"Architecture","bbox_percent":[10,20,90,55]}]}',
        width=1200,
        height=1600,
    )

    assert len(regions) == 1
    assert regions[0]["label"] == "Figure 4"
    left, top, right, bottom = regions[0]["crop_box"]
    assert left < 120
    assert top < 320
    assert right > 1080
    assert bottom > 880


def test_page_visual_region_parser_rejects_whole_page_crop() -> None:
    regions = _parse_page_visual_regions(
        '{"regions":[{"kind":"figure","bbox_percent":[0,0,100,100]}]}',
        width=1200,
        height=1600,
    )

    assert regions == []


def test_flow_section_uses_validated_scene_before_procedural_steps(tmp_path: Path) -> None:
    visual = tmp_path / "method.png"
    Image.new("RGB", (1280, 720), "navy").save(visual)
    slide = {
        "index": 1,
        "title": "Multi-Agent Method",
        "visual_kind": "flow",
        "visual_asset_paths": [str(visual)],
        "bullets": ["Plan", "Generate", "Evaluate"],
        "visual_items": ["Plan", "Generate", "Evaluate"],
    }
    subtitles = [
        {"slide_index": 1, "start_sec": i * 6, "end_sec": (i + 1) * 6, "text": text}
        for i, text in enumerate(
            ["The method coordinates agents.", "Then it generates scenes.", "Finally it evaluates the result."]
        )
    ]

    shots = build_scene_timeline({"title": "Demo"}, [slide], subtitles)

    assert shots[0]["shot_type"] == "media_establish"
    assert shots[0]["visual_asset_kind"] == "generated"
    assert shots[1]["shot_type"] in {"process_map", "process_trace"}


def test_flow_image_prompt_requires_text_free_physical_metaphor() -> None:
    prompt = _image_generation_prompt(
        {
            "visual_kind": "flow",
            "title": "Tree Search Visual Choice",
            "bullets": ["LaTeX code is debugged before VLM selection."],
        }
    ).casefold()

    assert "text-free physical metaphor" in prompt
    assert "do not draw a labelled flowchart" in prompt
    assert "never reproduce wording" in prompt


def test_conclusion_metrics_are_routed_to_summary_shots() -> None:
    slide = {
        "index": 2,
        "title": "Conclusion and Future Work",
        "visual_kind": "metrics",
        "bullets": ["Main contribution", "Practical value", "Future direction"],
    }
    subtitles = [
        {"slide_index": 2, "start_sec": i * 6, "end_sec": (i + 1) * 6, "text": text}
        for i, text in enumerate(
            [
                "The system automates the complete pipeline.",
                "Cursor grounding reduces production effort.",
                "Future work adds interactive formats.",
            ]
        )
    ]

    shots = build_scene_timeline({"title": "Demo"}, [slide], subtitles)

    assert _is_summary_slide(slide)
    assert [shot["shot_type"] for shot in shots] == ["key_claim", "contrast", "synthesis"]
    assert all(shot["visual_strategy"] == "kinetic_text" for shot in shots)


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


def test_metric_parser_separates_value_from_semantic_unit() -> None:
    cards = _metric_cards_from_items(["101 paper-video pairs", "16 slides per video"])

    assert cards[0] == ("101", "Paper-video pairs")
    assert cards[1] == ("16", "Average slides per video")


def test_metric_scene_prefers_real_statistics_over_ordinal_placeholders() -> None:
    cards = _metric_scene_cards(
        {
            "visual_items": ["Faithful explanations", "101 paper-video pairs"],
            "bullets": ["The benchmark spans multiple research domains."],
        },
        {"narration": "The dataset contains 101 paired papers and videos."},
    )

    assert cards[0][0] == "101"
    assert not _metric_cards_are_qualitative(cards)


def test_metric_scene_prefers_structured_table_values_and_preserves_duration() -> None:
    cards = _metric_scene_cards(
        {
            "visual_table": [
                ["Metric", "Value", "Meaning"],
                ["Papers", "101", "Dataset size"],
                ["Avg Slides", "16.0", "Presentation length"],
                ["Avg Duration", "6:15", "Video time"],
            ],
            "visual_items": ["101 Paired Papers", "16 Avg Slides", "6m 15s Avg Duration"],
        },
        {"narration": "The benchmark contains 101 paired papers."},
    )

    assert cards == [
        ("101", "Paper-video pairs"),
        ("16", "Average slides per video"),
        ("6:15", "Average video duration"),
    ]


def test_qualitative_metric_scene_uses_each_structured_table_row_as_its_own_module() -> None:
    cards = _metric_scene_cards(
        {
            "visual_table": [
                ["Metric", "Mechanism", "Evaluation Target"],
                ["Meta Similarity", "VLM alignment check", "Slide/Subtitle fidelity"],
                ["PresentArena", "Double-order pairwise comparison", "Video quality ranking"],
                ["PresentQuiz", "Paper-derived question answering", "Knowledge conveyance"],
                ["IP Memory", "Author-work association", "Research visibility impact"],
            ],
            "bullets": ["A deliberately long paragraph that must not merge two metric modules."],
        },
        {"narration": "The paper introduces tailored evaluation methods."},
    )

    assert cards == [
        ("01", "Meta Similarity: VLM alignment check — Slide/Subtitle fidelity"),
        ("02", "PresentArena: Double-order pairwise comparison — Video quality ranking"),
        ("03", "PresentQuiz: Paper-derived question answering — Knowledge conveyance"),
        ("04", "IP Memory: Author-work association — Research visibility impact"),
    ]


def test_qualitative_findings_are_not_treated_as_numeric_metrics() -> None:
    cards = _metric_scene_cards(
        {"bullets": ["Higher faithfulness", "Better information coverage", "Practical generation"]},
        {"narration": "The method improves the overall viewing experience."},
    )

    assert _metric_cards_are_qualitative(cards)
    assert all("Supports current explanation" not in label for _value, label in cards)


def test_qualitative_scene_detection_uses_source_content_not_small_number_heuristics() -> None:
    qualitative_slide = {
        "bullets": [
            "Long-context inputs from research papers with dense text.",
            "Multi-modal information including figures, tables, and text.",
            "Coordination of slides, subtitles, speech, and talker channels.",
        ]
    }
    numeric_slide = {"bullets": ["The study evaluates 8 systems across 33 scenes."]}

    assert _metric_scene_is_qualitative(qualitative_slide, {"narration": "These are three challenges."})
    assert not _metric_scene_is_qualitative(numeric_slide, {"narration": "The result is measurable."})


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


def test_image_prompt_includes_paper_background_and_section_specificity() -> None:
    source = {
        "title": "PaperTalker: Paper to Presentation Video Generation",
        "authors": "Research Team",
        "text": (
            "Abstract PaperTalker generates academic presentation videos from research papers. "
            "It coordinates slide generation, narration, cursor grounding, and evaluation using specialized agents. "
            "The Paper2Video benchmark contains paired papers and author-recorded presentation videos. "
            "Introduction Existing systems often lose cross-modal alignment."
        ),
    }
    slides = [
        {
            "index": 1,
            "title": "Agent Architecture",
            "purpose": "Explain coordination between specialized agents.",
            "bullets": ["Slide, narration, and cursor agents share a synchronized plan."],
            "visual_kind": "flow",
            "visual_prompt": "Show coordinated agents producing aligned video layers.",
        }
    ]

    context = _paper_visual_context(source, slides)
    prompt = _image_generation_prompt(slides[0], paper_context=context)

    assert "PaperTalker: Paper to Presentation Video Generation" in context
    assert "Paper2Video benchmark" in context
    assert "Agent Architecture" in prompt
    assert "cursor agents" in prompt
    assert "generic paper pages transforming into a video" in prompt


def test_image_variants_use_distinct_art_directions() -> None:
    slide = {
        "index": 2,
        "title": "Grounded alignment",
        "purpose": "Explain temporal grounding.",
        "bullets": ["Narration and cursor timing share one plan.", "Evidence is highlighted at the right moment."],
        "visual_kind": "flow",
    }

    wide = _image_generation_prompt(slide, variant_index=0)
    detail = _image_generation_prompt(slide, variant_index=1)

    assert wide != detail
    assert "editorial collage" in wide.casefold()
    assert "scientific cutaway" in detail.casefold()


def test_second_generated_asset_gets_its_own_detail_scene() -> None:
    strategy, reason = _route_shot_visual_strategy(
        "The next mechanism aligns the cursor with narration timing.",
        {"visual_kind": "flow", "title": "Alignment", "purpose": "Explain the mechanism"},
        beat_index=1,
        generated_assets=["wide.png", "detail.png"],
        paper_assets=[],
    )

    assert strategy == "generated_scene"
    assert "distinct generated detail" in reason


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


def test_generated_image_survives_temporary_vlm_outage(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "generated.png"
    Image.new("RGB", (1280, 720), "white").save(image_path)
    monkeypatch.setattr("auto_research.video_pipeline._call_openai_vision", lambda _prompt, _path: None)

    result = _validate_generated_slide_image(
        {"title": "Mechanism", "purpose": "Explain the method", "bullets": ["A grounded claim."]},
        image_path,
    )

    assert result["accepted"] is True
    assert result["validator_available"] is False
    assert result["validation_mode"] == "renderability_fallback"
    assert result["dimensions"] == [1280, 720]


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


def test_normalize_slide_repairs_metric_title_when_body_is_architecture() -> None:
    slide = _normalize_slide(
        1,
        {
            "title": "Novel Evaluation Metrics",
            "purpose": "Explain the complete PaperTalker multi-agent architecture.",
            "bullets": ["The system architecture coordinates slide and cursor agents."],
            "visual_kind": "flow",
        },
    )

    assert slide["title"] == "PaperTalker System Architecture"


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


def test_complete_page_region_is_ranked_before_embedded_example_image(tmp_path: Path) -> None:
    region = tmp_path / "figure_2.png"
    embedded = tmp_path / "example.png"
    Image.new("RGB", (900, 500), "white").save(region)
    Image.new("RGB", (1000, 700), "black").save(embedded)
    figures = [
        {
            "path": str(embedded),
            "page_text": "benchmark dataset papers videos statistics average slides duration",
            "width": 1000,
            "height": 700,
            "extraction_mode": "embedded_image",
        },
        {
            "path": str(region),
            "page_text": "Figure 2 Paper2Video benchmark statistics",
            "width": 900,
            "height": 500,
            "extraction_mode": "rendered_page_region",
        },
    ]
    slides = [
        {
            "title": "Paper2Video Benchmark",
            "purpose": "Present benchmark statistics",
            "bullets": ["The benchmark contains paired papers and videos."],
        }
    ]

    assign_paper_figures(slides, figures)

    assert slides[0]["paper_figure_paths"] == [str(region)]


def test_complete_source_region_survives_temporary_vlm_outage(tmp_path: Path, monkeypatch) -> None:
    region = tmp_path / "architecture.png"
    Image.new("RGB", (900, 500), "white").save(region)
    slides = [
        {
            "title": "System Architecture",
            "purpose": "Explain the agent architecture",
            "bullets": ["The architecture coordinates slide, cursor, and speech agents."],
        }
    ]
    figures = [
        {
            "path": str(region),
            "page_text": "Figure 4 system architecture coordinates slide cursor speech agents",
            "width": 900,
            "height": 500,
            "extraction_mode": "rendered_page_region",
        }
    ]
    monkeypatch.setattr(
        "auto_research.video_pipeline._validate_paper_figure_for_slide",
        lambda _slide, _path: {
            "accepted": False,
            "validator_available": False,
            "relevance_score": 0.0,
            "is_source_evidence": False,
            "reasons": ["No valid VLM decision."],
        },
    )

    assign_paper_figures(slides, figures, validate_with_vlm=True)

    assert slides[0]["paper_figure_paths"] == [str(region)]
    assert "VLM unavailable" in slides[0]["paper_figure_validation"][0]["reasons"][0]


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
    assert "Cross-modal alignment" in prompt
    assert "eight percent empty safe margin" in prompt
    assert "Keep every important object fully visible" in prompt
    assert "Full-bleed editorial vector illustration" in prompt
    assert "no nested canvas" in prompt
    assert "Synchronize narration with the current slide" in prompt
    assert "never reproduce wording from the prompt inside the image" in prompt


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
    assert timeline[0]["shot_type"] == "key_claim"
    assert timeline[0]["visual_strategy"] == "kinetic_text"
    assert timeline[0]["speech_start_sec"] == 0.3
    assert timeline[0]["speech_end_sec"] == 5.0
    assert timeline[1]["shot_type"] == "process_map"
    assert timeline[-1]["shot_type"] == "synthesis"
    assert timeline[-1]["motion"] == "takeaway_stack"
    assert all(shot["end_sec"] > shot["start_sec"] for shot in timeline)
    assert all(shot["hold_sec"] >= 1.5 for shot in timeline)
    assert all(shot["hold_sec"] <= 2.5 for shot in timeline)
    assert all(shot["entrance_sec"] < shot["animation_sec"] for shot in timeline)


def test_hybrid_3d_plan_selects_a_restrained_spread_of_spatial_shots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTO_VIDEO_HYBRID_3D", "1")
    monkeypatch.setenv("AUTO_VIDEO_HYBRID_3D_RATIO", "0.30")
    slides = [
        {
            "index": index,
            "title": f"Section {index}",
            "purpose": "Explain one mechanism.",
            "bullets": ["Input", "Operation", "Result"],
            "visual_items": ["Input", "Operation", "Result"],
            "visual_kind": "flow" if index % 2 else "metrics",
        }
        for index in range(1, 5)
    ]
    subtitles = [
        {
            "slide_index": slide_index,
            "start_sec": (slide_index - 1) * 18 + beat * 6,
            "end_sec": (slide_index - 1) * 18 + (beat + 1) * 6,
            "text": f"Section {slide_index} beat {beat + 1} explains the mechanism.",
        }
        for slide_index in range(1, 5)
        for beat in range(3)
    ]

    timeline = build_scene_timeline({"title": "Spatial Test"}, slides, subtitles)
    spatial = [shot for shot in timeline if shot["render_mode"] == "hybrid_3d"]

    assert 0.20 <= len(spatial) / len(timeline) <= 0.40
    assert len({shot["slide_index"] for shot in spatial}) >= 3
    assert all(shot["shot_type"] != "title_card" for shot in spatial)
    assert all(shot["spatial_stage"]["hud_is_flat"] for shot in spatial)
    assert all("narration" in shot["hud_layers"] for shot in spatial)


def test_hybrid_3d_camera_is_bounded_smooth_and_keeps_content_visible() -> None:
    shot = {
        "render_mode": "hybrid_3d",
        "spatial_stage": {"camera_motion": "soft_orbit"},
    }
    states = [_hybrid_3d_camera_state(shot, step / 20) for step in range(21)]
    assert max(abs(state["dx"]) for state in states) <= 12
    assert max(abs(state["yaw_px"]) for state in states) <= 10
    assert max(
        abs(states[index + 1]["yaw_px"] - states[index]["yaw_px"])
        for index in range(len(states) - 1)
    ) < 1.5

    quad = _hybrid_3d_quad(640, 360, shot, 0.5)
    assert all(0 <= x <= 640 and 0 <= y <= 360 for x, y in quad)

    layer = Image.new("RGBA", (640, 360), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((80, 70, 560, 290), radius=16, fill=(30, 180, 160, 255))
    projected = _apply_hybrid_3d_camera(layer, shot, 0.5)
    assert projected.size == layer.size
    assert projected.getbbox() is not None
    assert projected.getchannel("A").getbbox() is not None


def test_object_space_camera_creates_depth_dependent_parallax() -> None:
    shot = {"spatial_stage": {"camera_motion": "truck_left"}}
    near_start = _hybrid_project_point((180, 0, 40), width=1280, height=720, shot=shot, local=0.0)
    near_end = _hybrid_project_point((180, 0, 40), width=1280, height=720, shot=shot, local=1.0)
    far_start = _hybrid_project_point((180, 0, 620), width=1280, height=720, shot=shot, local=0.0)
    far_end = _hybrid_project_point((180, 0, 620), width=1280, height=720, shot=shot, local=1.0)

    near_motion = abs(near_end[0] - near_start[0])
    far_motion = abs(far_end[0] - far_start[0])
    assert near_motion > far_motion


def test_moving_texture_plane_uses_antialiased_boundary_mask(tmp_path: Path) -> None:
    texture_path = tmp_path / "texture.png"
    Image.new("RGB", (160, 90), (240, 245, 250)).save(texture_path)

    layer = _hybrid_texture_layer(
        str(texture_path),
        quad=[(23.25, 18.5), (181.75, 21.25), (176.5, 109.75), (19.5, 106.25)],
        canvas_size=(220, 130),
        opacity=1.0,
    )

    assert layer is not None
    alpha_histogram = layer.getchannel("A").histogram()
    assert alpha_histogram[0] > 0
    assert alpha_histogram[255] > 0
    assert any(alpha_histogram[1:255])


def test_metric_wall_keeps_model_labels_above_large_values() -> None:
    class RecordingDraw:
        def __init__(self) -> None:
            self.text_calls: list[tuple[tuple[int, int], str]] = []

        def rounded_rectangle(self, *_args: object, **_kwargs: object) -> None:
            pass

        def rectangle(self, *_args: object, **_kwargs: object) -> None:
            pass

        def textbbox(self, _xy: tuple[int, int], text: str, **_kwargs: object) -> tuple[int, int, int, int]:
            return (0, 0, len(text) * 8, 18)

        def text(self, xy: tuple[int, int], text: str, **_kwargs: object) -> None:
            self.text_calls.append((xy, text))

    draw = RecordingDraw()
    box = (76, 182, 1204, 510)

    _draw_scene_metric_wall(
        draw,
        [("85.4%", "PresentQuiz"), ("0.92", "Meta Similarity"), ("Win Rate 68%", "PresentArena")],
        box,
        shot={"animation_events": []},
        focus_index=0,
        reveal=1.0,
        accent=(34, 211, 185),
        fonts={"small": None, "number": None},
    )

    positions = {text: xy for xy, text in draw.text_calls}
    assert positions["PresentQuiz"][1] == box[1] + 18
    assert positions["85.4%"][1] == box[1] + 52
    assert positions["PresentArena"][1] < positions["Win Rate 68%"][1]


def test_scene_preview_window_is_explicit_and_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    timeline = [{"start_sec": 5.0, "end_sec": 25.0}]
    monkeypatch.setenv("AUTO_VIDEO_PREVIEW_START_SEC", "12")
    monkeypatch.setenv("AUTO_VIDEO_PREVIEW_DURATION_SEC", "20")

    assert _scene_render_window(timeline) == (12.0, 25.0)


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
        "process_map",
        "process_trace",
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


def test_one_slide_routes_each_narration_beat_to_its_own_visual_strategy(tmp_path: Path) -> None:
    visual = tmp_path / "scene.png"
    Image.new("RGB", (1280, 720), "navy").save(visual)
    slide = {
        "index": 1,
        "title": "PaperTalker overview",
        "purpose": "Explain the idea and evidence.",
        "bullets": ["Motivation", "Pipeline", "Six-times speedup", "Takeaway"],
        "visual_kind": "image",
        "visual_asset_paths": [str(visual)],
    }
    subtitles = [
        {"slide_index": 1, "start_sec": 0, "end_sec": 6, "text": "Researchers struggle to create academic videos manually."},
        {"slide_index": 1, "start_sec": 6, "end_sec": 12, "text": "The pipeline coordinates specialized agents."},
        {"slide_index": 1, "start_sec": 12, "end_sec": 18, "text": "Parallel generation provides a 6x speedup."},
        {"slide_index": 1, "start_sec": 18, "end_sec": 24, "text": "The system therefore makes paper explanations practical."},
    ]

    shots = build_scene_timeline({"title": "Demo"}, [slide], subtitles)

    assert [shot["visual_strategy"] for shot in shots] == [
        "generated_scene",
        "procedural_diagram",
        "procedural_chart",
        "kinetic_text",
    ]
    assert [shot["asset_source"] for shot in shots] == ["generated", "renderer", "renderer", "renderer"]


def test_scene_timeline_emits_semantic_animation_events() -> None:
    slides = [
        {
            "index": 1,
            "title": "Tree Search Visual Choice",
            "purpose": "Explore and select the best layout branch.",
            "bullets": ["Generate candidates", "Score layouts", "Select the winner"],
            "visual_items": ["Candidate A", "Candidate B", "Candidate C"],
            "visual_kind": "flow",
        },
        {
            "index": 2,
            "title": "Parallel Generation",
            "purpose": "Compare sequential and parallel slide generation.",
            "bullets": ["Sequential queue", "Parallel lanes", "Faster result"],
            "visual_kind": "flow",
        },
        {
            "index": 3,
            "title": "Benchmark Scale",
            "purpose": "Present measurable dataset statistics.",
            "bullets": ["101 paired papers"],
            "visual_kind": "metrics",
        },
    ]
    subtitles = [
        {"slide_index": 1, "start_sec": 0, "end_sec": 8, "text": "Tree search expands candidates and selects the best layout branch."},
        {"slide_index": 2, "start_sec": 8, "end_sec": 16, "text": "Parallel generation runs independent slide tasks at the same time."},
        {"slide_index": 3, "start_sec": 16, "end_sec": 24, "text": "The benchmark contains 101 paired papers."},
    ]

    timeline = build_scene_timeline({"title": "Animation Test"}, slides, subtitles)
    actions = [{event["action"] for event in shot["animation_events"]} for shot in timeline]

    assert {"expand_branch", "score_candidates", "select_winner"} <= actions[0]
    assert {"sequential_progress", "parallel_progress"} <= actions[1]
    assert {"count_up", "grow_bar"} <= actions[2]
    assert all(action in ANIMATION_EVENT_ACTIONS for shot_actions in actions for action in shot_actions)
    assert all(event["duration_sec"] > 0 for shot in timeline for event in shot["animation_events"])


def test_qualitative_chart_reveals_modules_without_counting_fake_values() -> None:
    timeline = build_scene_timeline(
        {"title": "Qualitative Animation"},
        [
            {
                "index": 1,
                "title": "Distinctive Challenges",
                "purpose": "Explain long-context and multi-modal alignment challenges.",
                "bullets": [
                    "Long-context inputs from research papers with dense text.",
                    "Multi-modal information including figures, tables, and text.",
                    "Coordination of slides, subtitles, speech, and talker channels.",
                ],
                "visual_kind": "metrics",
            }
        ],
        [
            {
                "slide_index": 1,
                "start_sec": 0,
                "end_sec": 9,
                "text": "Coordinating slides, subtitles, speech, and talker channels is difficult.",
            }
        ],
    )

    actions = {event["action"] for event in timeline[0]["animation_events"]}

    assert {"reveal_node", "flow_token", "highlight_result"} <= actions
    assert "count_up" not in actions
    assert "grow_bar" not in actions


def test_animation_event_progress_obeys_its_time_window() -> None:
    shot = {
        "animation_events": [
            {"action": "flow_token", "start_fraction": 0.2, "duration_fraction": 0.4}
        ]
    }

    assert _animation_event_progress(shot, "flow_token", 0.1) == 0
    assert 0 < _animation_event_progress(shot, "flow_token", 0.4) < 1
    assert _animation_event_progress(shot, "flow_token", 0.8) == 1


def test_metric_values_count_up_without_changing_final_evidence() -> None:
    assert _animated_metric_value("101", 0.5) == "50"
    assert _animated_metric_value("6:15", 0.5) == "3:08"
    assert _animated_metric_value("6x", 1.0) == "6x"


def test_hybrid_metric_reveal_locks_real_value_in_under_one_second() -> None:
    shot = {"duration_sec": 10.0}

    assert _hybrid_metric_reveal_progress(shot, 0.0) == 0
    assert _hybrid_metric_reveal_progress(shot, 0.05) < 1
    assert _hybrid_metric_reveal_progress(shot, 0.1) == 1


def test_single_metric_hero_uses_model_copy_instead_of_parser_damaged_label() -> None:
    title, detail = _hybrid_metric_hero_copy(
        {"animation_labels": {"secondary": "Parallel agent processing"}},
        {
            "focus_text": (
                "Slide-wise parallelization across independent slides achieves a generation "
                "speedup of more than 6x compared to sequential methods."
            )
        },
        "generation speedup more than compared to sequential methods",
    )

    assert title == "Parallel agent processing"
    assert detail.endswith("more than 6x compared to sequential methods.")


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
