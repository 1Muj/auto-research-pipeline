from __future__ import annotations

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from auto_research.cli import app


def _write_tiny_exp(root: Path) -> Path:
    exp_dir = root / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "tiny_review.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            name: tiny_review
            description: review test
            hypothesis: "A tiny run should pass."
            governance_phase: review
            command:
              - python
              - -c
              - |
                import json
                from pathlib import Path
                Path("metrics.json").write_text(
                    json.dumps({"loss": 0.01, "accuracy": 0.99}, indent=2),
                    encoding="utf-8",
                )
            metrics_path: metrics.json
            success_threshold:
              loss: 0.10
              accuracy: 0.90
            """
        ).strip(),
        encoding="utf-8",
    )
    return yaml_path


def test_review_and_visualize_cli(tmp_path: Path) -> None:
    yaml_path = _write_tiny_exp(tmp_path)
    runner = CliRunner()
    run = runner.invoke(app, ["run", "--cwd", str(tmp_path), "-e", str(yaml_path)])
    assert run.exit_code == 0, run.output

    review = runner.invoke(app, ["review", "--cwd", str(tmp_path), "-e", str(yaml_path)])
    assert review.exit_code == 0, review.output
    assert "Review brief:" in review.output
    assert any((tmp_path / "experiments" / "agent_output").glob("review_tiny_review_*.md"))

    dash = runner.invoke(app, ["visualize", "--cwd", str(tmp_path)])
    assert dash.exit_code == 0, dash.output
    html_path = tmp_path / "experiments" / "agent_output" / "vast_demo_dashboard.html"
    assert html_path.is_file()
    assert "Auto Research Vast Demo Dashboard" in html_path.read_text(encoding="utf-8")


def test_compare_systems_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["compare-systems", "--cwd", str(tmp_path)])
    assert result.exit_code == 0, result.output
    out = tmp_path / "docs" / "comparison_auto_research_agents.md"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "Hugging Face ML Intern" in text
    assert "AI Scientist-v2" in text
    assert "Google AI Co-Scientist" in text
    assert "OpenAI PaperBench" in text
