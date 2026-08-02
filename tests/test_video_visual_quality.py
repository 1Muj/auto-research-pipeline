from pathlib import Path

from PIL import Image, ImageDraw

from auto_research.video_pipeline import (
    PAPER_VISUAL_THEMES,
    _estimate_narration_duration,
    build_scene_timeline,
    build_subtitles,
    choose_paper_visual_theme,
    _clean_display_text,
    _draw_generated_image,
    _image_generation_prompt,
)


def test_display_text_removes_ellipsis_without_cutting_content() -> None:
    text = _clean_display_text("Complete claim... with supporting evidence… and a conclusion.")

    assert "..." not in text
    assert "…" not in text
    assert "supporting evidence" in text
    assert text.endswith("conclusion.")


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
    assert timeline[1]["shot_type"] == "process"
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
        "process",
        "process_focus",
        "synthesis",
    ]
    assert len({shot["background_stage"] for shot in timeline}) >= 2


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
