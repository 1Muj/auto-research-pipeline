from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_research.video_eval_repair import repair_video_artifacts
from auto_research.video_prompt_eval import run_prompt_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair an existing video artifact directory and re-evaluate it.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--eval-report", default="")
    parser.add_argument("--examples", default="examples/ppt_video_calibration_examples.json")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--seconds-per-slide", type=int, default=22)
    parser.add_argument("--target-slides", type=int, default=0, help="0 means auto; positive values force an exact slide count.")
    parser.add_argument("--use-api", action="store_true")
    parser.add_argument("--use-tts", action="store_true")
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir)
    eval_report = Path(args.eval_report) if args.eval_report else artifact_dir / "directorbench_prompt_eval_report.json"
    previous = {}
    if eval_report.is_file():
        previous = json.loads(eval_report.read_text(encoding="utf-8"))
    evaluation = previous.get("evaluation") if isinstance(previous.get("evaluation"), dict) else {}

    repair = repair_video_artifacts(
        artifact_dir,
        evaluation,
        fps=args.fps,
        seconds_per_slide=args.seconds_per_slide,
        use_api=args.use_api,
        use_tts=args.use_tts,
        target_slides=args.target_slides,
    )
    print("Repair summary: " + json.dumps(repair, ensure_ascii=False, separators=(",", ":"))[:2000])

    examples_path = Path(args.examples)
    report = run_prompt_evaluation(
        examples_path if examples_path.is_file() else None,
        artifact_dir,
        out_path=eval_report,
        use_api=args.use_api,
    )
    print(f"Prompt evaluation report: {eval_report}")
    print(
        "Evaluation summary: "
        + json.dumps(report["evaluation"], ensure_ascii=False, separators=(",", ":"))[:2000]
    )


if __name__ == "__main__":
    main()
