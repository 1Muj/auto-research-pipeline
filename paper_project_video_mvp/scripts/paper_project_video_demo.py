from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

def main() -> int:
    from auto_research.video.pipeline import run_video_pipeline

    parser = argparse.ArgumentParser(description="Run paper/project-to-video MVP demo.")
    parser.add_argument("--input", required=True, help="Paper file or project directory")
    parser.add_argument("--kind", choices=["paper", "project"], required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-slides", type=int, default=5)
    parser.add_argument("--seconds-per-slide", type=int, default=12)
    parser.add_argument("--target-score", type=float, default=0.9)
    parser.add_argument("--max-revisions", type=int, default=3)
    parser.add_argument("--min-revisions", type=int, default=1)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--use-api", action="store_true")
    parser.add_argument("--use-vlm-cursor", action="store_true")
    args = parser.parse_args()

    result = run_video_pipeline(
        ROOT / args.input if not Path(args.input).is_absolute() else Path(args.input),
        kind=args.kind,
        out_dir=ROOT / args.out_dir if not Path(args.out_dir).is_absolute() else Path(args.out_dir),
        max_slides=args.max_slides,
        seconds_per_slide=args.seconds_per_slide,
        use_api=args.use_api,
        target_score=args.target_score,
        max_revisions=args.max_revisions,
        min_revisions=args.min_revisions,
        fps=args.fps,
        use_vlm_cursor=args.use_vlm_cursor,
    )
    print(f"preview={result.preview_path}")
    print(f"metrics={result.metrics_path}")
    print(f"judge={result.judge_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
