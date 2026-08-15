"""Blender-operator handoff for scene-based paper video rendering.

The existing pipeline remains responsible for paper parsing, storyboarding,
assets, subtitles, TTS, and evaluation.  This module serializes that semantic
timeline into small, independently renderable Blender jobs.  A Blender MCP
operator (or a local Blender script) can consume the jobs without having to
reconstruct the research content from pixels.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Iterable


_ACTION_BY_SHOT_TYPE: dict[str, str] = {
    "title_card": "title_reveal",
    "media_establish": "documentary_establish",
    "media_detail": "documentary_push_in",
    "process_map": "mechanism_node_field",
    "process_trace": "mechanism_camera_trace",
    "evidence_board": "evidence_wall_scan",
    "evidence_closeup": "evidence_closeup",
    "data_landscape": "data_stage_establish",
    "data_focus": "data_focus_dolly",
    "data_detail": "data_chart_scan",
    "data_conclusion": "result_lockup",
    "contrast": "split_world_compare",
    "synthesis": "takeaway_orbit",
    "key_claim": "claim_reveal",
}


def normalize_asset_path(value: Any) -> str:
    """Return an absolute path that is portable between macOS temp aliases."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("/private/tmp/"):
        raw = "/tmp/" + raw.removeprefix("/private/tmp/")
    return str(Path(raw).expanduser())


def _shot_action(shot: dict[str, Any]) -> str:
    explicit = str(shot.get("operator_action") or "").strip()
    if explicit:
        return explicit
    motion = str(shot.get("motion") or "").strip()
    if motion:
        return motion
    return _ACTION_BY_SHOT_TYPE.get(str(shot.get("shot_type") or ""), "narrative_stage")


def _operator_shot(shot: dict[str, Any]) -> dict[str, Any]:
    """Keep semantic content while adding a concrete Blender action contract."""

    result = dict(shot)
    result["visual_asset_path"] = normalize_asset_path(result.get("visual_asset_path"))
    result["operator_action"] = _shot_action(result)
    result["hud_layer"] = {
        "headline": str(result.get("headline") or "").strip(),
        "focus_text": str(result.get("focus_text") or "").strip(),
        "show_numbers_only_if_grounded": True,
        "keep_flat_to_camera": True,
    }
    result["spatial_stage"] = {
        "scene_family": str(result.get("scene_family") or "narrative_stage"),
        "framing": str(result.get("framing") or "medium"),
        "camera_motion": {
            "documentary_establish": "dolly_in",
            "documentary_push_in": "soft_orbit",
            "mechanism_node_field": "truck_left",
            "mechanism_camera_trace": "truck_right",
            "evidence_wall_scan": "truck_left",
            "evidence_closeup": "dolly_in",
            "data_stage_establish": "dolly_in",
            "data_focus_dolly": "dolly_in",
            "data_chart_scan": "truck_right",
            "result_lockup": "dolly_in",
            "split_world_compare": "truck_left",
            "takeaway_orbit": "soft_orbit",
        }.get(_shot_action(result), "dolly_in"),
        "depth_layers": ["background", "spatial_objects", "hud"],
        "avoid_text_perspective": True,
    }
    return result


def partition_operator_shots(
    shots: Iterable[dict[str, Any]],
    *,
    max_shots: int = 3,
    start_sec: float = 0.0,
    duration_sec: float | None = None,
) -> list[dict[str, Any]]:
    """Partition a timeline into short operator-sized jobs.

    Parts are shot-aligned: a part never cuts through a semantic shot.  This
    makes it possible to render, inspect, and repair one spatial sequence at a
    time before running the full paper video.
    """

    max_shots = max(1, int(max_shots))
    window_start = max(0.0, float(start_sec))
    window_end = math.inf if duration_sec is None else window_start + max(0.01, float(duration_sec))
    selected = []
    for raw in shots:
        shot = _operator_shot(dict(raw))
        shot_start = float(shot.get("start_sec") or 0.0)
        shot_end = float(shot.get("end_sec") or shot_start)
        if shot_end <= window_start or shot_start >= window_end:
            continue
        selected.append(shot)

    parts: list[dict[str, Any]] = []
    for index in range(0, len(selected), max_shots):
        group = selected[index : index + max_shots]
        parts.append(
            {
                "part_index": len(parts) + 1,
                "shot_ids": [str(item.get("shot_id") or "") for item in group],
                "start_sec": round(float(group[0].get("start_sec") or 0.0), 3),
                "end_sec": round(float(group[-1].get("end_sec") or 0.0), 3),
                "shots": group,
            }
        )
    return parts


def build_operator_manifest(
    *,
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    out_dir: Path,
    audio_path: str = "",
    start_sec: float = 0.0,
    duration_sec: float | None = None,
    max_shots: int = 3,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
) -> dict[str, Any]:
    """Build a versioned manifest suitable for a Blender MCP operator."""

    parts = partition_operator_shots(
        timeline,
        max_shots=max_shots,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )
    return {
        "version": 1,
        "backend": "blender_operator",
        "operator_protocol": "blender_mcp",
        "source": {
            "title": str(source.get("title") or "").strip(),
            "authors": str(source.get("authors") or "").strip(),
        },
        "canvas": {"width": int(width), "height": int(height), "fps": int(fps)},
        "audio_path": normalize_asset_path(audio_path),
        "slides": slides,
        "subtitles": subtitles,
        "window": {
            "start_sec": round(max(0.0, float(start_sec)), 3),
            "duration_sec": None if duration_sec is None else round(max(0.01, float(duration_sec)), 3),
        },
        "render_contract": {
            "hud_is_flat": True,
            "numbers_must_be_source_grounded": True,
            "no_default_labels": True,
            "no_text_outside_frame": True,
            "motion_limit_degrees": 8,
            "depth_mix": {"spatial_stage": 0.30, "flat_hud": 0.70},
        },
        "parts": parts,
        "output_dir": str(out_dir.resolve()),
    }


def write_operator_manifest(manifest: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_operator_manifest(
    *,
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    out_dir: Path,
    audio_path: str = "",
    start_sec: float = 0.0,
    duration_sec: float | None = None,
    max_shots: int = 3,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
) -> Path:
    manifest = build_operator_manifest(
        source=source,
        slides=slides,
        subtitles=subtitles,
        timeline=timeline,
        out_dir=out_dir,
        audio_path=audio_path,
        start_sec=start_sec,
        duration_sec=duration_sec,
        max_shots=max_shots,
        fps=fps,
        width=width,
        height=height,
    )
    return write_operator_manifest(manifest, out_dir / "blender_operator_manifest.json")

