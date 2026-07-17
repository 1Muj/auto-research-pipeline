from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from auto_research.cli import app


def test_video_build_cli_writes_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "sample.md"
    source.write_text(
        """
        # Test Paper Video

        This project studies a builder workflow for turning research papers into video artifacts.
        The method creates slides, subtitles, cursor plans, talker inputs, and judge feedback.
        The judge agent reviews coverage, length, and visual synchronization before rendering.
        """.strip(),
        encoding="utf-8",
    )
    out_dir = tmp_path / "video_out"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "video",
            "build",
            "--cwd",
            str(tmp_path),
            "--input",
            str(source),
            "--kind",
            "paper",
            "--out-dir",
            str(out_dir),
            "--fps",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "preview.html").is_file()
    assert (out_dir / "storyboard.json").is_file()
    assert (out_dir / "judge_feedback.json").is_file()
    assert (out_dir / "revision_history.json").is_file()
    assert (out_dir / "iterations" / "round_0" / "judge_feedback.json").is_file()
    assert (out_dir / "iterations" / "round_1" / "judge_feedback.json").is_file()
    assert (out_dir / "flowmesh_spec.json").is_file()
    assert (out_dir / "metrics.json").is_file()
    assert (out_dir / "video.mp4").is_file()
    assert "Video preview:" in result.output
    assert "MP4 video:" in result.output

    history = json.loads((out_dir / "revision_history.json").read_text(encoding="utf-8"))
    assert history[0]["rerun_modules"] == [
        "slide_builder",
        "subtitle_builder",
        "cursor_builder",
        "talker_builder",
    ]
    assert "rerun_modules_next" in history[0]
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "module_scores" in metrics
    assert "failed_modules" in metrics
