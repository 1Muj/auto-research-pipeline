from pathlib import Path

from PIL import Image, ImageDraw

from auto_research.video_pipeline import (
    PAPER_VISUAL_THEMES,
    build_scene_timeline,
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

    assert "Cross-modal alignment" in prompt
    assert "cursor follows the evidence" in prompt
    assert "eight percent empty safe margin" in prompt
    assert "Do not crop" in prompt
    assert "generic technology theme" in prompt


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
        {"slide_index": 1, "start_sec": 0, "end_sec": 6, "text": "The project begins with one research question."},
        {"slide_index": 2, "start_sec": 6, "end_sec": 11, "text": "First parse the evidence."},
        {"slide_index": 2, "start_sec": 11, "end_sec": 16, "text": "Then animate the planned shots."},
    ]

    timeline = build_scene_timeline(source, slides, subtitles)

    assert len(timeline) == 4
    assert timeline[0]["shot_type"] == "opener"
    assert timeline[2]["shot_type"] == "process"
    assert timeline[-1]["motion"] == "sequential_nodes"
    assert all(shot["end_sec"] > shot["start_sec"] for shot in timeline)
