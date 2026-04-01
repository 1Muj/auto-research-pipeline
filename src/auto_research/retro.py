"""Aggregate recent feedback files into a short markdown retro."""

from __future__ import annotations

import json

from auto_research.config import PipelineConfig


def retro_markdown(cfg: PipelineConfig, last_n: int = 10) -> str:
    fb_dir = cfg.feedback_dir
    if not fb_dir.is_dir():
        return "# Experiment retro\n\nNo `experiments/feedback/` directory yet.\n"

    files = sorted(
        fb_dir.glob("*_feedback.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(1, last_n)]

    if not files:
        return "# Experiment retro\n\nNo `*_feedback.json` files yet.\n"

    lines: list[str] = [
        "# Experiment retro",
        "",
        f"Last **{len(files)}** feedback file(s), newest first.",
        "",
    ]
    passed = 0
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            lines.append(f"- **{p.name}**: (unreadable: {e})")
            continue
        ok = data.get("thresholds_passed")
        if ok is True:
            passed += 1
        exp = data.get("experiment", "?")
        rid = data.get("run_id", "?")
        lines.append(f"- **{p.name}** — `{exp}` / `{rid}` — thresholds_passed={ok}")
    lines.append("")
    lines.append(f"**Summary:** {passed}/{len(files)} runs passed all thresholds (in this sample).")
    lines.append("")
    lines.append("Re-run with a larger window: `auto-research retro --last 20`")
    return "\n".join(lines)
