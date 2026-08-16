#!/usr/bin/env python3
"""Render a short hybrid-3D preview from an existing pipeline checkpoint.

This path is intentionally offline: it reuses source/storyboard/image artifacts and
does not call text, vision, image, or TTS providers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_research.video_pipeline import render_mp4_video  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path, help="Existing pipeline output directory")
    parser.add_argument("--start", type=float, default=0.0, help="Timeline start in seconds")
    parser.add_argument("--duration", type=float, default=18.0, help="Preview length in seconds")
    parser.add_argument("--fps", type=int, default=6, help="Low preview frame rate")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--mode",
        choices=("clear_2d", "hybrid_3d"),
        default="clear_2d",
        help="Use clear 2D scene rendering by default; opt into the experimental 3D path explicitly.",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    source_path = run_dir / "source.json"
    storyboard_path = run_dir / "storyboard.json"
    if not source_path.is_file() or not storyboard_path.is_file():
        parser.error(f"missing source.json or storyboard.json in {run_dir}")

    source = json.loads(source_path.read_text(encoding="utf-8"))
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    slides = storyboard.get("slides") or []
    subtitles = storyboard.get("subtitles") or []
    cursor_plan = storyboard.get("cursor_plan") or []
    if not slides or not subtitles:
        parser.error("storyboard has no slides or subtitles")

    output_dir_name = "hybrid_3d_preview" if args.mode == "hybrid_3d" else "clear_2d_preview"
    output = args.out or run_dir / output_dir_name / "preview.mp4"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    os.environ["AUTO_VIDEO_RENDER_STYLE"] = "scene"
    os.environ["AUTO_VIDEO_HYBRID_3D"] = "1" if args.mode == "hybrid_3d" else "0"
    os.environ["AUTO_VIDEO_EXPERIMENTAL_3D"] = "1" if args.mode == "hybrid_3d" else "0"
    os.environ.setdefault("AUTO_VIDEO_HYBRID_3D_RATIO", "0.30")
    os.environ["AUTO_VIDEO_PREVIEW_START_SEC"] = str(max(0.0, args.start))
    os.environ["AUTO_VIDEO_PREVIEW_DURATION_SEC"] = str(max(0.25, args.duration))
    os.environ.setdefault("AUTO_VIDEO_FFMPEG_PRESET", "ultrafast")

    ok = render_mp4_video(
        source,
        slides,
        subtitles,
        cursor_plan,
        output,
        width=max(320, args.width),
        height=max(180, args.height),
        fps=max(1, args.fps),
    )
    if not ok:
        print(f"preview render failed: {output}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
