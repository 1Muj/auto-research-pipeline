"""Pre-run checks for experiment YAML (governance gate before auto-research run)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from auto_research.config import PipelineConfig, load_experiment_yaml


def preflight_experiment(yaml_path: Path, base: Path | None = None) -> tuple[list[str], list[str]]:
    """
    Return (errors, warnings). Errors should block CI; warnings are advisory.
    """
    errors: list[str] = []
    warnings: list[str] = []
    cfg = PipelineConfig().resolved(base)

    if not yaml_path.is_file():
        errors.append(f"Experiment file not found: {yaml_path}")
        return errors, warnings

    try:
        spec = load_experiment_yaml(yaml_path)
    except Exception as e:  # noqa: BLE001 — surface validation errors to user
        errors.append(f"Invalid experiment YAML: {e}")
        return errors, warnings

    if not spec.command:
        warnings.append("command is empty: run will produce a dry-run manifest only")

    mp = Path(spec.metrics_path)
    if mp.is_absolute():
        errors.append(f"metrics_path must be relative to project root, got: {spec.metrics_path}")

    root = cfg.root
    target = (root / spec.metrics_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        errors.append("metrics_path escapes project root (path traversal risk)")

    if not spec.success_threshold:
        warnings.append("success_threshold is empty: feedback will not gate on metrics")

    if spec.governance_phase and spec.governance_phase not in {
        "think",
        "plan",
        "build",
        "review",
        "test",
        "ship",
        "reflect",
    }:
        warnings.append(
            f"governance_phase '{spec.governance_phase}' is non-standard "
            "(expected think|plan|build|review|test|ship|reflect)"
        )

    return errors, warnings


def preflight_report(yaml_path: Path, base: Path | None = None) -> dict[str, Any]:
    errs, warns = preflight_experiment(yaml_path, base)
    return {"ok": not errs, "errors": errs, "warnings": warns}
