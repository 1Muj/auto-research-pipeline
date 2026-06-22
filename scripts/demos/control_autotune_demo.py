#!/usr/bin/env python3
"""AutoTune-Control: deterministic PID autotuning demo for auto-research.

The demo simulates a second-order plant and searches PID gains with a small
archive-guided loop inspired by recent automated-system/agentic-system work:
propose -> simulate -> evaluate -> critique -> refine.
"""

from __future__ import annotations

# ruff: noqa: E501
import argparse
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Gains:
    kp: float
    ki: float
    kd: float


@dataclass
class Trial:
    iteration: int
    strategy: str
    kp: float
    ki: float
    kd: float
    tracking_error: float
    settling_time: float
    overshoot: float
    energy_cost: float
    stability_score: float
    objective: float
    critique: str


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def simulate_pid(gains: Gains, *, dt: float, horizon: float, setpoint: float) -> dict[str, object]:
    """Simulate x'' + damping*x' + stiffness*x = u with saturated PID control."""
    damping = 0.42
    stiffness = 1.0
    x = 0.0
    v = 0.0
    integ = 0.0
    prev_error = setpoint - x
    times: list[float] = []
    xs: list[float] = []
    us: list[float] = []
    abs_errors: list[float] = []

    steps = int(horizon / dt)
    for i in range(steps):
        t = i * dt
        error = setpoint - x
        integ = _clamp(integ + error * dt, -2.0, 2.0)
        deriv = (error - prev_error) / dt
        u = gains.kp * error + gains.ki * integ + gains.kd * deriv
        u = _clamp(u, -12.0, 12.0)

        accel = u - damping * v - stiffness * x
        v += accel * dt
        x += v * dt

        times.append(round(t, 4))
        xs.append(round(x, 6))
        us.append(round(u, 6))
        abs_errors.append(abs(error))
        prev_error = error

    tracking_error = sum(abs_errors) / max(len(abs_errors), 1)
    overshoot = max(0.0, max(xs) - setpoint) if xs else 0.0
    energy_cost = sum(u * u for u in us) * dt / max(horizon, dt)
    settling_time = horizon
    tolerance = 0.05 * max(abs(setpoint), 1.0)
    for idx, value in enumerate(xs):
        if all(abs(vv - setpoint) <= tolerance for vv in xs[idx:]):
            settling_time = times[idx]
            break
    stable = math.isfinite(x) and max(abs(vv) for vv in xs) < 5.0
    stability_score = 1.0 if stable else 0.0
    return {
        "tracking_error": tracking_error,
        "settling_time": settling_time,
        "overshoot": overshoot,
        "energy_cost": energy_cost,
        "stability_score": stability_score,
        "trajectory": {
            "time": times[:: max(1, len(times) // 160)],
            "position": xs[:: max(1, len(xs) // 160)],
            "control": us[:: max(1, len(us) // 160)],
        },
    }


def objective(metrics: dict[str, object]) -> float:
    return (
        float(metrics["tracking_error"]) * 1.8
        + float(metrics["settling_time"]) * 0.18
        + float(metrics["overshoot"]) * 2.2
        + float(metrics["energy_cost"]) * 0.04
        + (1.0 - float(metrics["stability_score"])) * 5.0
    )


def critique(metrics: dict[str, object]) -> str:
    parts: list[str] = []
    if float(metrics["tracking_error"]) > 0.12:
        parts.append("tracking error high: increase proportional gain or integral action")
    if float(metrics["overshoot"]) > 0.12:
        parts.append("overshoot high: add damping through derivative gain")
    if float(metrics["settling_time"]) > 2.5:
        parts.append("settling too slow: search more aggressive kp/kd tradeoff")
    if float(metrics["energy_cost"]) > 8.0:
        parts.append("control energy high: penalize excessive gains")
    if not parts:
        parts.append("balanced response: exploit around current best gains")
    return "; ".join(parts)


def propose(
    rng: random.Random,
    iteration: int,
    archive: list[Trial],
) -> tuple[str, Gains]:
    if iteration < 8 or not archive:
        return (
            "space_filling",
            Gains(
                kp=rng.uniform(0.3, 8.0),
                ki=rng.uniform(0.0, 2.0),
                kd=rng.uniform(0.0, 3.5),
            ),
        )

    best = min(archive, key=lambda t: t.objective)
    radius = max(0.08, 0.7 * (1.0 - iteration / 40.0))
    if iteration % 5 == 0:
        return (
            "critic_explore",
            Gains(
                kp=rng.uniform(0.3, 8.0),
                ki=rng.uniform(0.0, 2.0),
                kd=rng.uniform(0.0, 3.5),
            ),
        )
    return (
        "archive_refine",
        Gains(
            kp=_clamp(best.kp + rng.gauss(0.0, radius * 1.5), 0.3, 8.0),
            ki=_clamp(best.ki + rng.gauss(0.0, radius * 0.45), 0.0, 2.0),
            kd=_clamp(best.kd + rng.gauss(0.0, radius * 0.75), 0.0, 3.5),
        ),
    )


def run_search(iterations: int, *, seed: int, dt: float, horizon: float) -> dict[str, object]:
    rng = random.Random(seed)
    archive: list[Trial] = []
    best_trajectory: dict[str, object] = {}
    for i in range(iterations):
        strategy, gains = propose(rng, i, archive)
        metrics = simulate_pid(gains, dt=dt, horizon=horizon, setpoint=1.0)
        score = objective(metrics)
        trial = Trial(
            iteration=i + 1,
            strategy=strategy,
            kp=round(gains.kp, 4),
            ki=round(gains.ki, 4),
            kd=round(gains.kd, 4),
            tracking_error=round(float(metrics["tracking_error"]), 6),
            settling_time=round(float(metrics["settling_time"]), 4),
            overshoot=round(float(metrics["overshoot"]), 6),
            energy_cost=round(float(metrics["energy_cost"]), 6),
            stability_score=round(float(metrics["stability_score"]), 4),
            objective=round(score, 6),
            critique=critique(metrics),
        )
        archive.append(trial)
        if trial.objective == min(t.objective for t in archive):
            best_trajectory = metrics["trajectory"]  # type: ignore[assignment]

    best = min(archive, key=lambda t: t.objective)
    baseline_metrics = simulate_pid(Gains(kp=1.0, ki=0.0, kd=0.0), dt=dt, horizon=horizon, setpoint=1.0)
    baseline_obj = objective(baseline_metrics)
    improvement = max(0.0, (baseline_obj - best.objective) / baseline_obj)
    return {
        "best_tracking_error": best.tracking_error,
        "settling_time": best.settling_time,
        "overshoot": best.overshoot,
        "energy_cost": best.energy_cost,
        "stability_score": best.stability_score,
        "objective": best.objective,
        "baseline_objective": round(baseline_obj, 6),
        "relative_improvement": round(improvement, 6),
        "iterations": iterations,
        "best_gains": {"kp": best.kp, "ki": best.ki, "kd": best.kd},
        "best_critique": best.critique,
        "loop": "propose -> simulate -> evaluate -> critique -> refine",
        "domain": "control_system_pid_autotuning",
        "trial_archive": [asdict(t) for t in archive],
        "best_trajectory": best_trajectory,
    }


def render_dashboard(metrics: dict[str, object], out: Path) -> None:
    trials = metrics.get("trial_archive", [])
    trajectory = metrics.get("best_trajectory", {})
    body = json.dumps({"metrics": metrics, "trials": trials, "trajectory": trajectory}, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoTune-Control Dashboard</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:#15202b; background:#f5f7fa; }}
    header {{ padding:28px 36px; background:#fff; border-bottom:1px solid #d9e2ec; }}
    h1 {{ margin:0 0 8px; font-size:30px; letter-spacing:0; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px 32px 42px; }}
    .sub {{ color:#64748b; }}
    .stats {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .panel,.stat {{ background:#fff; border:1px solid #d9e2ec; border-radius:8px; padding:16px; }}
    .label {{ color:#64748b; font-size:13px; }}
    .value {{ font-size:28px; font-weight:700; margin-top:6px; }}
    .grid {{ display:grid; grid-template-columns:1.1fr .9fr; gap:16px; margin-top:16px; }}
    svg {{ width:100%; height:280px; background:#fbfdff; border:1px solid #e4ebf2; border-radius:6px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:8px; border-bottom:1px solid #e4ebf2; text-align:left; }}
    th {{ color:#64748b; }}
    .ok {{ color:#157347; font-weight:700; }}
    @media (max-width:800px) {{ .stats,.grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AutoTune-Control</h1>
    <div class="sub">Archive-guided PID autotuning: propose -> simulate -> evaluate -> critique -> refine.</div>
  </header>
  <main>
    <section class="stats" id="stats"></section>
    <section class="grid">
      <div class="panel"><h2>Best Response</h2><svg id="trajectory"></svg></div>
      <div class="panel"><h2>Best Gains</h2><div id="gains"></div><h2>Critique</h2><p id="critique"></p></div>
    </section>
    <section class="panel" style="margin-top:16px"><h2>Search Archive</h2><table id="archive"></table></section>
  </main>
  <script>
    const data = {body};
    const m = data.metrics;
    const stats = [
      ['Tracking error', m.best_tracking_error],
      ['Settling time', m.settling_time],
      ['Overshoot', m.overshoot],
      ['Improvement', Math.round(m.relative_improvement * 1000) / 10 + '%']
    ];
    document.getElementById('stats').innerHTML = stats.map(([k,v]) => `<div class="stat"><div class="label">${{k}}</div><div class="value">${{v}}</div></div>`).join('');
    document.getElementById('gains').innerHTML = `<div class="value">Kp=${{m.best_gains.kp}} Ki=${{m.best_gains.ki}} Kd=${{m.best_gains.kd}}</div>`;
    document.getElementById('critique').textContent = m.best_critique;
    const svg = document.getElementById('trajectory');
    const t = data.trajectory.time || [];
    const x = data.trajectory.position || [];
    const w = 800, h = 260, pad = 28;
    svg.setAttribute('viewBox', `0 0 ${{w}} ${{h}}`);
    const xmax = Math.max(...t, 1), ymin = Math.min(...x, 0), ymax = Math.max(...x, 1.1);
    const sx = v => pad + (w - 2 * pad) * v / xmax;
    const sy = v => h - pad - (h - 2 * pad) * (v - ymin) / Math.max(ymax - ymin, 0.001);
    const path = x.map((v,i) => `${{i ? 'L' : 'M'}}${{sx(t[i]).toFixed(1)}},${{sy(v).toFixed(1)}}`).join(' ');
    svg.innerHTML = `<line x1="${{pad}}" y1="${{sy(1)}}" x2="${{w-pad}}" y2="${{sy(1)}}" stroke="#94a3b8" stroke-dasharray="5 4"/>` +
      `<path d="${{path}}" fill="none" stroke="#1d4ed8" stroke-width="3"/>`;
    const top = [...data.trials].sort((a,b) => a.objective - b.objective).slice(0, 12);
    document.getElementById('archive').innerHTML = '<tr><th>#</th><th>strategy</th><th>Kp</th><th>Ki</th><th>Kd</th><th>obj</th><th>error</th><th>overshoot</th></tr>' +
      top.map(r => `<tr><td>${{r.iteration}}</td><td>${{r.strategy}}</td><td>${{r.kp}}</td><td>${{r.ki}}</td><td>${{r.kd}}</td><td class="ok">${{r.objective}}</td><td>${{r.tracking_error}}</td><td>${{r.overshoot}}</td></tr>`).join('');
  </script>
</body>
</html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=28)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--dt", type=float, default=0.02)
    parser.add_argument("--horizon", type=float, default=6.0)
    parser.add_argument("--metrics-path", type=Path, default=Path("metrics.json"))
    parser.add_argument(
        "--dashboard-path",
        type=Path,
        default=Path("experiments/agent_output/control_autotune_dashboard.html"),
    )
    args = parser.parse_args()

    metrics = run_search(args.iterations, seed=args.seed, dt=args.dt, horizon=args.horizon)
    args.metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    render_dashboard(metrics, args.dashboard_path)
    summary = {
        k: v
        for k, v in metrics.items()
        if k not in {"trial_archive", "best_trajectory"}
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
