from __future__ import annotations

import json
import os
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DIMENSIONS = [
    {
        "id": "content_script_quality",
        "name": "Content / Script Quality",
        "weight": 0.24,
        "description": (
            "Checks whether the narration is correct, complete, grounded, and natural."
        ),
        "checkpoints": [
            "Content is faithful to the source paper, project, or user topic.",
            "Core problem, method, evidence, conclusion, and limitations are covered.",
            "Claims are specific and supported; no hallucinated results or invented details.",
            "Narration sounds like an explanation rather than mechanical script reading.",
        ],
        "high_signals": ["grounded claims", "clear arc", "specific evidence", "natural wording"],
        "low_signals": [
            "hallucinations",
            "missing core ideas",
            "empty claims",
            "script-like wording",
        ],
    },
    {
        "id": "slide_visual_quality",
        "name": "Slide Visual Quality",
        "weight": 0.18,
        "description": (
            "Checks whether the PPT pages are readable, structured, and visually useful."
        ),
        "checkpoints": [
            "Slide text is legible and not overcrowded.",
            "Layout, hierarchy, charts, and tables support scanning and comprehension.",
            "Visual elements serve the explanation rather than acting as decoration.",
            "Information density fits a narrated video format.",
        ],
        "high_signals": ["legible slides", "clear hierarchy", "useful visuals", "balanced density"],
        "low_signals": ["tiny text", "crowded layout", "irrelevant visuals", "weak hierarchy"],
    },
    {
        "id": "audio_narration_quality",
        "name": "Audio / Narration Quality",
        "weight": 0.14,
        "description": (
            "Checks voice clarity, pacing, pauses, audio quality, and transcript naturalness."
        ),
        "checkpoints": [
            "Speech pace, pauses, volume, and sentence boundaries are comfortable.",
            "Narration is clear, non-repetitive, and understandable.",
            "Audio has no obvious noise, clipping, dropouts, or sync-breaking artifacts.",
            "If audio is missing, judge from transcript only and lower confidence.",
        ],
        "high_signals": ["clean audio", "natural pauses", "comfortable pace", "clear transcript"],
        "low_signals": ["too fast", "noise", "repetition", "bad sentence breaks"],
    },
    {
        "id": "cross_modal_alignment",
        "name": "Cross-modal Alignment",
        "weight": 0.22,
        "description": (
            "Checks whether slide, narration, subtitles, cursor/focus, and timing agree."
        ),
        "checkpoints": [
            "Current narration corresponds to the active slide.",
            "Subtitles, visual focus, cursor movement, and key frames support the spoken point.",
            "There is no repeated pattern of saying one thing while showing another.",
            "Per-slide duration is appropriate for the amount of content.",
        ],
        "high_signals": ["slide-speech match", "good timing", "useful visual focus"],
        "low_signals": ["talking about absent content", "mistimed slide changes", "random focus"],
    },
    {
        "id": "stability_overall_experience",
        "name": "Stability / Overall Experience",
        "weight": 0.12,
        "description": "Checks consistency of style, pacing, difficulty, and viewer usefulness.",
        "checkpoints": [
            "The whole video keeps a coherent style, difficulty level, and explanation rhythm.",
            "The presentation does not degrade, contradict itself, or lose the audience halfway.",
            "The viewer can leave with a useful understanding of the topic.",
        ],
        "high_signals": ["consistent style", "stable pacing", "coherent story", "viewer value"],
        "low_signals": [
            "quality drift",
            "contradictions",
            "abrupt difficulty changes",
            "confusing arc",
        ],
    },
    {
        "id": "actionable_revision_quality",
        "name": "Actionable Revision Quality",
        "weight": 0.10,
        "description": "Checks whether the evaluator returns concrete next-step fixes.",
        "checkpoints": [
            "Problems are localized to slides, timestamps, subtitles, frames, or modules.",
            "Revision advice can be used directly by the next generation pass.",
            "Feedback separates critical blockers from nice-to-have improvements.",
        ],
        "high_signals": ["specific fixes", "module-level advice", "prioritized bottlenecks"],
        "low_signals": ["generic comments", "no evidence", "unclear next action"],
    },
]

