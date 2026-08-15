from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_research.video_prompt_eval import run_prompt_evaluation


def _write_calibration_examples(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "examples": [
                    {
                        "id": "good",
                        "label": "high",
                        "score": 4.5,
                        "summary": "Clear grounded PPT explanation.",
                        "strengths": ["aligned narration", "source-backed claims"],
                        "weaknesses": [],
                        "why": "High because it is clear and grounded.",
                    },
                    {
                        "id": "bad",
                        "label": "low",
                        "score": 1.5,
                        "summary": "Vague PPT explanation with mismatched narration.",
                        "strengths": [],
                        "weaknesses": ["misaligned narration", "unsupported claims"],
                        "why": "Low because content and slides do not match.",
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_artifact_dir(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "source.json").write_text(
        json.dumps({"title": "Demo", "kind": "paper", "text": "A grounded demo."}),
        encoding="utf-8",
    )
    (path / "storyboard.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "index": 1,
                        "title": "Motivation",
                        "bullets": ["Need inspectable PPT videos."],
                        "speaker_note": "This explains why inspection matters.",
                        "visual_asset_preference": "procedural",
                        "visual_asset_paths": [str(path / "selected.png")],
                        "visual_asset_comparison": {
                            "winner": "procedural",
                            "reason": "The rejected image is not used.",
                        },
                    }
                ],
                "subtitles": [
                    {
                        "slide_index": 1,
                        "start_sec": 0,
                        "end_sec": 8,
                        "text": "This explains why inspection matters.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (path / "metrics.json").write_text(
        json.dumps(
            {
                "judge_overall_score": 0.8,
                "slide_count": 1,
                "generated_image_count": 0,
                "paper_figure_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (path / "image_generation.json").write_text(
        json.dumps([{"slide_index": 1, "ok": False, "error": "image rejected: garbled text"}]),
        encoding="utf-8",
    )
    (path / "asset_manifest.json").write_text(
        json.dumps(
            {
                "shot_count": 3,
                "strategy_counts": {"kinetic_text": 3},
                "repairable_shots": ["s01-01"],
            }
        ),
        encoding="utf-8",
    )
    (path / "slides.md").write_text(
        "# Motivation\n- Need inspectable PPT videos.\n",
        encoding="utf-8",
    )
    (path / "subtitles.srt").write_text(
        "1\n00:00:00,000 --> 00:00:08,000\nThis explains why inspection matters.\n",
        encoding="utf-8",
    )


def test_prompt_evaluation_writes_prompt_report(tmp_path: Path) -> None:
    examples = tmp_path / "examples.json"
    artifact_dir = tmp_path / "artifact"
    out = tmp_path / "report.json"
    _write_calibration_examples(examples)
    _write_artifact_dir(artifact_dir)

    report = run_prompt_evaluation(examples, artifact_dir, out_path=out, use_api=False)

    assert out.is_file()
    assert report["learned_rubric"]["learned_from_examples"] == 2
    assert report["learned_rubric"]["score_scale"] == "0-10"
    assert report["evaluation"]["classification"] == "not_run"
    assert "strict multimodal evaluator" in report["judge_prompt"]
    assert "content_script_quality" in report["judge_prompt"]
    assert '"accepted_generated_images": 0' in report["judge_prompt"]
    assert '"rejected_candidate_images": 1' in report["judge_prompt"]
    assert '"unresolved_final_visual_failures": 0' in report["judge_prompt"]
    assert '"selected.png"' in report["judge_prompt"]
    assert '"intentionally_skipped_generated_images": 0' in report["judge_prompt"]
    assert "cannot receive an excellent visual-quality score" in report["judge_prompt"]
    assert "Never cite a rejected_candidate_sample as evidence" in report["judge_prompt"]
    assert "prompt_package" in report
    assert "system_prompt" in report["prompt_package"]
    assert report["prompt_package"]["dataset_mapping"][0]["name"] == "PresentEval"


def test_prompt_eval_cli_runs_without_api(tmp_path: Path) -> None:
    from auto_research.cli import app

    examples = tmp_path / "examples.json"
    artifact_dir = tmp_path / "artifact"
    out = tmp_path / "report.json"
    _write_calibration_examples(examples)
    _write_artifact_dir(artifact_dir)

    result = CliRunner().invoke(
        app,
        [
            "video",
            "prompt-eval",
            "--cwd",
            str(tmp_path),
            "--examples",
            str(examples),
            "--artifact-dir",
            str(artifact_dir),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "Prompt evaluation report:" in result.output


def test_prompt_eval_cli_uses_default_examples_when_omitted(tmp_path: Path) -> None:
    from auto_research.cli import app

    artifact_dir = tmp_path / "artifact"
    out = tmp_path / "report.json"
    _write_artifact_dir(artifact_dir)

    result = CliRunner().invoke(
        app,
        [
            "video",
            "prompt-eval",
            "--cwd",
            str(tmp_path),
            "--artifact-dir",
            str(artifact_dir),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["examples_path"] == "builtin"
    assert report["learned_rubric"]["learned_from_examples"] == 2
    assert report["learned_rubric"]["score_scale"] == "0-10"
