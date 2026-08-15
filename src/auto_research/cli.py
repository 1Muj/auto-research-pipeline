from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import typer

from auto_research import __version__
from auto_research.config import PipelineConfig
from auto_research.video_prompt_eval import run_prompt_evaluation

app = typer.Typer(no_args_is_help=True, add_completion=False)

vast_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Vast.ai GPU rental helpers (wraps scripts/deploy_vast_5080.sh).",
)

video_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Paper/project-to-video MVP helpers.",
)


@vast_app.command("deploy")
def vast_deploy_cmd(
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
) -> None:
    """Create a Vast.ai GPU instance via scripts/deploy_vast_5080.sh."""
    root = PipelineConfig().resolved(cwd).root
    script = root / "scripts" / "deploy_vast_5080.sh"
    if not script.is_file():
        typer.echo(typer.style(f"Missing {script}", fg=typer.colors.RED))
        raise typer.Exit(code=1)
    typer.echo(typer.style(f"Running {script}", fg=typer.colors.CYAN))
    proc = subprocess.run(["bash", str(script)], cwd=str(root), check=False)
    raise typer.Exit(code=proc.returncode)


@vast_app.command("push")
def vast_push_cmd(
    ssh_cmd: str | None = typer.Option(
        None,
        "--ssh",
        "--ssh-cmd",
        help='Full SSH command from Vast, e.g. "ssh -p 12345 root@23.158.136.85"',
    ),
    target: str | None = typer.Option(None, "--target", help="SSH target, e.g. root@HOST"),
    port: str | None = typer.Option(None, "--port", help="SSH port if using --target"),
    remote_dir: str = typer.Option(
        "/root/auto-research",
        "--remote-dir",
        help="Remote project directory",
    ),
    experiment: Path = typer.Option(
        Path("experiments/_demo_mnist_cnn.yaml"),
        "--experiment",
        "-e",
        help="Experiment YAML to run after upload",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    no_run: bool = typer.Option(False, "--no-run", help="Upload and install only"),
    skip_install: bool = typer.Option(False, "--skip-install", help="Upload only"),
    no_pull_results: bool = typer.Option(
        False,
        "--no-pull-results",
        help="Do not pull remote run/feedback artifacts back",
    ),
) -> None:
    """Upload local code to an existing Vast instance over SSH and optionally run an experiment."""
    root = PipelineConfig().resolved(cwd).root
    script = root / "scripts" / "deploy_existing_vast.sh"
    if not script.is_file():
        typer.echo(typer.style(f"Missing {script}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    args = ["bash", str(script), "--remote-dir", remote_dir, "-e", str(experiment)]
    if ssh_cmd:
        args.extend(["--ssh", ssh_cmd])
    if target:
        args.extend(["--target", target])
    if port:
        args.extend(["--port", port])
    if no_run:
        args.append("--no-run")
    if skip_install:
        args.append("--skip-install")
    if no_pull_results:
        args.append("--no-pull-results")

    typer.echo(typer.style(f"Running {script}", fg=typer.colors.CYAN))
    proc = subprocess.run(args, cwd=str(root), check=False)
    raise typer.Exit(code=proc.returncode)


app.add_typer(vast_app, name="vast")


@video_app.command("build")
def video_build_cmd(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="Paper .md/.txt/.pdf file or local project directory",
    ),
    kind: str = typer.Option(
        "paper",
        "--kind",
        help="Input kind: paper or project",
    ),
    out_dir: Path = typer.Option(
        Path("experiments/video_output/manual"),
        "--out-dir",
        "-o",
        help="Output artifact directory",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    max_slides: int = typer.Option(5, "--max-slides", help="Max slides/scenes"),
    seconds_per_slide: int = typer.Option(12, "--seconds-per-slide", help="Rough pacing"),
    target_score: float = typer.Option(0.9, "--target-score", help="Judge score needed to stop"),
    max_revisions: int = typer.Option(3, "--max-revisions", help="Maximum revise rounds"),
    min_revisions: int = typer.Option(
        1,
        "--min-revisions",
        help="Minimum revise rounds before accepting judge satisfaction",
    ),
    fps: int = typer.Option(12, "--fps", help="MP4 frame rate; higher is smoother but slower"),
    use_api: bool = typer.Option(
        False,
        "--use-api",
        help=(
            "Use DeepSeek/OpenAI-compatible API if DEEPSEEK_API_KEY or "
            "OPENAI_API_KEY is set; otherwise heuristic fallback"
        ),
    ),
    use_vlm_cursor: bool = typer.Option(
        False,
        "--use-vlm-cursor",
        help="Use a vision model to ground cursor points when OPENAI_VISION_* is configured",
    ),
    use_omni_cursor: bool = typer.Option(
        False,
        "--use-omni-cursor",
        help="Use Lumid qwen-omni for cursor/highlight grounding when LUM_API_KEY is configured",
    ),
    use_image_api: bool = typer.Option(
        False,
        "--use-image-api",
        help="Use OpenAI GPT Image to generate visual assets",
    ),
    use_tts: bool = typer.Option(
        False,
        "--use-tts",
        help="Use Lumid qwen-tts to synthesize narration audio and mux it into the MP4",
    ),
) -> None:
    """Build slides, subtitles, cursor plan, judge feedback, FlowMesh spec, and HTML preview."""
    from auto_research.video.pipeline import run_video_pipeline

    root = PipelineConfig().resolved(cwd).root
    inp = input_path if input_path.is_absolute() else root / input_path
    out = out_dir if out_dir.is_absolute() else root / out_dir
    result = run_video_pipeline(
        inp,
        kind=kind,
        out_dir=out,
        max_slides=max_slides,
        seconds_per_slide=seconds_per_slide,
        use_api=use_api,
        target_score=target_score,
        max_revisions=max_revisions,
        min_revisions=min_revisions,
        fps=fps,
        use_vlm_cursor=use_vlm_cursor,
        use_omni_cursor=use_omni_cursor,
        use_image_api=use_image_api,
        use_tts=use_tts,
    )
    typer.echo(typer.style(f"Video preview: {result.preview_path}", fg=typer.colors.CYAN))
    typer.echo(typer.style(f"MP4 video: {result.video_path}", fg=typer.colors.CYAN))
    typer.echo(typer.style(f"Metrics: {result.metrics_path}", fg=typer.colors.GREEN))
    typer.echo(typer.style(f"Judge feedback: {result.judge_path}", fg=typer.colors.BLUE))


@video_app.command("demo")
def video_demo_cmd(
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    use_api: bool = typer.Option(
        False,
        "--use-api",
        help="Use DeepSeek/OpenAI-compatible API if configured",
    ),
    target_score: float = typer.Option(0.9, "--target-score", help="Judge score needed to stop"),
    max_revisions: int = typer.Option(3, "--max-revisions", help="Maximum revise rounds"),
    min_revisions: int = typer.Option(1, "--min-revisions", help="Minimum revise rounds"),
    fps: int = typer.Option(12, "--fps", help="MP4 frame rate; higher is smoother but slower"),
    use_vlm_cursor: bool = typer.Option(
        False,
        "--use-vlm-cursor",
        help="Use a vision model to ground cursor points when OPENAI_VISION_* is configured",
    ),
    use_omni_cursor: bool = typer.Option(
        False,
        "--use-omni-cursor",
        help="Use Lumid qwen-omni for cursor/highlight grounding when LUM_API_KEY is configured",
    ),
    use_image_api: bool = typer.Option(
        False,
        "--use-image-api",
        help="Use OpenAI GPT Image to generate visual assets",
    ),
    use_tts: bool = typer.Option(
        False,
        "--use-tts",
        help="Use Lumid qwen-tts to synthesize narration audio and mux it into the MP4",
    ),
) -> None:
    """Run both built-in paper and project video demos."""
    from auto_research.video.pipeline import run_video_pipeline

    root = PipelineConfig().resolved(cwd).root
    demos = [
        (
            root / "examples" / "paper_to_video" / "sample_paper.md",
            "paper",
            root / "experiments" / "video_output" / "paper_demo",
        ),
        (
            root / "examples" / "project_to_video",
            "project",
            root / "experiments" / "video_output" / "project_demo",
        ),
    ]
    for inp, kind, out in demos:
        result = run_video_pipeline(
            inp,
            kind=kind,
            out_dir=out,
            use_api=use_api,
            target_score=target_score,
            max_revisions=max_revisions,
            min_revisions=min_revisions,
            fps=fps,
            use_vlm_cursor=use_vlm_cursor,
            use_omni_cursor=use_omni_cursor,
            use_image_api=use_image_api,
            use_tts=use_tts,
        )
        typer.echo(typer.style(f"{kind} preview: {result.preview_path}", fg=typer.colors.CYAN))
        typer.echo(typer.style(f"{kind} mp4: {result.video_path}", fg=typer.colors.CYAN))


@video_app.command("prompt-eval")
def video_prompt_eval_cmd(
    examples: Path | None = typer.Option(
        None,
        "--examples",
        "-e",
        help=(
            "JSON file with your high/low/score calibration examples; "
            "default uses built-in anchors"
        ),
    ),
    artifact_dir: Path = typer.Option(
        ...,
        "--artifact-dir",
        "-a",
        help="Video artifact directory containing storyboard.json, slides.md, metrics.json, etc.",
    ),
    out: Path = typer.Option(
        Path("experiments/video_output/prompt_eval_report.json"),
        "--out",
        "-o",
        help="Where to write the learned rubric, judge prompt, and evaluation report",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    transcript: Path | None = typer.Option(
        None,
        "--transcript",
        help="Optional transcript text from the real PPT/video audio",
    ),
    standard: str = typer.Option(
        "",
        "--standard",
        help="Extra user scoring standard to merge into the learned rubric",
    ),
    use_api: bool = typer.Option(
        False,
        "--use-api",
        help="Use OPENAI-compatible API to learn the rubric and score the artifact",
    ),
) -> None:
    """Learn a user-specific judge prompt from labeled examples, then evaluate an artifact."""
    root = PipelineConfig().resolved(cwd).root
    examples_path = None
    if examples:
        examples_path = examples if examples.is_absolute() else root / examples
    else:
        default_examples = root / "examples" / "ppt_video_calibration_examples.json"
        if default_examples.is_file():
            examples_path = default_examples
    artifact_path = artifact_dir if artifact_dir.is_absolute() else root / artifact_dir
    out_path = out if out.is_absolute() else root / out
    transcript_path = None
    if transcript:
        transcript_path = transcript if transcript.is_absolute() else root / transcript
    report = run_prompt_evaluation(
        examples_path,
        artifact_path,
        out_path=out_path,
        use_api=use_api,
        transcript_path=transcript_path,
        extra_standard=standard,
    )
    evaluation = report["evaluation"]
    typer.echo(typer.style(f"Prompt evaluation report: {out_path}", fg=typer.colors.CYAN))
    typer.echo(
        typer.style(
            f"Classification: {evaluation.get('classification')} | "
            f"Score: {evaluation.get('overall_score')} | "
            f"Confidence: {evaluation.get('confidence')}",
            fg=typer.colors.GREEN,
        )
    )


app.add_typer(video_app, name="video")


@app.command("run")
def run_cmd(
    experiment: Path | None = typer.Option(
        None,
        "--experiment",
        "-e",
        help="Path to experiment YAML (default: run all *.yaml in experiments/)",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Pretty-print JSON (ignored if --brief)",
    ),
    brief: bool = typer.Option(
        False,
        "--brief",
        "-b",
        help="Short multi-line summary (best for narrow terminals / demos)",
    ),
) -> None:
    """Run one experiment file or all experiments under experiments/."""
    from auto_research.pipeline import ResearchPipeline

    pipe = ResearchPipeline(base=cwd)
    root = pipe.cfg.root
    if experiment:
        report = pipe.run_one(experiment)
        _echo_report(report, root, pretty=pretty, brief=brief)
    else:
        reports = pipe.run_all()
        if brief:
            for report in reports:
                _echo_report(report, root, pretty=False, brief=True)
                typer.echo("")
        else:
            typer.echo(_json({"runs": len(reports), "reports": reports}, pretty=pretty))


def _preflight_or_exit(experiment: Path, cwd: Path | None) -> None:
    from auto_research.preflight import preflight_experiment

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
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Pretty-print each run JSON (ignored if --brief)",
    ),
    brief: bool = typer.Option(
        False,
        "--brief",
        "-b",
        help="Short multi-line summary per run (best for narrow terminals / demos)",
    ),
) -> None:
    """Preflight → run for one or all experiment YAMLs, then print retro once at the end."""
    from auto_research.pipeline import ResearchPipeline
    from auto_research.retro import retro_markdown

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
        _echo_report(report, cfg.root, pretty=pretty, brief=brief)
        typer.echo("")

    typer.echo(typer.style("--- retro ---", fg=typer.colors.CYAN))
    typer.echo(retro_markdown(cfg, last))


@app.command("agent")
def agent_cmd(
    experiment: Path = typer.Option(
        ...,
        "--experiment",
        "-e",
        help="Experiment YAML to run (preflight → run → agent markdown brief)",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    llm: bool = typer.Option(
        False,
        "--llm",
        help=(
            "Optional: embed LLM suggestions in the brief (ANTHROPIC_API_KEY + "
            "pip install -e '.[anthropic]', or OPENAI_API_KEY for OpenAI-compatible API). "
            "Otherwise open the .md in Claude Code."
        ),
    ),
    out_dir: Path | None = typer.Option(
        None,
        "--out-dir",
        help="Directory for agent markdown (default: experiments/agent_output/)",
    ),
    apply_suggested_yaml: bool = typer.Option(
        False,
        "--apply-suggested-yaml",
        help=(
            "With --llm: take the first ```yaml from the model, validate+preflight, "
            "and overwrite -e (backup under <out-dir>/yaml_backups/)."
        ),
    ),
) -> None:
    """Run one experiment, read feedback, write a markdown brief for Claude Code / human."""
    from auto_research.agent_loop import run_agent_turn

    code, report, perr = run_agent_turn(
        experiment,
        cwd,
        use_llm=llm,
        out_dir=out_dir,
        apply_suggested_yaml=apply_suggested_yaml,
    )
    for e in perr:
        typer.echo(typer.style(e, fg=typer.colors.RED))
    if code == 2:
        raise typer.Exit(code=2)
    if report:
        am = report.get("agent_markdown")
        if am:
            typer.echo(typer.style(f"Agent brief: {am}", fg=typer.colors.CYAN))
        bu = report.get("experiment_yaml_backup")
        if bu:
            typer.echo(
                typer.style(
                    f"Experiment YAML backup (before run): {bu}",
                    fg=typer.colors.BLUE,
                )
            )
        yp = report.get("yaml_patch")
        if yp and yp.get("applied"):
            typer.echo(typer.style(yp.get("message", "YAML updated."), fg=typer.colors.GREEN))
    if code == 3:
        typer.echo(
            typer.style(
                "YAML patch was not applied — see agent brief.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=3)
    if code == 0:
        typer.echo(typer.style("Thresholds passed.", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("Thresholds not met — see agent brief.", fg=typer.colors.YELLOW))
        raise typer.Exit(code=1)


@app.command("retro")
def retro_cmd(
    last: int = typer.Option(10, "--last", "-n", help="Number of recent feedback files"),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
) -> None:
    """Print a markdown retro from recent experiments/feedback/*.json."""
    from auto_research.retro import retro_markdown

    cfg = PipelineConfig().resolved(cwd)
    typer.echo(retro_markdown(cfg, last))


@app.command("review")
def review_cmd(
    experiment: Path = typer.Option(
        ...,
        "--experiment",
        "-e",
        help="Experiment YAML to review using the latest matching feedback",
    ),
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    out_dir: Path | None = typer.Option(
        None,
        "--out-dir",
        help="Output directory (default: experiments/agent_output)",
    ),
) -> None:
    """Write a lightweight reviewer/critic brief from metrics and feedback."""
    from auto_research.reviewer import write_review

    cfg = PipelineConfig().resolved(cwd)
    out = write_review(experiment, cfg, out_dir=out_dir)
    typer.echo(typer.style(f"Review brief: {out}", fg=typer.colors.CYAN))


@app.command("visualize")
def visualize_cmd(
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Output HTML path (default: experiments/agent_output/vast_demo_dashboard.html)",
    ),
    limit: int = typer.Option(20, "--limit", help="Most recent feedback files to include"),
) -> None:
    """Generate a standalone HTML dashboard from run/feedback artifacts."""
    from auto_research.reviewer import write_visualization

    cfg = PipelineConfig().resolved(cwd)
    written = write_visualization(cfg, out=out, limit=limit)
    typer.echo(typer.style(f"Dashboard: {written}", fg=typer.colors.CYAN))


@app.command("compare-systems")
def compare_systems_cmd(
    cwd: Path | None = typer.Option(None, "--cwd", help="Project root"),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Output markdown path (default: docs/comparison_auto_research_agents.md)",
    ),
) -> None:
    """Write a markdown comparison with AI Scientist, Co-Scientist, PaperBench, and ML Intern."""
    from auto_research.reviewer import write_comparison

    cfg = PipelineConfig().resolved(cwd)
    written = write_comparison(cfg, out=out)
    typer.echo(typer.style(f"Comparison: {written}", fg=typer.colors.CYAN))


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    typer.echo(__version__)


def _json(obj: object, *, pretty: bool = False) -> str:
    """JSON for terminal: compact default; pass pretty=True for indent=2."""
    if pretty:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _short_path(path_str: str, root: Path) -> str:
    try:
        return str(Path(path_str).resolve().relative_to(root.resolve()))
    except ValueError:
        return path_str


def _report_brief(report: dict[str, Any], root: Path) -> str:
    summary = report.get("summary") or {}
    exp = summary.get("experiment", "?")
    rid = summary.get("run_id", "?")
    st = summary.get("status", "?")
    lines = [
        f"experiment={exp}  run_id={rid}  status={st}",
    ]
    fb = report.get("feedback_path")
    if fb:
        lines.append(f"feedback: {_short_path(str(fb), root)}")
    mp = summary.get("metrics_path")
    if mp:
        lines.append(f"metrics: {_short_path(str(mp), root)}")
    metrics = report.get("metrics") or {}
    parts: list[str] = []
    for k, v in metrics.items():
        if k in ("duration_sec", "exit_code"):
            continue
        if isinstance(v, (dict, list)):
            continue
        parts.append(f"{k}={v}")
    if parts:
        lines.append("values: " + " ".join(str(p) for p in parts))
    dur = metrics.get("duration_sec")
    ec = metrics.get("exit_code")
    if dur is not None or ec is not None:
        lines.append(f"duration_sec={dur}  exit_code={ec}")
    return "\n".join(lines)


def _echo_report(report: dict[str, Any], root: Path, *, pretty: bool, brief: bool) -> None:
    if brief:
        typer.echo(typer.style(_report_brief(report, root), fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style(_json(report, pretty=pretty), fg=typer.colors.GREEN))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