DATASET_MAPPING = [
    {
        "name": "PresentEval",
        "url": "https://huggingface.co/datasets/AIGeeksGroup/PresentEval",
        "best_for": [
            "end-to-end narrated presentation video evaluation",
            "research/retrieval/content delivery quality",
            "PPT-video task realism",
        ],
        "use_in_prompt": (
            "Use as the closest benchmark family for whether a generated narrated "
            "presentation satisfies the user's open-ended request."
        ),
    },
    {
        "name": "PresentBench",
        "url": "https://huggingface.co/datasets/lynnzuo/PresentBench",
        "best_for": [
            "fine-grained slide checklist design",
            "coverage and factual grounding",
            "slide-level verifiable criteria",
        ],
        "use_in_prompt": (
            "Use to make slide visual/content scoring checklist-like instead of vague."
        ),
    },
    {
        "name": "Slides-Align",
        "url": "https://huggingface.co/datasets/Yqy6/Slides-Align",
        "best_for": [
            "human preference over generated slide decks",
            "visual/document design preference anchors",
            "reward-model-style high/low comparisons",
        ],
        "use_in_prompt": "Use to calibrate what a preferred slide deck looks like.",
    },
    {
        "name": "AIGVE-Bench",
        "url": "https://huggingface.co/datasets/xiaoliux/AIGVE-Bench",
        "best_for": [
            "AI-generated video quality dimensions",
            "human-scored video artifacts",
            "visual/audio/general video quality comments",
        ],
        "use_in_prompt": "Use to supplement video quality and multi-aspect comment standards.",
    },
    {
        "name": "DirectorBench",
        "url": "https://github.com/jiaminchen-1031/DirectorBench",
        "best_for": [
            "multi-agent diagnostic evaluation architecture",
            "checkpoint-level bottleneck reporting",
            "profile-aware weighting",
        ],
        "use_in_prompt": (
            "Use the method and output structure, not the film-specific metrics verbatim."
        ),
    },
]

MAX_ARTIFACT_TEXT_CHARS = 24000
MAX_ARTIFACT_JSON_BYTES = 2_000_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_from_model(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _call_openai_compatible(prompt: str) -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    import httpx

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    timeout = float(os.environ.get("AUTO_VIDEO_API_TIMEOUT", "60"))
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You produce concise JSON for a PPT/video prompt-based evaluation system."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": int(os.environ.get("AUTO_VIDEO_EVAL_MAX_TOKENS", "6000")),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = str(message.get("content") or "")
        if content.strip():
            return content
        return str(message.get("reasoning_content") or "")
    except Exception:
        return None


BUILTIN_CALIBRATION_EXAMPLES = [
    {
        "id": "builtin_high_grounded_clear",
        "label": "high",
        "score": 8.8,
        "summary": (
            "A PPT explanation video with a clear motivation-method-evidence-limitation arc."
        ),
        "transcript": (
            "The presenter explains why the problem matters, defines the core idea, "
            "walks through the workflow, and ties claims back to visible slide evidence."
        ),
        "slides": [
            "Motivation: concrete problem and audience need.",
            "Workflow: ingest, build slides, narrate, align visual focus, judge and revise.",
        ],
        "strengths": [
            "Narration matches the active slide.",
            "Claims are grounded in the provided source or visible slide content.",
            "Feedback is specific enough to drive another generation pass.",
        ],
        "weaknesses": ["Audio/video inspection may need real frames and transcript."],
        "why": (
            "This is high quality because it is useful to the viewer, grounded, aligned, "
            "and easy to improve further."
        ),
    },
    {
        "id": "builtin_low_misaligned_vague",
        "label": "low",
        "score": 3.0,
        "summary": (
            "A PPT explanation video with generic slides and narration that does not match "
            "what is currently on screen."
        ),
        "transcript": (
            "The presenter makes broad claims about performance and deployment without "
            "showing evidence, definitions, or a coherent workflow."
        ),
        "slides": ["Overview: AI system.", "Results: it works well."],
        "strengths": ["The deck has a minimal structure."],
        "weaknesses": [
            "Narration discusses absent content.",
            "Important claims have no evidence.",
            "The comments do not tell the generator what to fix next.",
        ],
        "why": (
            "This is low quality because visual polish cannot compensate for weak grounding, "
            "unclear explanation, and slide-narration mismatch."
        ),
    },
]


def load_calibration_examples(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return [dict(item) for item in BUILTIN_CALIBRATION_EXAMPLES]
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        examples = data
    elif isinstance(data, dict) and isinstance(data.get("examples"), list):
        examples = data["examples"]
    else:
        raise ValueError("Calibration file must be a JSON list or an object with an examples list.")
    cleaned: list[dict[str, Any]] = []
    for i, item in enumerate(examples, start=1):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("quality") or "").lower()
        score = item.get("score")
        cleaned.append(
            {
                "id": str(item.get("id") or f"example_{i:03d}"),
                "label": label or _label_from_score(score),
                "score": score,
                "summary": str(item.get("summary") or item.get("input_summary") or "")[:1200],
                "transcript": str(item.get("transcript") or item.get("narration") or "")[:4000],
                "slides": item.get("slides") if isinstance(item.get("slides"), list) else [],
                "strengths": _string_list(item.get("strengths")),
                "weaknesses": _string_list(item.get("weaknesses")),
                "why": str(
                    item.get("why") or item.get("rationale") or item.get("comment") or ""
                )[:2000],
            }
        )
    if not cleaned:
        raise ValueError("Calibration file did not contain any usable examples.")
    return cleaned


def _label_from_score(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "unlabeled"
    if value <= 1.0:
        if value >= 0.8:
            return "high"
        if value <= 0.4:
            return "low"
        return "medium"
    if value <= 5.0:
        if value >= 4.0:
            return "high"
        if value <= 2.0:
            return "low"
        return "medium"
    if value >= 8.0:
        return "high"
    if value <= 4.0:
        return "low"
    return "medium"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:300] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value[:300]]
    return []


