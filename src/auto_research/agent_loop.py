"""Optional loop: run experiment, read feedback, write a markdown brief for Claude Code / human."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import ValidationError

from auto_research.config import ExperimentSpec, PipelineConfig
from auto_research.pipeline import ResearchPipeline
from auto_research.preflight import preflight_experiment

_YAML_FENCE = re.compile(r"```(?:yaml|yml)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_first_yaml_fence(markdown: str) -> str | None:
    """Return inner text of the first ```yaml / ```yml fenced block, or None."""
    m = _YAML_FENCE.search(markdown)
    return m.group(1).strip() if m else None


def apply_llm_yaml_to_experiment(
    llm_markdown: str,
    experiment: Path,
    cwd: Path | None,
    backup_dir: Path,
) -> tuple[bool, str, Path | None]:
    """
    Parse first YAML fence from LLM output, validate + preflight, backup original, write experiment.
    """
    raw = extract_first_yaml_fence(llm_markdown)
    if not raw:
        return False, "No ```yaml (or ```yml) fenced block in LLM response.", None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return False, f"Invalid YAML syntax: {e}", None
    if not isinstance(data, dict):
        return False, "YAML root must be a mapping (object).", None
    try:
        ExperimentSpec.model_validate(data)
    except ValidationError as e:
        return False, f"Invalid experiment fields: {e}", None

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="auto_research_patch_",
        delete=False,
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(raw)
        tmp_path = Path(f.name)
    try:
        errs, _warns = preflight_experiment(tmp_path, cwd)
        if errs:
            return False, "Preflight failed for proposed YAML: " + "; ".join(errs), None
    finally:
        tmp_path.unlink(missing_ok=True)

    experiment = experiment.resolve()
    if not experiment.is_file():
        return False, f"Experiment file not found: {experiment}", None

    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{experiment.stem}_pre_patch_{ts}.yaml"
    shutil.copy2(experiment, backup_path)
    experiment.write_text(raw, encoding="utf-8")
    return True, f"Updated {experiment} (backup: {backup_path})", backup_path


def _build_remediation_prompt(
    yaml_source: str,
    feedback: dict[str, Any],
    report: dict[str, Any],
    *,
    require_full_yaml_fence: bool = False,
) -> str:
    payload = {
        "feedback": feedback,
        "run_summary": report.get("summary"),
        "metrics": report.get("metrics"),
    }
    passed = bool(feedback.get("thresholds_passed"))
    goal = (
        "All thresholds passed. Suggest optional follow-up experiments or small improvements."
        if passed
        else (
            "Thresholds failed. Diagnose and propose concrete fixes to command, "
            "success_threshold, or training code."
        )
    )
    return (
        "You help improve an auto-research experiment. "
        f"{goal}\n\n"
        "## Current experiment YAML\n\n```yaml\n"
        + yaml_source[:80000]
        + "\n```\n\n## Latest run (JSON)\n\n```json\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)[:60000]
        + "\n```\n\n"
        "Respond in Markdown."
        + (
            " You must output exactly one fenced ```yaml block containing the **complete** "
            "replacement experiment file (valid YAML, all required keys such as `name`)."
            if require_full_yaml_fence
            else " If proposing a full YAML replacement, use one ```yaml block."
        )
        + "\nDo not invent paths outside the repo root."
    )


def _llm_anthropic(user_prompt: str) -> str | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    client = Anthropic()
    msg = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        max_tokens=4096,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts: list[str] = []
    for block in msg.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts) if parts else None


def _llm_openai_compatible(user_prompt: str) -> str | None:
    """Chat Completions API (OpenAI or any compatible gateway)."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    url = f"{base}/chat/completions"
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "max_tokens": 4096,
                },
            )
            r.raise_for_status()
            data = r.json()
        choice = data["choices"][0]["message"]["content"]
        return str(choice) if choice is not None else None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None


def _llm_remediation(
    yaml_source: str,
    feedback: dict[str, Any],
    report: dict[str, Any],
    *,
    require_full_yaml_fence: bool = False,
) -> str | None:
    user = _build_remediation_prompt(
        yaml_source,
        feedback,
        report,
        require_full_yaml_fence=require_full_yaml_fence,
    )
    prefer = (os.environ.get("AUTO_RESEARCH_LLM_PROVIDER") or "").strip().lower()
    has_a = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_o = bool(os.environ.get("OPENAI_API_KEY"))

    if prefer == "openai" and has_o:
        out = _llm_openai_compatible(user)
        if out:
            return out
    if prefer == "anthropic" and has_a:
        out = _llm_anthropic(user)
        if out:
            return out

    if has_a and (not prefer or prefer not in ("openai", "anthropic")):
        out = _llm_anthropic(user)
        if out:
            return out
    if has_o:
        return _llm_openai_compatible(user)
    return None


