"""Integration: cycle runs preflight + run + retro without error on a minimal experiment."""

from __future__ import annotations

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from auto_research.cli import app


def test_cycle_minimal_experiment(tmp_path: Path) -> None:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "tiny.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            name: tiny_cycle
            command:
              - python
              - -c
              - |
                import json
                from pathlib import Path
                Path("metrics.json").write_text(
                    json.dumps({"loss": 0.01}, indent=2),
                    encoding="utf-8",
                )
            metrics_path: metrics.json
            success_threshold:
              loss: 0.10
            """
        ).strip(),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["cycle", "--cwd", str(tmp_path), "-e", str(yaml_path), "--last", "3"],
    )
    assert result.exit_code == 0, result.output
    assert "preflight: ok" in result.output
    assert "tiny_cycle" in result.output
    assert "--- retro ---" in result.output
    assert "Experiment retro" in result.output