def _read_text_limited(path: Path, *, max_chars: int = MAX_ARTIFACT_TEXT_CHARS) -> str:
    with path.open("rb") as f:
        data = f.read(max_chars * 4)
    return data.decode("utf-8", errors="ignore")[:max_chars]


def learn_user_rubric(
    examples: list[dict[str, Any]],
    *,
    use_api: bool,
    extra_standard: str = "",
) -> dict[str, Any]:
    fallback = _fallback_rubric(examples, extra_standard=extra_standard)
    if not use_api:
        return fallback
    prompt = textwrap.dedent(
        f"""
        You are designing a prompt-based evaluator for PPT explanation videos.
        Infer the user's scoring standard from labeled examples. This is prompt calibration,
        not model training. Produce a reusable rubric that a multimodal LLM can apply.

        Adapt the DirectorBench idea to PPT explanation videos:
        - checkpoint-level diagnosis, not only an aggregate score
        - specialist dimensions for content/script, slide visuals, audio, cross-modal
          alignment, stability/experience, and actionable revision quality
        - profile-aware weighting when user preferences are provided
        - evidence-backed bottleneck reporting

        Return JSON only:
        {{
          "score_scale": "0-10",
          "classification_thresholds": {{
            "excellent": ">= 8.5",
            "good": ">= 7.0 and < 8.5",
            "medium": ">= 5.5 and < 7.0",
            "weak": ">= 4.0 and < 5.5",
            "poor": "< 4.0"
          }},
          "decision_boundary": {{
            "excellent": "...",
            "good": "...",
            "medium": "...",
            "weak": "...",
            "poor": "..."
          }},
          "dimensions": [
            {{
              "id": "snake_case",
              "name": "...",
              "weight": 0.0,
              "description": "...",
              "checkpoints": ["..."],
              "high_signals": ["..."],
              "low_signals": ["..."]
            }}
          ],
          "non_negotiables": ["..."],
          "judge_style": "...",
          "user_preference_hypothesis": {{
            "what_the_user_seems_to_like": ["..."],
            "what_the_user_seems_to_dislike": ["..."],
            "missing_examples_needed": ["..."]
          }}
        }}

        Extra user standard:
        {extra_standard or "(none)"}

        Labeled examples:
        {json.dumps(examples, ensure_ascii=False)[:30000]}
        """
    ).strip()
    data = _json_from_model(_call_openai_compatible(prompt))
    if not isinstance(data, dict):
        return fallback
    dimensions = data.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        data["dimensions"] = fallback["dimensions"]
    data.setdefault("score_scale", "0-10")
    data.setdefault("classification_thresholds", fallback["classification_thresholds"])
    data.setdefault("decision_boundary", fallback["decision_boundary"])
    data.setdefault("non_negotiables", fallback["non_negotiables"])
    data.setdefault("judge_style", fallback["judge_style"])
    data.setdefault("user_preference_hypothesis", fallback["user_preference_hypothesis"])
    data["learned_from_examples"] = len(examples)
    data["rubric_mode"] = "api_learned"
    return data