def write_agent_markdown(
    out_dir: Path,
    experiment: Path,
    feedback_path: Path,
    round_idx: int,
    feedback: dict[str, Any],
    report: dict[str, Any],
    llm_text: str | None,
    yaml_patch_note: str | None = None,
    *,
    timestamp: str | None = None,
    experiment_yaml_backup: Path | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"agent_round{round_idx}_{ts}.md"
    lines = [
        "# Research agent turn",
        "",
        f"- **experiment file**: `{experiment}`",
    ]
    if experiment_yaml_backup is not None:
        lines.append(
            f"- **experiment YAML backup (before this run)**: `{experiment_yaml_backup}`",
        )
    lines.extend(
        [
        f"- **round**: {round_idx}",
        f"- **thresholds_passed**: {feedback.get('thresholds_passed')}",
        f"- **feedback file**: `{feedback_path}`",
        "",
        ]
    )
    lines.extend(
        [
        "## Threshold detail",
        "",
        "```json",
        json.dumps(feedback.get("threshold_detail", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Metrics snapshot",
        "",
        "```json",
        json.dumps(feedback.get("metrics", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        ]
    )
    if llm_text:
        lines.extend(["## Suggested next edits (LLM)", "", llm_text, ""])
    if yaml_patch_note:
        lines.extend(["## YAML auto-patch", "", yaml_patch_note, ""])
    if not llm_text:
        lines.extend(
            [
                "## Next steps (Claude Code)",
                "",
                "Open this file in **Claude Code** (or your editor assistant) and ask it to "
                "propose changes to the experiment YAML or training script from the metrics "
                "and threshold detail above.",
                "",
                "Optional: run again with `auto-research agent --llm ...` with "
                "`ANTHROPIC_API_KEY` (and `pip install -e \".[anthropic]\"`) or "
                "`OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL` / `OPENAI_MODEL`) to "
                "pre-fill an LLM section in this brief.",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_agent_turn(
    experiment: Path,
    cwd: Path | None,
    *,
    use_llm: bool,
    out_dir: Path | None,
    apply_suggested_yaml: bool = False,
) -> tuple[int, dict[str, Any] | None, list[str]]:
    """
    Preflight → run one experiment → write agent markdown.
    Exit codes: 0 thresholds ok, 1 thresholds miss, 2 preflight errors,
    3 --apply-suggested-yaml set but patch not applied.
    """
    if apply_suggested_yaml and not use_llm:
        return 2, None, ["--apply-suggested-yaml requires --llm"]

    cfg = PipelineConfig().resolved(cwd)
    od = out_dir or (cfg.experiments_dir / "agent_output")

    errs, _ = preflight_experiment(experiment, cwd)
    if errs:
        return 2, None, errs

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = od / "yaml_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    exp_path = experiment.resolve()
    run_yaml_backup = backup_dir / f"{exp_path.stem}_before_agent_run_{run_ts}.yaml"
    shutil.copy2(exp_path, run_yaml_backup)

    yaml_source = exp_path.read_text(encoding="utf-8")
    pipe = ResearchPipeline(base=cwd)
    report = pipe.run_one(experiment)
    fb_path = Path(report["feedback_path"])
    feedback = json.loads(fb_path.read_text(encoding="utf-8"))

    llm_text = (
        _llm_remediation(
            yaml_source,
            feedback,
            report,
            require_full_yaml_fence=apply_suggested_yaml,
        )
        if use_llm
        else None
    )

    patch_meta: dict[str, Any] | None = None
    yaml_patch_note: str | None = None

    if apply_suggested_yaml:
        if not llm_text:
            patch_meta = {
                "applied": False,
                "message": (
                    "No LLM response (set ANTHROPIC_API_KEY + anthropic extra, or OPENAI_API_KEY)."
                ),
                "backup": None,
            }
        else:
            ok, msg, backup = apply_llm_yaml_to_experiment(
                llm_text, experiment, cwd, backup_dir
            )
            patch_meta = {
                "applied": ok,
                "message": msg,
                "backup": str(backup) if backup else None,
            }
        lines_pf = [
            f"- **applied**: {patch_meta['applied']}",
            f"- **detail**: {patch_meta['message']}",
        ]
        if patch_meta.get("backup"):
            lines_pf.append(f"- **backup**: `{patch_meta['backup']}`")
        yaml_patch_note = "\n".join(lines_pf)

    written = write_agent_markdown(
        od,
        experiment,
        fb_path,
        1,
        feedback,
        report,
        llm_text,
        yaml_patch_note=yaml_patch_note,
        timestamp=run_ts,
        experiment_yaml_backup=run_yaml_backup,
    )
    report = {
        **report,
        "agent_markdown": str(written),
        "experiment_yaml_backup": str(run_yaml_backup),
    }
    if patch_meta is not None:
        report["yaml_patch"] = patch_meta

    if apply_suggested_yaml and patch_meta and not patch_meta.get("applied"):
        return 3, report, []
    if feedback.get("thresholds_passed"):
        return 0, report, []
    return 1, report, []
