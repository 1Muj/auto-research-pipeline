"""CLI + agent_loop: agent command and preflight failure path."""

from __future__ import annotations

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from auto_research.agent_loop import (
    apply_llm_yaml_to_experiment,
    extract_first_yaml_fence,
    run_agent_turn,
)
from auto_research.cli import app


def test_agent_cmd_passes_thresholds(tmp_path: Path) -> None:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "tiny_agent.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            name: tiny_agent
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
    result = runner.invoke(app, ["agent", "--cwd", str(tmp_path), "-e", str(yaml_path)])
    assert result.exit_code == 0, result.output
    assert "Agent brief:" in result.output
    assert "Experiment YAML backup (before run):" in result.output
    assert "Thresholds passed." in result.output
    out = exp_dir / "agent_output"
    assert out.is_dir()
    assert any(out.glob("agent_round1_*.md"))
    backups = out / "yaml_backups"
    assert backups.is_dir()
    assert any(backups.glob("*_before_agent_run_*.yaml"))


def test_agent_cmd_preflight_exit_2(tmp_path: Path) -> None:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "bad_metrics.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            name: bad_metrics
            command: [python, -c, "print(1)"]
            metrics_path: /tmp/abs_metrics.json
            """
        ).strip(),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["agent", "--cwd", str(tmp_path), "-e", str(yaml_path)])
    assert result.exit_code == 2, result.output
    assert "metrics_path must be relative" in result.output


def test_extract_first_yaml_fence() -> None:
    body = extract_first_yaml_fence("x\n```yaml\nname: a\n```\n")
    assert body == "name: a"
    assert extract_first_yaml_fence("no fence") is None


def test_apply_llm_yaml_to_experiment_writes_and_backups(tmp_path: Path) -> None:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "patch_me.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            name: patch_me
            command: [python, -c, "print(0)"]
            metrics_path: metrics.json
            """
        ).strip(),
        encoding="utf-8",
    )
    llm_md = textwrap.dedent(
        """
        Proposed fix:

        ```yaml
        name: patch_me
        command: [python, -c, "print(1)"]
        metrics_path: metrics.json
        ```
        """
    ).strip()
    backup_root = exp_dir / "agent_output" / "yaml_backups"
    ok, msg, backup = apply_llm_yaml_to_experiment(
        llm_md, yaml_path, tmp_path, backup_root
    )
    assert ok, msg
    assert backup is not None and backup.is_file()
    new_text = yaml_path.read_text(encoding="utf-8")
    assert "print(1)" in new_text
    assert "print(0)" not in new_text


def test_agent_apply_suggested_yaml_requires_llm(tmp_path: Path) -> None:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "tiny.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """
            name: tiny
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
        ["agent", "--cwd", str(tmp_path), "-e", str(yaml_path), "--apply-suggested-yaml"],
    )
    assert result.exit_code == 2, result.output
    assert "requires --llm" in result.output


def test_run_agent_turn_returns_preflight_errors(tmp_path: Path) -> None:
    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True)
    yaml_path = exp_dir / "missing.yaml"
    code, report, errs = run_agent_turn(
        yaml_path,
        tmp_path,
        use_llm=False,
        out_dir=None,
    )
    assert code == 2
    assert report is None
    assert errs and "not found" in errs[0].lower()
