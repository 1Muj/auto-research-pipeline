from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from auto_research.cli import app


def test_control_autotune_script_outputs_metrics_and_dashboard(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    dashboard_path = tmp_path / "control.html"
    proc = subprocess.run(
        [
            "python",
            "scripts/demos/control_autotune_demo.py",
            "--iterations",
            "12",
            "--metrics-path",
            str(metrics_path),
            "--dashboard-path",
            str(dashboard_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["iterations"] == 12
    assert metrics["stability_score"] >= 0.95
    assert metrics["best_tracking_error"] < 0.3
    assert dashboard_path.is_file()
    assert "AutoTune-Control" in dashboard_path.read_text(encoding="utf-8")


def test_control_autotune_experiment_cli() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "preflight",
            "-e",
            "experiments/_demo_control_autotune.yaml",
        ],
    )
    assert result.exit_code == 0, result.output
