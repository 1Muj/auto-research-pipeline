from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from auto_research.config import ExperimentSpec, PipelineConfig


def _minimize_metric(name: str) -> bool:
    n = name.lower()
    return "loss" in n or "error" in n or n.startswith("perplexity")


def evaluate_thresholds(
    metrics: dict[str, Any],
    thresholds: dict[str, float],
) -> tuple[bool, dict[str, Any]]:
    """Return (all_passed, per-metric detail).

    Lower-is-better for names containing loss/error; else higher-is-better.
    """
    detail: dict[str, Any] = {}
    ok = True
    for key, bound in thresholds.items():
        if key not in metrics:
            detail[key] = {"pass": False, "reason": "missing"}
            ok = False
            continue
        val = metrics[key]
        try:
            fv = float(val)
        except (TypeError, ValueError):
            detail[key] = {"pass": False, "reason": "not_numeric", "value": val}
            ok = False
            continue
        minimize = _minimize_metric(key)
        passed = fv <= bound if minimize else fv >= bound
        detail[key] = {
            "pass": passed,
            "value": fv,
            "bound": bound,
            "direction": "minimize" if minimize else "maximize",
        }
        ok = ok and passed
    return ok, detail


def write_feedback(
    spec: ExperimentSpec,
    cfg: PipelineConfig,
    run_summary: dict[str, Any],
    metrics: dict[str, Any],
) -> Path:
    cfg.feedback_dir.mkdir(parents=True, exist_ok=True)
    passed, detail = evaluate_thresholds(metrics, spec.success_threshold)
    body: dict[str, Any] = {
        "experiment": spec.name,
        "run_id": run_summary.get("run_id"),
        "thresholds_passed": passed,
        "threshold_detail": detail,
        "metrics": metrics,
    }
    out = cfg.feedback_dir / f"{run_summary.get('run_id', 'unknown')}_feedback.json"
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return out


def maybe_llm_feedback(report: dict[str, Any]) -> str | None:
    """
    Optional: call Anthropic Messages API to summarize experiment outcome.
    Requires: pip install 'auto-research[anthropic]' and ANTHROPIC_API_KEY.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    client = Anthropic()
    text = json.dumps(report, indent=2)[:120000]
    msg = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize this experiment feedback in 5 bullet points, "
                    "with concrete next steps.\n\n" + text
                ),
            }
        ],
    )
    parts = []
    for block in msg.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts) if parts else None
