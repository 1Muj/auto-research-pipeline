from __future__ import annotations

from pathlib import Path

from auto_research.blender_operator import (
    build_operator_manifest,
    normalize_asset_path,
    partition_operator_shots,
)


def test_normalize_private_tmp_asset_path() -> None:
    assert normalize_asset_path("/private/tmp/run/image.png") == "/tmp/run/image.png"


def test_partition_is_shot_aligned_and_adds_operator_contract() -> None:
    shots = [
        {"shot_id": "a", "start_sec": 0, "end_sec": 4, "shot_type": "media_establish"},
        {"shot_id": "b", "start_sec": 4, "end_sec": 8, "shot_type": "process_map"},
        {"shot_id": "c", "start_sec": 8, "end_sec": 12, "shot_type": "data_focus"},
    ]
    parts = partition_operator_shots(shots, max_shots=2, start_sec=3, duration_sec=7)
    assert [part["shot_ids"] for part in parts] == [["a", "b"], ["c"]]
    assert parts[0]["shots"][0]["operator_action"] == "documentary_establish"
    assert parts[0]["shots"][0]["hud_layer"]["keep_flat_to_camera"] is True


def test_manifest_preserves_grounding_contract(tmp_path: Path) -> None:
    manifest = build_operator_manifest(
        source={"title": "Paper", "authors": "Author"},
        slides=[],
        subtitles=[],
        timeline=[{"shot_id": "a", "start_sec": 0, "end_sec": 3, "shot_type": "title_card"}],
        out_dir=tmp_path,
        audio_path="/private/tmp/audio.wav",
        max_shots=1,
    )
    assert manifest["backend"] == "blender_operator"
    assert manifest["operator_protocol"] == "blender_mcp"
    assert manifest["audio_path"] == "/tmp/audio.wav"
    assert manifest["render_contract"]["no_default_labels"] is True
    assert manifest["parts"][0]["shots"][0]["operator_action"] == "title_reveal"

