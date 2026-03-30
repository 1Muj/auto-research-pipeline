from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from auto_research.config import ExperimentSpec, PipelineConfig


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_experiment(
    spec: ExperimentSpec,
    cfg: PipelineConfig,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute experiment command, capture env, write run manifest and metrics."""
    rid = run_id or f"{spec.name}_{uuid.uuid4().hex[:8]}"
    run_dir = cfg.runs_dir / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, **spec.env}
    manifest: dict[str, Any] = {
        "run_id": rid,
        "experiment": spec.name,
        "started_at": _utc_now(),
        "command": spec.command,
        "cwd": str(cfg.root),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    metrics: dict[str, Any] = {}
    status = "skipped"
    if spec.command:
        t0 = time.perf_counter()
        proc = subprocess.run(
            spec.command,
            cwd=cfg.root,
            env=env,
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - t0
        manifest["finished_at"] = _utc_now()
        manifest["exit_code"] = proc.returncode
        manifest["duration_sec"] = round(elapsed, 4)
        manifest["stdout_tail"] = (proc.stdout or "")[-8000:]
        manifest["stderr_tail"] = (proc.stderr or "")[-8000:]
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        status = "ok" if proc.returncode == 0 else "failed"

        metrics_path = cfg.root / spec.metrics_path
        if metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        else:
            metrics = {
                "loss": float("nan"),
                "note": "metrics file missing; fill via your training script",
            }
        metrics["duration_sec"] = round(elapsed, 4)
        metrics["exit_code"] = proc.returncode
    else:
        manifest["finished_at"] = _utc_now()
        manifest["note"] = "no command; dry run"
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        metrics = {"dry_run": True}

    metrics_out = run_dir / "metrics.json"
    metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    summary = {
        "run_id": rid,
        "experiment": spec.name,
        "status": status,
        "metrics_path": str(metrics_out),
        "manifest_path": str(run_dir / "manifest.json"),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
