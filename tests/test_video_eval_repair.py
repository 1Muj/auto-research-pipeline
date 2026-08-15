from __future__ import annotations

import json
from pathlib import Path

from auto_research.video_eval_repair import _load_visual_asset_state, _restore_visual_assets


def test_eval_repair_restores_selected_generated_and_source_assets(tmp_path: Path) -> None:
    generated = tmp_path / "generated_images" / "slide_01.png"
    source = tmp_path / "paper_figures" / "page_02_region_01.png"
    generated.parent.mkdir()
    source.parent.mkdir()
    generated.write_bytes(b"generated")
    source.write_bytes(b"source")
    (tmp_path / "visual_asset_selection.json").write_text(
        json.dumps(
            [
                {
                    "slide_index": 1,
                    "winner": "generated",
                    "generated_paths": [str(generated)],
                    "source_paths": [str(source)],
                    "selected_order": [str(generated), str(source)],
                    "scores": {"generated": 9, "source": 4},
                }
            ]
        ),
        encoding="utf-8",
    )

    state = _load_visual_asset_state(tmp_path, [{"index": 1, "title": "Old title"}])
    repaired = [{"index": 1, "title": "Rewritten title", "visual_kind": "image"}]

    assert _restore_visual_assets(repaired, state) == 1
    assert repaired[0]["generated_image_paths"] == [str(generated)]
    assert repaired[0]["paper_figure_paths"] == [str(source)]
    assert repaired[0]["visual_asset_paths"] == [str(generated), str(source)]
    assert repaired[0]["visual_asset_preference"] == "generated_scene"


def test_eval_repair_drops_missing_assets(tmp_path: Path) -> None:
    (tmp_path / "visual_asset_selection.json").write_text(
        json.dumps(
            [
                {
                    "slide_index": 1,
                    "winner": "generated",
                    "generated_paths": [str(tmp_path / "missing.png")],
                    "selected_order": [str(tmp_path / "missing.png")],
                }
            ]
        ),
        encoding="utf-8",
    )
    state = _load_visual_asset_state(tmp_path, [{"index": 1}])
    repaired = [{"index": 1, "visual_kind": "image"}]

    assert _restore_visual_assets(repaired, state) == 0
    assert "visual_asset_paths" not in repaired[0]