def _fallback_rubric(examples: list[dict[str, Any]], *, extra_standard: str) -> dict[str, Any]:
    high = [e for e in examples if e.get("label") == "high"]
    low = [e for e in examples if e.get("label") == "low"]
    non_negotiables = [
        "Every score must cite concrete evidence from slides, transcript, frames, or timestamps.",
        "Do not reward a polished video if the content is wrong or not aligned with the slides.",
        "Give revision advice that can be acted on in the next generation pass.",
    ]
    if extra_standard.strip():
        non_negotiables.append(extra_standard.strip()[:500])
    return {
        "score_scale": "0-10",
        "classification_thresholds": {
            "excellent": ">= 8.5",
            "good": ">= 7.0 and < 8.5",
            "medium": ">= 5.5 and < 7.0",
            "weak": ">= 4.0 and < 5.5",
            "poor": "< 4.0",
        },
        "decision_boundary": {
            "excellent": (
                "Content is correct, slides are readable, narration is clear, alignment is strong, "
                "and the viewer gets real value."
            ),
            "good": (
                "Strong presentation with minor issues that do not block comprehension."
            ),
            "medium": (
                "Understandable but has noticeable gaps in grounding, pacing, visuals, "
                "or alignment."
            ),
            "weak": (
                "Significant issues reduce trust or make the explanation hard to follow."
            ),
            "poor": (
                "Fundamental problems in content, slide readability, narration, or synchronization."
            ),
        },
        "dimensions": DEFAULT_DIMENSIONS,
        "non_negotiables": non_negotiables,
        "judge_style": (
            "Strict but constructive; prefer evidence-backed criticism over generic praise."
        ),
        "user_preference_hypothesis": {
            "what_the_user_seems_to_like": [
                "clear explanations grounded in source material",
                "PPT pages that match the spoken content",
                "specific revision advice for the next generation pass",
            ],
            "what_the_user_seems_to_dislike": [
                "empty polish without substance",
                "narration that does not match the slide",
                "generic feedback without concrete fixes",
            ],
            "missing_examples_needed": [
                "at least one user-rated 8-10 video",
                "at least one user-rated 4-6 video",
                "at least one user-rated 0-3 video with reasons",
            ],
        },
        "learned_from_examples": len(examples),
        "label_counts": {"high": len(high), "low": len(low), "total": len(examples)},
        "rubric_mode": "fallback_from_examples",
    }


def load_artifact_context(
    artifact_dir: Path,
    *,
    transcript_path: Path | None = None,
) -> dict[str, Any]:
    files = {
        "source": "source.json",
        "storyboard": "storyboard.json",
        "metrics": "metrics.json",
        "judge_feedback": "judge_feedback.json",
        "slides_markdown": "slides.md",
        "subtitles_srt": "subtitles.srt",
        "cursor_plan": "cursor_plan.json",
        "talker_plan": "talker_plan.json",
    }
    context: dict[str, Any] = {
        "artifact_dir": str(artifact_dir.resolve()),
        "available_files": [],
        "missing_files": [],
    }
    for key, filename in files.items():
        path = artifact_dir / filename
        if not path.is_file():
            context["missing_files"].append(filename)
            continue
        context["available_files"].append(filename)
        if path.suffix == ".json":
            if path.stat().st_size > MAX_ARTIFACT_JSON_BYTES:
                context[key] = {
                    "truncated_text": _read_text_limited(path),
                    "note": "Large JSON artifact was truncated for evaluator prompt context.",
                }
                continue
            try:
                context[key] = json.loads(
                    _read_text_limited(path, max_chars=MAX_ARTIFACT_JSON_BYTES)
                )
            except json.JSONDecodeError:
                context[key] = _read_text_limited(path)
        else:
            context[key] = _read_text_limited(path)
    if transcript_path and transcript_path.is_file():
        context["external_transcript"] = transcript_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )[:24000]
    video_path = artifact_dir / "video.mp4"
    if video_path.is_file():
        context["video_file"] = str(video_path.resolve())
    return context


