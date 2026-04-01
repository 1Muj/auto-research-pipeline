from __future__ import annotations

import json
from pathlib import Path

import typer

from auto_research import __version__
from auto_research.config import PipelineConfig
from auto_research.pipeline import ResearchPipeline
from auto_research.preflight import preflight_experiment
from auto_research.retro import retro_markdown

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("run")
def run_cmd(
    experiment: Path | None = typer.Option(
        None,
        "--experiment",
        "-e",
        help="Path to experiment YAML (default: run all *.yaml in experiments/)",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
) -> None:
    """Run one experiment file or all experiments under experiments/."""
    pipe = ResearchPipeline(base=cwd)
    if experiment:
        report = pipe.run_one(experiment)
        typer.echo(typer.style(_json(report), fg=typer.colors.GREEN))
    else:
        reports = pipe.run_all()
        typer.echo(_json({"runs": len(reports), "reports": reports}))


@app.command("preflight")
def preflight_cmd(
    experiment: Path = typer.Option(
        ...,
        "--experiment",
        "-e",
        help="Experiment YAML to validate before run",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
) -> None:
    """Validate experiment YAML and metrics contract (governance gate)."""
    errs, warns = preflight_experiment(experiment, cwd)
    for w in warns:
        typer.echo(typer.style(w, fg=typer.colors.YELLOW))
    for e in errs:
        typer.echo(typer.style(e, fg=typer.colors.RED))
    if errs:
        raise typer.Exit(code=1)
    typer.echo(typer.style("preflight: ok", fg=typer.colors.GREEN))


@app.command("retro")
def retro_cmd(
    last: int = typer.Option(10, "--last", "-n", help="Number of recent feedback files"),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
) -> None:
    """Print a markdown retro from recent experiments/feedback/*.json."""
    cfg = PipelineConfig().resolved(cwd)
    typer.echo(retro_markdown(cfg, last))


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    typer.echo(__version__)


def _json(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
