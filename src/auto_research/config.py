from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ExperimentSpec(BaseModel):
    """Single experiment definition (YAML-backed)."""

    name: str
    description: str = ""
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    metrics_path: str = "metrics.json"
    success_threshold: dict[str, float] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    root: Path = Field(default_factory=lambda: Path.cwd())
    experiments_dir: Path = Field(default_factory=lambda: Path("experiments"))
    runs_dir: Path = Field(default_factory=lambda: Path("experiments/runs"))
    feedback_dir: Path = Field(default_factory=lambda: Path("experiments/feedback"))

    def resolved(self, base: Path | None = None) -> PipelineConfig:
        b = (base or self.root).resolve()
        return PipelineConfig(
            root=b,
            experiments_dir=(b / self.experiments_dir).resolve(),
            runs_dir=(b / self.runs_dir).resolve(),
            feedback_dir=(b / self.feedback_dir).resolve(),
        )


def load_experiment_yaml(path: Path) -> ExperimentSpec:
    import yaml

    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ExperimentSpec.model_validate(data)
