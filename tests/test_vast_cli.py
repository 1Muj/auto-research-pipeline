"""Vast.ai Typer subcommand wiring."""

from __future__ import annotations

from typer.testing import CliRunner

from auto_research.cli import app


def test_vast_group_help() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["vast", "--help"])
    assert r.exit_code == 0, r.output
    assert "deploy" in r.output


def test_vast_deploy_help() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["vast", "deploy", "--help"])
    assert r.exit_code == 0, r.output
    assert "deploy_vast_5080" in r.output or "Vast" in r.output


def test_vast_push_help() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["vast", "push", "--help"])
    assert r.exit_code == 0, r.output
    assert "existing Vast" in r.output or "SSH" in r.output
