from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_research.config import PipelineConfig, load_experiment_yaml
from auto_research.experiments import run_experiment
from auto_research.feedback import maybe_llm_feedback, write_feedback


class ResearchPipeline:
    def __init__(self, base: Path | None = None) -> None:
        self.cfg = PipelineConfig().resolved(base)

    def run_one(self, experiment_file: Path) -> dict[str, Any]:
        spec = load_experiment_yaml(experiment_file)
        summary = run_experiment(spec, self.cfg)
        metrics_path = Path(summary["metrics_path"])
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        fb_path = write_feedback(spec, self.cfg, summary, metrics)
        report = {
            "summary": summary,
            "feedback_path": str(fb_path),
            "metrics": metrics,
        }
        llm = maybe_llm_feedback(report)
        if llm:
            out = self.cfg.feedback_dir / f"{summary['run_id']}_llm.txt"
            out.write_text(llm, encoding="utf-8")
            report["llm_summary_path"] = str(out)
        return report

    def run_all(self, pattern: str = "*.yaml") -> list[dict[str, Any]]:
        self.cfg.experiments_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        for path in sorted(self.cfg.experiments_dir.glob(pattern)):
            if path.name.startswith("_"):
                continue
            results.append(self.run_one(path))
        return results