def build_system_prompt(rubric: dict[str, Any]) -> str:
    return textwrap.dedent(
        f"""
        You are a strict multimodal evaluator for PPT explanation videos.

        Your evaluation style is adapted from DirectorBench:
        - Diagnose checkpoint-level bottlenecks instead of only giving one total score.
        - Use specialist dimensions: content/script, slide visuals, audio/narration,
          cross-modal alignment, stability/overall experience, and actionable revisions.
        - Weight the result using the provided user profile or calibration examples when available.
        - Every score must cite concrete evidence from source text, slide screenshots, storyboard,
          video frames, subtitles, ASR transcript, audio metadata, or timestamps.
        - If an input modality is missing, lower confidence for affected dimensions and say so.

        Scoring standard:
        {json.dumps(rubric, ensure_ascii=False, indent=2)}

        High scores require real viewer value: correct content, clear explanation, readable PPT,
        strong slide-narration alignment, and concrete revision advice. Visual polish alone is
        not enough.

        Return JSON only. Do not include Markdown, explanations outside JSON, or extra keys.
        """
    ).strip()


def build_user_input_template() -> str:
    return textwrap.dedent(
        """
        Evaluate this PPT explanation video.

        User goal / topic:
        {{user_goal_or_topic}}

        Source material:
        {{source_material_or_summary}}

        PPT / slide material:
        {{slide_text_or_storyboard}}

        Video evidence:
        {{video_file_path_or_sampled_frames}}

        ASR transcript / subtitles:
        {{transcript_or_srt}}

        Audio / timing metadata:
        {{duration_speed_volume_or_missing}}

        User preference profile:
        {{optional_user_preference_profile}}

        Calibration examples:
        {{optional_high_medium_low_examples}}
        """
    ).strip()


def build_calibration_example_template() -> str:
    return textwrap.dedent(
        """
        {
          "examples": [
            {
              "id": "video_a_user_8",
              "label": "high",
              "score": 8.0,
              "summary": "What this PPT/video is about.",
              "transcript": "Important transcript excerpts or ASR text.",
              "slides": ["Slide 1 summary", "Slide 2 summary"],
              "strengths": ["Why the user likes it"],
              "weaknesses": ["Remaining issues"],
              "why": "The user's reason for giving this score."
            },
            {
              "id": "video_b_user_4",
              "label": "weak",
              "score": 4.0,
              "summary": "What this PPT/video is about.",
              "transcript": "Important transcript excerpts or ASR text.",
              "slides": ["Slide 1 summary", "Slide 2 summary"],
              "strengths": ["Any parts that still work"],
              "weaknesses": ["Why the user dislikes it"],
              "why": "The user's reason for giving this score."
            }
          ]
        }
        """
    ).strip()


def build_preference_update_process() -> list[str]:
    return [
        (
            "Collect user-rated PPT/video examples with score, label, transcript excerpts, "
            "slide summaries, and reasons."
        ),
        (
            "Normalize mixed score scales into 0-10 while preserving the original user "
            "score in the example."
        ),
        (
            "Compare high-rated and low-rated cases to infer preference signals, dislikes, "
            "and non-negotiables."
        ),
        "Adjust dimension weights only when repeated examples show a stable preference pattern.",
        (
            "Add new preference hypotheses to the evaluator prompt, but keep evidence and "
            "confidence requirements."
        ),
        (
            "Re-score a small holdout set after each prompt change and keep changes only "
            "if ranking improves."
        ),
    ]


def build_prompt_package(rubric: dict[str, Any]) -> dict[str, Any]:
    return {
        "system_prompt": build_system_prompt(rubric),
        "user_input_template": build_user_input_template(),
        "calibration_example_template": build_calibration_example_template(),
        "preference_update_process": build_preference_update_process(),
        "dataset_mapping": DATASET_MAPPING,
    }


