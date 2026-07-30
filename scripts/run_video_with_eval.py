from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from auto_research.video_eval_repair import repair_video_artifacts
from auto_research.video_pipeline import run_video_pipeline
from auto_research.video_prompt_eval import run_prompt_evaluation


def _score_value(evaluation: dict) -> float:
    try:
        return float(evaluation.get("overall_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _needs_repair(evaluation: dict, *, threshold: float) -> bool:
    classification = str(evaluation.get("classification") or "").lower()
    return _score_value(evaluation) < threshold or classification in {"weak", "poor"}


def _is_valid_evaluation(report: dict) -> bool:
    evaluation = report.get("evaluation") if isinstance(report.get("evaluation"), dict) else {}
    classification = str(evaluation.get("classification") or "").lower()
    return evaluation.get("overall_score") is not None and classification != "model_parse_failed"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paper/project-to-video and prompt evaluation.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--kind", default="paper")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-slides", type=int, default=10)
    parser.add_argument("--seconds-per-slide", type=int, default=22)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--target-score", type=float, default=0.88)
    parser.add_argument("--min-revisions", type=int, default=1)
    parser.add_argument("--max-revisions", type=int, default=3)
    parser.add_argument("--use-api", action="store_true")
    parser.add_argument("--use-image-api", action="store_true")
    parser.add_argument("--use-tts", action="store_true")
    parser.add_argument("--use-omni-cursor", action="store_true")
    parser.add_argument("--eval-report", required=True)
    parser.add_argument("--examples", default="examples/ppt_video_calibration_examples.json")
    parser.add_argument("--eval-repair-rounds", type=int, default=int(os.environ.get("AUTO_VIDEO_EVAL_REPAIR_ROUNDS", "1")))
    parser.add_argument("--eval-repair-threshold", type=float, default=float(os.environ.get("AUTO_VIDEO_EVAL_REPAIR_THRESHOLD", "7.0")))
    args = parser.parse_args()

    result = run_video_pipeline(
        Path(args.input),
        kind=args.kind,
        out_dir=Path(args.out_dir),
        max_slides=args.max_slides,
        seconds_per_slide=args.seconds_per_slide,
        use_api=args.use_api,
        target_score=args.target_score,
        max_revisions=args.max_revisions,
        min_revisions=args.min_revisions,
        fps=args.fps,
        use_omni_cursor=args.use_omni_cursor,
        use_image_api=args.use_image_api,
        use_tts=args.use_tts,
    )
    print(f"Video preview: {result.preview_path}")
    print(f"MP4 video: {result.video_path}")
    print(f"Metrics: {result.metrics_path}")
    print(f"Judge feedback: {result.judge_path}")

    examples_path = Path(args.examples)
    report = run_prompt_evaluation(
        examples_path if examples_path.is_file() else None,
        Path(args.out_dir),
        out_path=Path(args.eval_report),
        use_api=args.use_api,
    )
    eval_report_path = Path(args.eval_report)
    initial_report_path = eval_report_path.with_name(eval_report_path.stem + "_round_0.json")
    initial_report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for repair_round in range(1, max(0, args.eval_repair_rounds) + 1):
        evaluation = report.get("evaluation") if isinstance(report.get("evaluation"), dict) else {}
        if not _needs_repair(evaluation, threshold=args.eval_repair_threshold):
            break
        print(
            "Evaluation repair round "
            f"{repair_round}: score={_score_value(evaluation):.2f} "
            f"classification={evaluation.get('classification')} "
            f"threshold={args.eval_repair_threshold:.2f}"
        )
        os.environ.setdefault("AUTO_VIDEO_REPAIR_MAX_SLIDES", str(args.max_slides))
        repair = repair_video_artifacts(
            Path(args.out_dir),
            evaluation,
            fps=args.fps,
            seconds_per_slide=args.seconds_per_slide,
            use_api=args.use_api,
            use_tts=args.use_tts,
            target_slides=0,
        )
        print("Repair summary: " + json.dumps(repair, ensure_ascii=False, separators=(",", ":"))[:2000])
        round_report_path = eval_report_path.with_name(f"{eval_report_path.stem}_round_{repair_round}.json")
        next_report = run_prompt_evaluation(
            examples_path if examples_path.is_file() else None,
            Path(args.out_dir),
            out_path=round_report_path,
            use_api=args.use_api,
        )
        if _is_valid_evaluation(next_report):
            report = next_report
            eval_report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            print(
                "Evaluation retry failed; keeping the last valid report as final. "
                f"Failed report saved to: {round_report_path}"
            )
            break

    print(f"Prompt evaluation report: {args.eval_report}")
    print(
        "Evaluation summary: "
        + json.dumps(report["evaluation"], ensure_ascii=False, separators=(",", ":"))[:2000]
    )


if __name__ == "__main__":
    main()
