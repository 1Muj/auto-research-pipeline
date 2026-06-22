from __future__ import annotations

# ruff: noqa: E501
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auto_research.config import PipelineConfig, load_experiment_yaml

SYSTEM_COMPARISON: list[dict[str, str]] = [
    {
        "system": "AI Scientist-v2",
        "focus": "End-to-end automated ML discovery",
        "mechanism": "Hypothesis, experiment execution, analysis, figures, paper writing, reviewer loop",
        "auto_research_mapping": "YAML experiment spec, Vast execution, threshold feedback, reviewer brief",
        "lite_implementation": "review + visualize commands over real run artifacts",
    },
    {
        "system": "Google AI Co-Scientist",
        "focus": "Scientist-in-the-loop hypothesis generation",
        "mechanism": "Multi-agent generation, reflection, ranking, evolution of hypotheses",
        "auto_research_mapping": "Governance fields plus critic recommendations from metrics",
        "lite_implementation": "review command checks hypothesis/metrics alignment and next experiments",
    },
    {
        "system": "OpenAI PaperBench",
        "focus": "Evaluate research-paper replication by agents",
        "mechanism": "Hierarchical rubrics and objective grading of replication subtasks",
        "auto_research_mapping": "success_threshold and threshold_detail as a compact rubric",
        "lite_implementation": "feedback JSON and visualization expose pass/fail evidence",
    },
    {
        "system": "Hugging Face ML Intern",
        "focus": "Open-source ML engineer agent for HF ecosystem",
        "mechanism": "Agent loop, tool router, docs/papers/datasets access, local or sandbox tools, traces",
        "auto_research_mapping": "Local CLI, experiment commands, Vast push, artifacts, review output",
        "lite_implementation": "ml-intern-lite demo tracks planning, tool trace, artifact and shipping metrics",
    },
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_feedback_for_experiment(cfg: PipelineConfig, experiment_name: str) -> Path:
    candidates: list[tuple[float, Path]] = []
    for path in cfg.feedback_dir.glob("*_feedback.json"):
        try:
            body = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if body.get("experiment") == experiment_name:
            candidates.append((path.stat().st_mtime, path))
    if not candidates:
        raise FileNotFoundError(
            f"No feedback found for experiment '{experiment_name}' under {cfg.feedback_dir}"
        )
    return max(candidates, key=lambda item: item[0])[1]


def _manifest_for_feedback(cfg: PipelineConfig, feedback: dict[str, Any]) -> dict[str, Any]:
    run_id = str(feedback.get("run_id") or "")
    if not run_id:
        return {}
    path = cfg.runs_dir / run_id / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return _load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def _threshold_lines(detail: dict[str, Any]) -> list[str]:
    if not detail:
        return ["- No success thresholds were provided; add a measurable rubric."]
    lines: list[str] = []
    for key, item in detail.items():
        if not isinstance(item, dict):
            lines.append(f"- `{key}`: malformed threshold detail")
            continue
        passed = "pass" if item.get("pass") else "fail"
        if item.get("reason"):
            lines.append(f"- `{key}`: **{passed}** ({item.get('reason')})")
            continue
        value = item.get("value")
        bound = item.get("bound")
        direction = item.get("direction")
        lines.append(f"- `{key}`: **{passed}** value={value} bound={bound} direction={direction}")
    return lines


def _next_actions(feedback: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    detail = feedback.get("threshold_detail") or {}
    failed = [k for k, v in detail.items() if isinstance(v, dict) and not v.get("pass")]
    metrics = feedback.get("metrics") or {}
    actions: list[str] = []
    if failed:
        actions.append(
            "Tighten the next run around failed metrics: "
            + ", ".join(f"`{name}`" for name in failed)
            + "."
        )
        actions.append(
            "Inspect `manifest.json` stdout/stderr tails before changing thresholds; fix execution "
            "or data issues before treating the result as a model-quality problem."
        )
    else:
        actions.append(
            "Keep the current run as the baseline artifact and run one ablation that changes only one "
            "factor: training budget, model size, data split, or metric threshold."
        )
        actions.append(
            "Add a stronger success threshold or a second metric if this demo is now too easy."
        )
    if metrics.get("device") in ("cpu", "no cuda"):
        actions.append("GPU was not used according to metrics; verify `nvidia-smi` and PyTorch CUDA.")
    if manifest.get("exit_code") not in (None, 0):
        actions.append(f"Command exited with code {manifest.get('exit_code')}; prioritize runtime repair.")
    actions.append("Regenerate the visualization after the next Vast run and compare deltas.")
    return actions


def build_review_markdown(
    experiment_path: Path,
    cfg: PipelineConfig,
    *,
    feedback_path: Path | None = None,
) -> str:
    spec = load_experiment_yaml(experiment_path)
    fb_path = feedback_path or _latest_feedback_for_experiment(cfg, spec.name)
    feedback = _load_json(fb_path)
    manifest = _manifest_for_feedback(cfg, feedback)
    governance = manifest.get("governance") or {}
    lines = [
        "# Auto Research Reviewer Brief",
        "",
        f"- experiment: `{spec.name}`",
        f"- experiment_yaml: `{experiment_path}`",
        f"- feedback: `{fb_path}`",
        f"- run_id: `{feedback.get('run_id', '')}`",
        f"- thresholds_passed: **{feedback.get('thresholds_passed')}**",
        "",
        "## Hypothesis Alignment",
        "",
        f"- hypothesis: {governance.get('hypothesis') or spec.hypothesis or '(not set)'}",
        f"- phase: {governance.get('governance_phase') or spec.governance_phase or '(not set)'}",
        f"- command_exit_code: {manifest.get('exit_code', '(unknown)')}",
        "",
        "## Threshold Review",
        "",
        *_threshold_lines(feedback.get("threshold_detail") or {}),
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(feedback.get("metrics", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Critic Recommendations",
        "",
    ]
    lines.extend(f"- {item}" for item in _next_actions(feedback, manifest))
    lines.extend(
        [
            "",
            "## Relation To Recent Agentic Research Systems",
            "",
            "- AI Scientist-v2 style: this brief is the lightweight reviewer loop after an experiment.",
            "- Co-Scientist style: hypothesis and next-action sections keep a human scientist in the loop.",
            "- PaperBench style: thresholds act as a small rubric instead of a full replication rubric.",
            "- ML Intern style: the pipeline ships runnable code/artifacts, not only a text answer.",
            "",
        ]
    )
    return "\n".join(lines)


def write_review(
    experiment_path: Path,
    cfg: PipelineConfig,
    *,
    out_dir: Path | None = None,
    feedback_path: Path | None = None,
) -> Path:
    od = out_dir or (cfg.experiments_dir / "agent_output")
    od.mkdir(parents=True, exist_ok=True)
    spec = load_experiment_yaml(experiment_path)
    out = od / f"review_{spec.name}_{_utc_stamp()}.md"
    out.write_text(
        build_review_markdown(experiment_path, cfg, feedback_path=feedback_path),
        encoding="utf-8",
    )
    return out


def comparison_markdown() -> str:
    lines = [
        "# Background Comparison: Automated Research Agents",
        "",
        "| System | Focus | Mechanism | Mapping in auto-research | Lite implementation |",
        "|---|---|---|---|---|",
    ]
    for row in SYSTEM_COMPARISON:
        lines.append(
            "| {system} | {focus} | {mechanism} | {auto_research_mapping} | "
            "{lite_implementation} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## References",
            "",
            "- AI Scientist-v2: https://arxiv.org/abs/2504.08066",
            "- Google AI Co-Scientist: https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/",
            "- PaperBench: https://arxiv.org/abs/2504.01848",
            "- Hugging Face ML Intern: https://github.com/huggingface/ml-intern",
            "",
        ]
    )
    return "\n".join(lines)


def write_comparison(cfg: PipelineConfig, *, out: Path | None = None) -> Path:
    path = out or (cfg.root / "docs" / "comparison_auto_research_agents.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(comparison_markdown(), encoding="utf-8")
    return path


def _collect_feedback_rows(cfg: PipelineConfig, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(cfg.feedback_dir.glob("*_feedback.json"), key=lambda p: p.stat().st_mtime):
        try:
            fb = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        manifest = _manifest_for_feedback(cfg, fb)
        metrics = fb.get("metrics") or {}
        rows.append(
            {
                "path": str(path),
                "experiment": fb.get("experiment"),
                "run_id": fb.get("run_id"),
                "passed": bool(fb.get("thresholds_passed")),
                "duration_sec": metrics.get("duration_sec", manifest.get("duration_sec")),
                "exit_code": metrics.get("exit_code", manifest.get("exit_code")),
                "device": metrics.get("device", ""),
                "metrics": metrics,
                "threshold_detail": fb.get("threshold_detail") or {},
            }
        )
    return rows[-limit:]


def visualization_html(cfg: PipelineConfig, *, limit: int = 20) -> str:
    rows = _collect_feedback_rows(cfg, limit)
    passed = sum(1 for row in rows if row["passed"])
    failed = len(rows) - passed
    data = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto Research Vast Demo Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5e6b78;
      --line: #d9e2ec;
      --ok: #157347;
      --bad: #b42318;
      --accent: #1d4ed8;
      --bg: #f7f9fb;
      --panel: #ffffff;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 28px 32px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    .sub {{ color: var(--muted); font-size: 14px; }}
    main {{ padding: 24px 32px 40px; max-width: 1180px; margin: 0 auto; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .stat, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .label {{ color: var(--muted); font-size: 13px; }}
    .value {{ font-size: 30px; font-weight: 700; margin-top: 6px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); }}
    th {{ color: var(--muted); font-weight: 600; }}
    .ok {{ color: var(--ok); font-weight: 700; }}
    .bad {{ color: var(--bad); font-weight: 700; }}
    .bar {{ height: 12px; border-radius: 999px; background: #e5eaf0; overflow: hidden; }}
    .bar > span {{ display: block; height: 100%; background: var(--accent); }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #0b1220; color: #d8e5ff; padding: 12px; border-radius: 6px; }}
    @media (max-width: 760px) {{ .stats, .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Auto Research Vast Demo Dashboard</h1>
    <div class="sub">Generated from local <code>experiments/feedback</code> artifacts. Source rows: {len(rows)}.</div>
  </header>
  <main>
    <section class="stats">
      <div class="stat"><div class="label">Runs</div><div class="value">{len(rows)}</div></div>
      <div class="stat"><div class="label">Passed</div><div class="value ok">{passed}</div></div>
      <div class="stat"><div class="label">Failed</div><div class="value bad">{failed}</div></div>
      <div class="stat"><div class="label">Pass rate</div><div class="value">{round((passed / len(rows) * 100) if rows else 0, 1)}%</div></div>
    </section>
    <section class="grid">
      <div class="panel">
        <h2>Run Timeline</h2>
        <table id="runs"></table>
      </div>
      <div class="panel">
        <h2>Metric Snapshot</h2>
        <div id="metricBars"></div>
      </div>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Raw Latest Feedback</h2>
      <pre id="raw"></pre>
    </section>
  </main>
  <script>
    const rows = {data};
    const table = document.getElementById('runs');
    table.innerHTML = '<tr><th>Experiment</th><th>Run</th><th>Status</th><th>Device</th><th>Duration</th></tr>' +
      rows.map(r => `<tr><td>${{r.experiment || ''}}</td><td>${{r.run_id || ''}}</td>` +
        `<td class="${{r.passed ? 'ok' : 'bad'}}">${{r.passed ? 'pass' : 'fail'}}</td>` +
        `<td>${{r.device || ''}}</td><td>${{r.duration_sec ?? ''}}</td></tr>`).join('');
    const latest = rows[rows.length - 1] || {{}};
    const metrics = latest.metrics || {{}};
    const numeric = Object.entries(metrics).filter(([, v]) => typeof v === 'number' && isFinite(v));
    document.getElementById('metricBars').innerHTML = numeric.map(([k, v]) => {{
      const width = Math.max(4, Math.min(100, Math.abs(v) * 100));
      return `<div style="margin:10px 0"><div class="label">${{k}} = ${{v}}</div><div class="bar"><span style="width:${{width}}%"></span></div></div>`;
    }}).join('') || '<div class="label">No numeric metrics yet.</div>';
    document.getElementById('raw').textContent = JSON.stringify(latest, null, 2);
  </script>
</body>
</html>
"""


def write_visualization(cfg: PipelineConfig, *, out: Path | None = None, limit: int = 20) -> Path:
    path = out or (cfg.root / "experiments" / "agent_output" / "vast_demo_dashboard.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(visualization_html(cfg, limit=limit), encoding="utf-8")
    return path