def _truncate_text(value: Any, limit: int = 900) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def summarize_artifact_context(artifact_context: dict[str, Any]) -> dict[str, Any]:
    source = (
        artifact_context.get("source")
        if isinstance(artifact_context.get("source"), dict)
        else {}
    )
    storyboard = (
        artifact_context.get("storyboard")
        if isinstance(artifact_context.get("storyboard"), dict)
        else {}
    )
    metrics = (
        artifact_context.get("metrics")
        if isinstance(artifact_context.get("metrics"), dict)
        else {}
    )
    judge = (
        artifact_context.get("judge_feedback")
        if isinstance(artifact_context.get("judge_feedback"), dict)
        else {}
    )
    slides = storyboard.get("slides") if isinstance(storyboard.get("slides"), list) else []
    subtitles = storyboard.get("subtitles") if isinstance(storyboard.get("subtitles"), list) else []
    cursor_plan = (
        storyboard.get("cursor_plan") if isinstance(storyboard.get("cursor_plan"), list) else []
    )
    slide_summaries: list[dict[str, Any]] = []
    for slide in slides[:12]:
        if not isinstance(slide, dict):
            continue
        slide_summaries.append(
            {
                "index": slide.get("index"),
                "title": _truncate_text(slide.get("title"), 160),
                "purpose": _truncate_text(slide.get("purpose"), 220),
                "bullets": [_truncate_text(item, 220) for item in (slide.get("bullets") or [])[:4]],
                "speaker_note": _truncate_text(slide.get("speaker_note"), 700),
                "visual_kind": slide.get("visual_kind"),
                "visual_caption": _truncate_text(slide.get("visual_caption"), 220),
            }
        )
    subtitle_samples = [
        {
            "slide_index": item.get("slide_index"),
            "start_sec": item.get("start_sec"),
            "end_sec": item.get("end_sec"),
            "text": _truncate_text(item.get("text"), 260),
        }
        for item in subtitles[:24]
        if isinstance(item, dict)
    ]
    return {
        "artifact_dir": artifact_context.get("artifact_dir"),
        "available_files": artifact_context.get("available_files", []),
        "missing_files": artifact_context.get("missing_files", []),
        "video_file": artifact_context.get("video_file", ""),
        "source": {
            "kind": source.get("kind"),
            "title": _truncate_text(source.get("title"), 220),
            "source_path": source.get("source_path"),
            "text_excerpt": _truncate_text(source.get("text"), 1400),
        },
        "metrics": {
            "video_rendered": metrics.get("video_rendered"),
            "video_path": metrics.get("video_path"),
            "slide_count": metrics.get("slide_count"),
            "subtitle_count": metrics.get("subtitle_count"),
            "estimated_duration_sec": metrics.get("estimated_duration_sec"),
            "judge_overall_score": metrics.get("judge_overall_score"),
            "target_score": metrics.get("target_score"),
            "satisfied": metrics.get("satisfied"),
            "audio_muxed": metrics.get("audio_muxed"),
            "tts_requested": metrics.get("tts_requested"),
            "tts_ok": metrics.get("tts_ok"),
            "image_api_requested": metrics.get("image_api_requested"),
            "image_generation_ok": metrics.get("image_generation_ok"),
            "vlm_cursor_points": metrics.get("vlm_cursor_points"),
        },
        "previous_pipeline_judge": {
            "overall_score": judge.get("overall_score"),
            "module_scores": judge.get("module_scores"),
            "failed_modules": judge.get("failed_modules"),
            "revise_next": judge.get("revise_next"),
        },
        "slides": slide_summaries,
        "subtitle_samples": subtitle_samples,
        "cursor_sample_count": len(cursor_plan),
        "transcript_excerpt": _truncate_text(artifact_context.get("external_transcript"), 1800),
        "modality_note": (
            "This prompt evaluates available artifacts. If real video frames/audio are not "
            "provided to the model, visual and audio scores must use lower confidence."
        ),
    }


