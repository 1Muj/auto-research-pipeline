#!/usr/bin/env python3
"""Export a checkpointed paper-video timeline as Blender operator-sized jobs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from auto_research.blender_operator import export_operator_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--max-shots", type=int, default=3)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    timeline_path = run_dir / "scene_timeline.json"
    source_path = run_dir / "source.json"
    storyboard_path = run_dir / "storyboard.json"
    if not timeline_path.is_file() or not source_path.is_file() or not storyboard_path.is_file():
        parser.error("run_dir must contain scene_timeline.json, source.json, and storyboard.json")

    timeline_doc = json.loads(timeline_path.read_text(encoding="utf-8"))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    out_dir = (args.out_dir or run_dir / "blender_operator").resolve()
    audio_path = str(next((p for p in (run_dir / "audio.wav", run_dir / "audio.mp3") if p.is_file()), ""))
    manifest_path = export_operator_manifest(
        source=source,
        slides=storyboard.get("slides") or [],
        subtitles=storyboard.get("subtitles") or [],
        timeline=timeline_doc.get("shots") or [],
        out_dir=out_dir,
        audio_path=audio_path,
        start_sec=max(0.0, args.start),
        duration_sec=args.duration,
        max_shots=max(1, args.max_shots),
        fps=max(1, args.fps),
        width=max(320, args.width),
        height=max(180, args.height),
    )
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(json.dumps({
        "manifest": str(manifest_path),
        "parts": len(document["parts"]),
        "shots": sum(len(part["shots"]) for part in document["parts"]),
        "window": document["window"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

