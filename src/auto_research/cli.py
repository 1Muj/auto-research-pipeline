from __future__ import annotations

import json
from pathlib import Path

import typer

from auto_research import __version__
from auto_research.pipeline import ResearchPipeline

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