def build_judge_prompt(
    rubric: dict[str, Any],
    examples: list[dict[str, Any]],
    artifact_context: dict[str, Any],
) -> str:
    compact_examples = [
        {
            "id": e["id"],
            "label": e["label"],
            "score": e.get("score"),
            "summary": e.get("summary"),
            "strengths": e.get("strengths", [])[:3],
            "weaknesses": e.get("weaknesses", [])[:3],
            "why": e.get("why", "")[:700],
        }
        for e in examples[:12]
    ]
    prompt_package = build_prompt_package(rubric)
    summarized_context = summarize_artifact_context(artifact_context)
    return textwrap.dedent(
        f"""
        SYSTEM PROMPT:
        {prompt_package["system_prompt"]}

        USER TASK:
        Evaluate the target PPT/video artifact according to the user's learned standard.
        Use calibration examples as preference anchors, not as content to copy.

        User-learned rubric:
        {json.dumps(rubric, ensure_ascii=False, indent=2)}

        Calibration anchors:
        {json.dumps(compact_examples, ensure_ascii=False, indent=2)}

        Target artifact summary:
        {json.dumps(summarized_context, ensure_ascii=False, indent=2)}

        If actual video frames or audio are not provided, clearly mark those dimensions as
        lower-confidence instead of pretending you inspected them.

        Return JSON only:
        {{
          "overall_score": 0,
          "confidence": 0.0,
          "classification": "excellent|good|medium|weak|poor",
          "dimension_scores": {{
            "content_script_quality": {{
              "score": 0,
              "confidence": 0.0,
              "evidence": [],
              "problems": [],
              "revision_advice": []
            }},
            "slide_visual_quality": {{
              "score": 0,
              "confidence": 0.0,
              "evidence": [],
              "problems": [],
              "revision_advice": []
            }},
            "audio_narration_quality": {{
              "score": 0,
              "confidence": 0.0,
              "evidence": [],
              "problems": [],
              "revision_advice": []
            }},
            "cross_modal_alignment": {{
              "score": 0,
              "confidence": 0.0,
              "evidence": [],
              "problems": [],
              "revision_advice": []
            }},
            "stability_overall_experience": {{
              "score": 0,
              "confidence": 0.0,
              "evidence": [],
              "problems": [],
              "revision_advice": []
            }},
            "actionable_revision_quality": {{
              "score": 0,
              "confidence": 0.0,
              "evidence": [],
              "problems": [],
              "revision_advice": []
            }}
          }},
          "major_bottlenecks": [],
          "highest_priority_fixes": [],
          "prompt_improvement_suggestions": [],
          "user_preference_inference": {{
            "what_the_user_seems_to_like": [],
            "what_the_user_seems_to_dislike": [],
            "missing_examples_needed": []
          }}
        }}
        """
    ).strip()


def evaluate_with_prompt(
    prompt: str,
    *,
    use_api: bool,
) -> dict[str, Any]:
    if not use_api:
        return {
            "overall_score": None,
            "confidence": 0.0,
            "classification": "not_run",
            "dimension_scores": {},
            "major_bottlenecks": [],
            "highest_priority_fixes": [
                "Run with --use-api and OPENAI_API_KEY to let the configured large model score it.",
            ],
            "prompt_improvement_suggestions": [
                "Add more labeled high/low examples from your own PPT videos.",
                "Include transcript and sampled video frames for stronger multimodal judgment.",
            ],
            "user_preference_inference": {
                "what_the_user_seems_to_like": [],
                "what_the_user_seems_to_dislike": [],
                "missing_examples_needed": [
                    "user-rated 8-10 example",
                    "user-rated 4-6 example",
                    "user-rated 0-3 example",
                ],
            },
        }
    raw_response = _call_openai_compatible(prompt)
    data = _json_from_model(raw_response)
    if isinstance(data, dict):
        return data
    return {
        "overall_score": None,
        "confidence": 0.0,
        "classification": "model_parse_failed",
        "dimension_scores": {},
        "major_bottlenecks": ["The model response was not valid JSON."],
        "highest_priority_fixes": [
            "Retry with a smaller artifact context or stricter JSON instruction."
        ],
        "prompt_improvement_suggestions": ["Shorten calibration examples and target context."],
        "user_preference_inference": {
            "what_the_user_seems_to_like": [],
            "what_the_user_seems_to_dislike": [],
            "missing_examples_needed": [],
        },
        "raw_response_excerpt": _truncate_text(raw_response, 2000),
    }


def _classification(score: float) -> str:
    if score >= 8.5:
        return "excellent"
    if score >= 7.0:
        return "good"
    if score >= 5.5:
        return "medium"
    if score >= 3.5:
        return "weak"
    return "poor"


