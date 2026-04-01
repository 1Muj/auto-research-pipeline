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


def _preflight_or_exit(experiment: Path, cwd: Path | None) -> None:
    errs, warns = preflight_experiment(experiment, cwd)
    for w in warns:
        typer.echo(typer.style(w, fg=typer.colors.YELLOW))
    for e in errs:
        typer.echo(typer.style(e, fg=typer.colors.RED))
    if errs:
        raise typer.Exit(code=1)
    typer.echo(typer.style("preflight: ok", fg=typer.colors.GREEN))


def _cycle_experiment_files(cfg: PipelineConfig) -> list[Path]:
    """Same selection as run_all: experiments/*.yaml, skip _*.yaml."""
    d = cfg.experiments_dir
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.yaml") if not p.name.startswith("_"))


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
    _preflight_or_exit(experiment, cwd)


@app.command("cycle")
def cycle_cmd(
    experiment: Path | None = typer.Option(
        None,
        "--experiment",
        "-e",
        help="One YAML; omit to run all experiments/*.yaml (excluding _*.yaml), in sorted order",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    last: int = typer.Option(10, "--last", "-n", help="Retro: recent feedback files to include"),
) -> None:
    """Preflight → run for one or all experiment YAMLs, then print retro once at the end."""
    cfg = PipelineConfig().resolved(cwd)
    if experiment is not None:
        paths = [experiment]
    else:
        paths = _cycle_experiment_files(cfg)
        if not paths:
            typer.echo(
                typer.style(
                    f"No experiments to cycle under {cfg.experiments_dir} "
                    "(need *.yaml, excluding _*.yaml).",
                    fg=typer.colors.RED,
                )
            )
            raise typer.Exit(code=1)

    pipe = ResearchPipeline(base=cwd)
    for i, path in enumerate(paths):
        if len(paths) > 1:
            msg = f"=== cycle {i + 1}/{len(paths)}: {path} ==="
            typer.echo(typer.style(msg, fg=typer.colors.BLUE))
        _preflight_or_exit(path, cwd)
        report = pipe.run_one(path)
        typer.echo(typer.style(_json(report), fg=typer.colors.GREEN))
        typer.echo("")

    typer.echo(typer.style("--- retro ---", fg=typer.colors.CYAN))
    typer.echo(retro_markdown(cfg, last))


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