def fallback_artifact_evaluation(artifact_context: dict[str, Any], *, reason: str) -> dict[str, Any]:
    summary = summarize_artifact_context(artifact_context)
    metrics = summary.get("metrics", {}) if isinstance(summary.get("metrics"), dict) else {}
    slides = summary.get("slides", []) if isinstance(summary.get("slides"), list) else []
    subtitles = summary.get("subtitle_samples", []) if isinstance(summary.get("subtitle_samples"), list) else []
    slide_count = int(metrics.get("slide_count") or len(slides) or 0)
    subtitle_count = int(metrics.get("subtitle_count") or len(subtitles) or 0)
    has_audio = bool(metrics.get("audio_muxed") or metrics.get("audio_stream_present"))
    video_rendered = bool(metrics.get("video_rendered") or summary.get("video_file"))
    titles = [str(slide.get("title") or "") for slide in slides if isinstance(slide, dict)]
    title_diversity = len(set(titles)) / max(1, len(titles))
    score = 4.5
    if video_rendered:
        score += 0.8
    if has_audio:
        score += 0.9
    if 6 <= slide_count <= 12:
        score += 0.7
    if subtitle_count >= slide_count:
        score += 0.5
    if title_diversity > 0.8:
        score += 0.4
    score = round(max(0.0, min(10.0, score)), 1)

    def dimension(value: float, evidence: list[str], problems: list[str], advice: list[str]) -> dict[str, Any]:
        return {
            "score": round(max(0.0, min(10.0, value)), 1),
            "confidence": 0.35,
            "evidence": evidence,
            "problems": problems,
            "revision_advice": advice,
        }

    return {
        "overall_score": score,
        "confidence": 0.35,
        "classification": _classification(score),
        "dimension_scores": {
            "content_script_quality": dimension(
                score,
                [f"Fallback evaluated {slide_count} slides and {subtitle_count} subtitle items."],
                ["Model evaluator failed, so content quality was not deeply judged."],
                ["Retry API evaluation with compact context for more reliable content diagnosis."],
            ),
            "slide_visual_quality": dimension(
                score - 0.3,
                [f"Detected {slide_count} slide records in storyboard."],
                ["Visual quality confidence is low without direct frame inspection."],
                ["Sample rendered frames or screenshots for a stronger visual evaluation."],
            ),
            "audio_narration_quality": dimension(
                7.0 if has_audio else 3.0,
                ["Audio stream appears present." if has_audio else "No confirmed audio stream in metrics."],
                [] if has_audio else ["Audio mux or TTS may have failed."],
                ["Verify playback in Finder/QuickTime and keep ffprobe audio checks in the pipeline."],
            ),
            "cross_modal_alignment": dimension(
                score - 0.6,
                ["Subtitle and slide artifacts are both present."],
                ["Fallback cannot verify frame-level alignment."],
                ["Use sampled video frames plus subtitle timestamps for alignment scoring."],
            ),
            "stability_overall_experience": dimension(
                score,
                ["Video artifact was rendered." if video_rendered else "No rendered video confirmed."],
                ["Fallback confidence is limited because the model evaluator failed."],
                ["Keep the last valid model evaluation if a later retry fails."],
            ),
            "actionable_revision_quality": dimension(
                5.0,
                ["Fallback generated generic repair suggestions."],
                ["Advice is less specific than model-based diagnosis."],
                ["Rerun prompt evaluation after reducing context size."],
            ),
        },
        "major_bottlenecks": [reason, "Fallback scoring was used because model evaluation failed."],
        "highest_priority_fixes": [
            "Keep the last valid model evaluation instead of overwriting it with a failed retry.",
            "Retry evaluator with a smaller artifact context or later API call.",
        ],
        "prompt_improvement_suggestions": [
            "Use compact artifact context on retry.",
            "Ask for strict JSON and preserve previous valid reports.",
        ],
        "user_preference_inference": {
            "what_the_user_seems_to_like": [],
            "what_the_user_seems_to_dislike": [],
            "missing_examples_needed": [],
        },
        "fallback_reason": reason,
    }


def run_prompt_evaluation(
    examples_path: Path | None,
    artifact_dir: Path,
    *,
    out_path: Path,
    use_api: bool,
    transcript_path: Path | None = None,
    extra_standard: str = "",
) -> dict[str, Any]:
    examples = load_calibration_examples(examples_path)
    rubric = learn_user_rubric(examples, use_api=use_api, extra_standard=extra_standard)
    artifact_context = load_artifact_context(artifact_dir, transcript_path=transcript_path)
    prompt = build_judge_prompt(rubric, examples, artifact_context)
    prompt_package = build_prompt_package(rubric)
    evaluation = evaluate_with_prompt(prompt, use_api=use_api)
    if evaluation.get("classification") == "model_parse_failed":
        evaluation = fallback_artifact_evaluation(
            artifact_context,
            reason="Model evaluator returned empty or invalid JSON.",
        )
    report = {
        "created_at": _utc_now(),
        "examples_path": str(examples_path.resolve()) if examples_path else "builtin",
        "artifact_dir": str(artifact_dir.resolve()),
        "use_api": use_api,
        "learned_rubric": rubric,
        "prompt_package": prompt_package,
        "evaluation": evaluation,
        "judge_prompt": prompt,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
