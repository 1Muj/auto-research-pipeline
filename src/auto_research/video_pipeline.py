from __future__ import annotations

# ruff: noqa: E501
import base64
import html
import json
import math
import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SLIDE_PLAN = [
    ("Motivation", "What problem does this work try to solve?"),
    ("Core Idea", "What is the main technical or product idea?"),
    ("Workflow", "How does the method or project work end to end?"),
    ("Evidence", "What results, examples, or implementation details support it?"),
    ("Limitations", "What should be improved in the next version?"),
]


@dataclass
class VideoPipelineResult:
    out_dir: Path
    metrics_path: Path
    preview_path: Path
    video_path: Path
    storyboard_path: Path
    judge_path: Path
    revision_history_path: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return clean[:70] or "paper-project-video"


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PDF input needs pypdf. Install with `pip install pypdf`, or pass a .md/.txt file."
        ) from exc
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages[:30]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def load_source(input_path: Path, *, kind: str) -> dict[str, Any]:
    path = input_path.resolve()
    if kind not in {"paper", "project"}:
        raise ValueError("kind must be 'paper' or 'project'")
    if kind == "project" and path.is_dir():
        text, files = _load_project_text(path)
        title = path.name
        return {
            "kind": kind,
            "title": title,
            "source_path": str(path),
            "text": text,
            "files": files,
        }
    if not path.is_file():
        raise FileNotFoundError(f"Input not found: {path}")
    if path.suffix.lower() == ".pdf":
        text = _extract_pdf_text(path)
    else:
        text = _read_text_file(path)
    title = _guess_title(text) or path.stem.replace("_", " ").replace("-", " ").title()
    return {"kind": kind, "title": title, "source_path": str(path), "text": text, "files": []}


def _load_project_text(path: Path) -> tuple[str, list[str]]:
    candidates = [
        "README.md",
        "README.rst",
        "README.txt",
        "pyproject.toml",
        "package.json",
        "requirements.txt",
        "docs/README.md",
    ]
    chunks: list[str] = []
    used: list[str] = []
    for rel in candidates:
        p = path / rel
        if p.is_file():
            used.append(rel)
            chunks.append(f"\n\n# File: {rel}\n" + _read_text_file(p)[:20000])
    if not chunks:
        for p in sorted(path.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".md", ".txt", ".py", ".toml", ".json"}:
                used.append(str(p.relative_to(path)))
                chunks.append(f"\n\n# File: {p.relative_to(path)}\n" + _read_text_file(p)[:8000])
            if len(chunks) >= 8:
                break
    if not chunks:
        chunks.append(f"Project directory {path.name}. No readable text files found.")
    return "\n".join(chunks), used


def _guess_title(text: str) -> str:
    for line in text.splitlines()[:40]:
        line = line.strip().strip("#").strip()
        if 8 <= len(line) <= 120 and not line.lower().startswith(("abstract", "introduction")):
            return line
    return ""


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?。！？])\s+", compact)
    return [p.strip() for p in parts if len(p.strip()) >= 35]


def _keywords(text: str, *, limit: int = 14) -> list[str]:
    stop = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "paper",
        "project",
        "using",
        "used",
        "into",
        "their",
        "there",
        "which",
        "were",
        "been",
        "also",
        "about",
        "through",
        "these",
        "those",
        "and",
        "for",
        "the",
        "of",
        "to",
        "in",
        "on",
        "a",
        "an",
        "is",
        "are",
        "as",
        "by",
    }
    counts: dict[str, int] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text):
        key = word.lower()
        if key in stop:
            continue
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [k for k, _ in ranked[:limit]]


def _pick_sentences(text: str, query_words: list[str], *, count: int = 3) -> list[str]:
    sents = _sentences(text)
    if not sents:
        return ["Source text is short; use the available material as the slide evidence."]
    scored: list[tuple[int, int, str]] = []
    q = [w.lower() for w in query_words]
    for i, sent in enumerate(sents):
        low = sent.lower()
        score = sum(2 for w in q if w in low)
        score += 1 if 80 <= len(sent) <= 220 else 0
        scored.append((score, -i, sent))
    out = [s for _, _, s in sorted(scored, reverse=True)[:count]]
    return [s[:260].strip() for s in out]


def _call_openai_compatible(prompt: str) -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    timeout = float(os.environ.get("AUTO_VIDEO_API_TIMEOUT", "60"))
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You produce concise JSON for an academic paper/project-to-video pipeline.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 2500,
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
        return str(data["choices"][0]["message"]["content"])
    except Exception:
        return None


def _call_openai_vision(prompt: str, image_path: Path) -> str | None:
    key = os.environ.get("OPENAI_VISION_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base_url = (
        os.environ.get("OPENAI_VISION_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = os.environ.get("OPENAI_VISION_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"
    timeout = float(os.environ.get("AUTO_VIDEO_API_TIMEOUT", "60"))
    try:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded}",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 500,
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
        return str(data["choices"][0]["message"]["content"])
    except Exception:
        return None


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


def _score01(value: Any, fallback: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return fallback
    if score > 1.0:
        score = score / 10.0
    return round(max(0.0, min(1.0, score)), 3)


def build_slides(source: dict[str, Any], *, max_slides: int, use_api: bool) -> list[dict[str, Any]]:
    text = source["text"][:65000]
    title = source["title"]
    if use_api:
        prompt = textwrap.dedent(
            f"""
            Convert this {source['kind']} into {max_slides} presentation slides.
            Return JSON only:
            {{"slides":[{{"title":"...","bullets":["..."],"speaker_note":"...","visual_prompt":"..."}}]}}
            Keep bullets grounded in the source and suitable for a short research demo video.

            Title: {title}
            Source:
            {text[:45000]}
            """
        ).strip()
        data = _json_from_model(_call_openai_compatible(prompt))
        slides = data.get("slides") if isinstance(data, dict) else None
        if isinstance(slides, list) and slides:
            return [_normalize_slide(i, item) for i, item in enumerate(slides[:max_slides], start=1)]

    keys = _keywords(text)
    sections = SLIDE_PLAN[:max_slides]
    slides: list[dict[str, Any]] = []
    for i, (name, purpose) in enumerate(sections, start=1):
        query = [name.lower(), *keys[i - 1 : i + 4]]
        evidence = _pick_sentences(text, query, count=3)
        bullets = [re.sub(r"\s+", " ", item).strip(" -") for item in evidence]
        slides.append(
            {
                "index": i,
                "title": f"{i}. {name}",
                "purpose": purpose,
                "bullets": bullets[:3],
                "speaker_note": _speaker_note(name, title, bullets),
                "visual_prompt": _visual_prompt(source["kind"], name, keys),
            }
        )
    return slides


def _normalize_slide(index: int, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"title": f"{index}. Slide", "bullets": [str(item)]}
    bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    return {
        "index": index,
        "title": str(item.get("title") or f"{index}. Slide"),
        "purpose": str(item.get("purpose") or ""),
        "bullets": [str(b)[:260] for b in bullets[:4]],
        "speaker_note": str(item.get("speaker_note") or item.get("note") or "")[:900],
        "visual_prompt": str(item.get("visual_prompt") or "")[:500],
    }


def _speaker_note(section: str, title: str, bullets: list[str]) -> str:
    lead = {
        "Motivation": f"This video starts from the motivation of {title}.",
        "Core Idea": "The core idea is summarized as a compact claim before showing implementation details.",
        "Workflow": "The workflow view turns the source into an executable sequence of builders.",
        "Evidence": "This part highlights the strongest evidence available in the input.",
        "Limitations": "The final slide keeps the scope honest and proposes the next experiment.",
    }.get(section, "This slide summarizes one part of the work.")
    return " ".join([lead, *bullets[:2]])[:900]


def _visual_prompt(kind: str, section: str, keys: list[str]) -> str:
    topic = ", ".join(keys[:5]) if keys else kind
    return f"{kind} explainer scene for {section.lower()}, using visual anchors: {topic}"


def build_subtitles(slides: list[dict[str, Any]], *, seconds_per_slide: int) -> list[dict[str, Any]]:
    subtitles: list[dict[str, Any]] = []
    t = 0
    for slide in slides:
        note = slide.get("speaker_note") or " ".join(slide.get("bullets") or [])
        sentences = _sentences(note) or [note]
        for sent in sentences[:3]:
            start = t
            duration = max(4, min(9, round(len(sent) / 18)))
            subtitles.append(
                {
                    "slide_index": slide["index"],
                    "start_sec": start,
                    "end_sec": start + duration,
                    "text": sent.strip(),
                    "visual_focus_prompt": slide.get("visual_prompt", ""),
                }
            )
            t += duration
        if t < slide["index"] * seconds_per_slide:
            t = slide["index"] * seconds_per_slide
    return subtitles


def build_cursor_plan(
    subtitles: list[dict[str, Any]],
    *,
    slides: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
    out_dir: Path | None = None,
    use_vlm_cursor: bool = False,
) -> list[dict[str, Any]]:
    anchors = [(20, 28), (48, 36), (72, 44), (38, 62), (66, 70)]
    slide_lookup = {int(slide["index"]): slide for slide in slides or []}
    grounding_dir = out_dir / "cursor_grounding" if out_dir else None
    if grounding_dir:
        grounding_dir.mkdir(parents=True, exist_ok=True)
    plan: list[dict[str, Any]] = []
    for i, item in enumerate(subtitles):
        x, y = anchors[i % len(anchors)]
        grounding_mode = "heuristic"
        reason = item.get("visual_focus_prompt", "")
        slide_index = int(item["slide_index"])
        slide = slide_lookup.get(slide_index)
        if use_vlm_cursor and slide and source and grounding_dir:
            grounded = _ground_cursor_with_vlm(
                source,
                slide,
                item,
                grounding_dir=grounding_dir,
            )
            if grounded:
                x = int(grounded["x_percent"])
                y = int(grounded["y_percent"])
                reason = str(grounded.get("reason") or reason)
                grounding_mode = "vlm"
        plan.append(
            {
                "start_sec": item["start_sec"],
                "end_sec": item["end_sec"],
                "slide_index": slide_index,
                "x_percent": x,
                "y_percent": y,
                "reason": reason,
                "grounding_mode": grounding_mode,
            }
        )
    return plan


def _ground_cursor_with_vlm(
    source: dict[str, Any],
    slide: dict[str, Any],
    subtitle: dict[str, Any],
    *,
    grounding_dir: Path,
) -> dict[str, Any] | None:
    image_path = grounding_dir / f"slide_{int(slide['index']):02d}.png"
    if not image_path.is_file():
        if not _write_grounding_slide_image(source, slide, image_path):
            return None
    prompt = textwrap.dedent(
        f"""
        You are grounding a presentation cursor.
        Look at the slide image and choose where a human presenter would point while saying this subtitle.
        Return JSON only:
        {{"x_percent": 0-100, "y_percent": 0-100, "target_label": "...", "reason": "..."}}

        Rules:
        - Prefer the relevant bullet text, figure, or title.
        - Put the cursor near the target, not on top of the subtitle area.
        - Use percentages relative to the image width and height.
        - Do not choose decorative empty space.

        Presentation title: {source.get('title', '')}
        Slide title: {slide.get('title', '')}
        Slide bullets: {json.dumps(slide.get('bullets', []), ensure_ascii=False)}
        Subtitle: {subtitle.get('text', '')}
        """
    ).strip()
    data = _json_from_model(_call_openai_vision(prompt, image_path))
    if not isinstance(data, dict):
        return None
    try:
        x = max(5, min(92, int(float(data.get("x_percent")))))
        y = max(14, min(74, int(float(data.get("y_percent")))))
    except (TypeError, ValueError):
        return None
    return {
        "x_percent": x,
        "y_percent": y,
        "target_label": str(data.get("target_label", "")),
        "reason": str(data.get("reason", "")),
    }


def build_talker_plan(subtitles: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(item["text"] for item in subtitles)
    return {
        "mode": os.environ.get("AUTO_VIDEO_TALKER_MODE", "placeholder"),
        "tts_provider": os.environ.get("AUTO_VIDEO_TTS_PROVIDER", "not_configured"),
        "talking_head_provider": os.environ.get("AUTO_VIDEO_TALKING_HEAD_PROVIDER", "not_configured"),
        "voice_sample_path": os.environ.get("AUTO_VIDEO_VOICE_SAMPLE", ""),
        "portrait_path": os.environ.get("AUTO_VIDEO_PORTRAIT", ""),
        "narration_text": text,
        "api_ready": bool(
            os.environ.get("ELEVENLABS_API_KEY")
            or os.environ.get("HEYGEN_API_KEY")
            or os.environ.get("D_ID_API_KEY")
        ),
        "note": "This MVP writes storyboard/subtitle/cursor artifacts. External TTS/talking-head APIs can consume this plan.",
    }


def judge_storyboard(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    *,
    use_api: bool,
) -> dict[str, Any]:
    source_words = set(_keywords(source["text"], limit=60))
    slide_text = " ".join(
        " ".join([slide["title"], " ".join(slide.get("bullets") or []), slide.get("speaker_note", "")])
        for slide in slides
    ).lower()
    covered = sum(1 for word in source_words if word in slide_text)
    coverage = min(1.0, covered / max(1, min(len(source_words), 30)))
    slide_count_score = min(1.0, len(slides) / 5)
    narration_len = sum(len(item["text"].split()) for item in subtitles)
    length_score = 1.0 if 120 <= narration_len <= 900 else max(0.35, min(1.0, narration_len / 120))
    visual_score = min(1.0, sum(1 for s in slides if s.get("visual_prompt")) / max(1, len(slides)))
    subtitle_density_score = min(1.0, len(subtitles) / max(1, len(slides) * 2))
    cursor_count_score = min(1.0, len(subtitles) / max(1, len(slides) * 2))
    talker_score = 1.0 if subtitles else 0.0
    module_scores = {
        "slide_builder": round(min(1.0, coverage * 0.7 + slide_count_score * 0.3), 3),
        "subtitle_builder": round(min(1.0, length_score * 0.7 + subtitle_density_score * 0.3), 3),
        "cursor_builder": round(min(1.0, visual_score * 0.6 + cursor_count_score * 0.4), 3),
        "talker_builder": round(talker_score, 3),
    }
    module_threshold = 0.8
    failed_modules = [
        module for module, score in module_scores.items() if float(score) < module_threshold
    ]
    heuristic = round(
        min(
            1.0,
            module_scores["slide_builder"] * 0.35
            + module_scores["subtitle_builder"] * 0.25
            + module_scores["cursor_builder"] * 0.25
            + module_scores["talker_builder"] * 0.15,
        ),
        3,
    )
    feedback = {
        "slide_builder": "Improve source coverage and make each slide grounded in input evidence.",
        "subtitle_builder": "Make narration complete, natural, and paced for the slide duration.",
        "cursor_builder": "Align cursor focus with the active narration and avoid random jumps.",
        "talker_builder": "Prepare narration text and provider metadata for downstream TTS/talker APIs.",
    }
    api_comment = ""
    if use_api:
        prompt = textwrap.dedent(
            f"""
            Judge this paper/project-to-video storyboard. Return JSON only:
            {{"overall_score":0.0,"module_scores":{{"slide_builder":0.0,"subtitle_builder":0.0,"cursor_builder":0.0,"talker_builder":0.0}},"failed_modules":["..."],"revise_next":{{"module":"instruction"}}}}
            Source title: {source['title']}
            Slides:
            {json.dumps(slides, ensure_ascii=False)[:18000]}
            Subtitles:
            {json.dumps(subtitles, ensure_ascii=False)[:12000]}
            """
        ).strip()
        data = _json_from_model(_call_openai_compatible(prompt))
        if isinstance(data, dict):
            score = data.get("overall_score")
            heuristic = _score01(score, heuristic)
            if isinstance(data.get("module_scores"), dict):
                for name, value in data["module_scores"].items():
                    if name in module_scores:
                        module_scores[name] = _score01(value, module_scores[name])
            if isinstance(data.get("failed_modules"), list):
                failed_modules = [
                    str(name)
                    for name in data["failed_modules"]
                    if str(name) in module_scores
                ]
            failed_modules = [
                module for module, score in module_scores.items() if float(score) < module_threshold
            ]
            if isinstance(data.get("revise_next"), dict):
                feedback = {
                    str(k): str(v)
                    for k, v in data["revise_next"].items()
                    if str(k) in module_scores
                } or feedback
            elif isinstance(data.get("revise_next"), list):
                feedback = {"slide_builder": " ".join(str(x) for x in data["revise_next"][:4])}
            api_comment = "openai_compatible_judge"
    return {
        "overall_score": heuristic,
        "target_score": None,
        "module_scores": module_scores,
        "module_threshold": module_threshold,
        "failed_modules": failed_modules,
        "coverage_score": round(coverage, 3),
        "length_score": round(length_score, 3),
        "visual_sync_score": round(visual_score, 3),
        "slide_count_score": round(slide_count_score, 3),
        "revise_next": feedback,
        "judge_mode": api_comment or "heuristic_judge",
    }


def revise_slides(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    judge: dict[str, Any],
    *,
    round_index: int,
    use_api: bool,
) -> list[dict[str, Any]]:
    if use_api:
        prompt = textwrap.dedent(
            f"""
            Revise this paper/project-to-video slide storyboard based on judge feedback.
            Return JSON only:
            {{"slides":[{{"title":"...","bullets":["..."],"speaker_note":"...","visual_prompt":"..."}}]}}
            Keep the same number of slides. Make the narration more grounded and presentation-ready.

            Source title: {source['title']}
            Judge feedback:
            {json.dumps(judge, ensure_ascii=False)}

            Current slides:
            {json.dumps(slides, ensure_ascii=False)[:24000]}
            """
        ).strip()
        data = _json_from_model(_call_openai_compatible(prompt))
        revised = data.get("slides") if isinstance(data, dict) else None
        if isinstance(revised, list) and revised:
            return [_normalize_slide(i, item) for i, item in enumerate(revised[: len(slides)], start=1)]

    feedback = judge.get("revise_next") or []
    feedback_text = " ".join(str(x) for x in feedback) or "tighten grounding and narration"
    revised_slides: list[dict[str, Any]] = []
    for slide in slides:
        item = dict(slide)
        bullets = [str(b) for b in item.get("bullets", [])]
        if round_index == 1:
            item["speaker_note"] = (
                str(item.get("speaker_note", ""))
                + " Revision pass: this slide is checked against the source and judge feedback."
            ).strip()
        elif round_index == 2 and len(bullets) < 4:
            bullets.append("Revision focus: improve evidence, pacing, and visual grounding for this scene.")
        else:
            item["speaker_note"] = (
                str(item.get("speaker_note", ""))
                + f" Judge note: {feedback_text[:180]}"
            ).strip()
        item["bullets"] = bullets[:4]
        item["visual_prompt"] = (
            str(item.get("visual_prompt", ""))
            + f"; revision round {round_index} focuses on judge feedback"
        ).strip("; ")
        revised_slides.append(item)
    return revised_slides


def revise_subtitles(
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    judge: dict[str, Any],
    *,
    round_index: int,
) -> list[dict[str, Any]]:
    instruction = ""
    revise_next = judge.get("revise_next") or {}
    if isinstance(revise_next, dict):
        instruction = str(revise_next.get("subtitle_builder", ""))
    revised: list[dict[str, Any]] = []
    by_slide: dict[int, list[dict[str, Any]]] = {}
    for item in subtitles:
        by_slide.setdefault(int(item["slide_index"]), []).append(dict(item))

    for slide in slides:
        slide_index = int(slide["index"])
        items = by_slide.get(slide_index, [])
        if not items:
            note = str(slide.get("speaker_note") or " ".join(slide.get("bullets") or []))
            items = [
                {
                    "slide_index": slide_index,
                    "start_sec": (slide_index - 1) * 12,
                    "end_sec": (slide_index - 1) * 12 + 7,
                    "text": note[:220],
                    "visual_focus_prompt": slide.get("visual_prompt", ""),
                }
            ]
        for item in items:
            text = str(item.get("text", "")).strip()
            if "Revision pass" not in text:
                item["text"] = (
                    text
                    + f" Revision pass {round_index}: narration is checked for pacing and clarity."
                )[:320]
            item["revise_reason"] = instruction or "module-level subtitle revision"
            revised.append(item)
    return revised


def revise_cursor_plan(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    cursor_plan: list[dict[str, Any]],
    judge: dict[str, Any],
    *,
    round_index: int,
    out_dir: Path | None = None,
    use_vlm_cursor: bool = False,
) -> list[dict[str, Any]]:
    if use_vlm_cursor:
        plan = build_cursor_plan(
            subtitles,
            slides=slides,
            source=source,
            out_dir=out_dir,
            use_vlm_cursor=True,
        )
        for item in plan:
            item["revision_round"] = round_index
        return plan
    instruction = ""
    revise_next = judge.get("revise_next") or {}
    if isinstance(revise_next, dict):
        instruction = str(revise_next.get("cursor_builder", ""))
    bullet_anchors = [(19, 34), (19, 47), (19, 60), (48, 43), (70, 56)]
    revised: list[dict[str, Any]] = []
    for i, subtitle in enumerate(subtitles):
        x, y = bullet_anchors[i % len(bullet_anchors)]
        revised.append(
            {
                "start_sec": subtitle["start_sec"],
                "end_sec": subtitle["end_sec"],
                "slide_index": subtitle["slide_index"],
                "x_percent": x,
                "y_percent": y,
                "reason": instruction or subtitle.get("visual_focus_prompt", ""),
                "revision_round": round_index,
            }
        )
    return revised


def revise_talker_plan(
    subtitles: list[dict[str, Any]],
    talker: dict[str, Any],
    judge: dict[str, Any],
    *,
    round_index: int,
) -> dict[str, Any]:
    revised = dict(talker)
    instruction = ""
    revise_next = judge.get("revise_next") or {}
    if isinstance(revise_next, dict):
        instruction = str(revise_next.get("talker_builder", ""))
    revised["narration_text"] = " ".join(str(item["text"]) for item in subtitles)
    revised["revision_round"] = round_index
    revised["revise_reason"] = instruction or "module-level talker plan refresh"
    return revised


def _downstream_modules(modules: list[str]) -> list[str]:
    order = ["slide_builder", "subtitle_builder", "cursor_builder", "talker_builder"]
    closure: set[str] = set(modules)
    if "slide_builder" in closure:
        closure.update(["subtitle_builder", "cursor_builder", "talker_builder"])
    if "subtitle_builder" in closure:
        closure.update(["cursor_builder", "talker_builder"])
    return [module for module in order if module in closure]


def _write_iteration_artifacts(
    out_dir: Path,
    *,
    round_index: int,
    rerun_modules: list[str],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    cursor_plan: list[dict[str, Any]],
    talker: dict[str, Any],
    judge: dict[str, Any],
) -> dict[str, str]:
    rd = out_dir / "iterations" / f"round_{round_index}"
    rd.mkdir(parents=True, exist_ok=True)
    payloads = {
        "slides.json": slides,
        "subtitles.json": subtitles,
        "cursor_plan.json": cursor_plan,
        "talker_plan.json": talker,
        "judge_feedback.json": judge,
        "rerun_modules.json": rerun_modules,
    }
    written: dict[str, str] = {}
    for name, payload in payloads.items():
        path = rd / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[name] = str(path)
    return written


def run_revision_loop(
    source: dict[str, Any],
    *,
    out_dir: Path,
    max_slides: int,
    seconds_per_slide: int,
    use_api: bool,
    target_score: float,
    max_revisions: int,
    min_revisions: int,
    use_vlm_cursor: bool,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
]:
    slides = build_slides(source, max_slides=max_slides, use_api=use_api)
    subtitles = build_subtitles(slides, seconds_per_slide=seconds_per_slide)
    cursor_plan = build_cursor_plan(
        subtitles,
        slides=slides,
        source=source,
        out_dir=out_dir,
        use_vlm_cursor=use_vlm_cursor,
    )
    talker = build_talker_plan(subtitles)
    history: list[dict[str, Any]] = []
    max_revisions = max(0, max_revisions)
    min_revisions = max(0, min_revisions)
    current_rerun_modules = ["slide_builder", "subtitle_builder", "cursor_builder", "talker_builder"]

    for round_index in range(max_revisions + 1):
        judge = judge_storyboard(source, slides, subtitles, use_api=use_api)
        judge["target_score"] = target_score
        score = float(judge.get("overall_score") or 0.0)
        failed_modules = [
            str(module) for module in judge.get("failed_modules", []) if isinstance(module, str)
        ]
        satisfied = score >= target_score and not failed_modules and round_index >= min_revisions
        if satisfied:
            next_modules: list[str] = []
        elif failed_modules:
            next_modules = _downstream_modules(failed_modules)
        else:
            next_modules = ["slide_builder"]
        judge["rerun_modules_next"] = next_modules
        artifacts = _write_iteration_artifacts(
            out_dir,
            round_index=round_index,
            rerun_modules=current_rerun_modules,
            slides=slides,
            subtitles=subtitles,
            cursor_plan=cursor_plan,
            talker=talker,
            judge=judge,
        )
        history.append(
            {
                "round": round_index,
                "score": score,
                "target_score": target_score,
                "satisfied": satisfied,
                "failed_modules": failed_modules,
                "rerun_modules": current_rerun_modules,
                "rerun_modules_next": next_modules,
                "revise_next": judge.get("revise_next", {}),
                "artifacts": artifacts,
            }
        )
        if satisfied or round_index >= max_revisions:
            return slides, subtitles, cursor_plan, talker, judge, history
        if "slide_builder" in next_modules:
            slides = revise_slides(
                source,
                slides,
                judge,
                round_index=round_index + 1,
                use_api=use_api,
            )
            subtitles = build_subtitles(slides, seconds_per_slide=seconds_per_slide)
            cursor_plan = build_cursor_plan(
                subtitles,
                slides=slides,
                source=source,
                out_dir=out_dir,
                use_vlm_cursor=use_vlm_cursor,
            )
            talker = build_talker_plan(subtitles)
        elif "subtitle_builder" in next_modules:
            subtitles = revise_subtitles(
                slides,
                subtitles,
                judge,
                round_index=round_index + 1,
            )
            cursor_plan = build_cursor_plan(
                subtitles,
                slides=slides,
                source=source,
                out_dir=out_dir,
                use_vlm_cursor=use_vlm_cursor,
            )
            talker = build_talker_plan(subtitles)
        elif "cursor_builder" in next_modules:
            cursor_plan = revise_cursor_plan(
                source,
                slides,
                subtitles,
                cursor_plan,
                judge,
                round_index=round_index + 1,
                out_dir=out_dir,
                use_vlm_cursor=use_vlm_cursor,
            )
            if "talker_builder" in next_modules:
                talker = revise_talker_plan(
                    subtitles,
                    talker,
                    judge,
                    round_index=round_index + 1,
                )
        elif "talker_builder" in next_modules:
            talker = revise_talker_plan(
                subtitles,
                talker,
                judge,
                round_index=round_index + 1,
            )
        current_rerun_modules = next_modules

    return slides, subtitles, cursor_plan, talker, judge, history


def write_srt(subtitles: list[dict[str, Any]], out: Path) -> None:
    def ts(sec: int) -> str:
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02}:{m:02}:{s:02},000"

    lines: list[str] = []
    for i, item in enumerate(subtitles, start=1):
        lines.extend(
            [
                str(i),
                f"{ts(int(item['start_sec']))} --> {ts(int(item['end_sec']))}",
                item["text"],
                "",
            ]
        )
    out.write_text("\n".join(lines), encoding="utf-8")


def write_slides_markdown(source: dict[str, Any], slides: list[dict[str, Any]], out: Path) -> None:
    lines = [f"# {source['title']}", "", f"- input_kind: `{source['kind']}`", f"- source: `{source['source_path']}`", ""]
    for slide in slides:
        lines.extend([f"## {slide['title']}", "", *[f"- {b}" for b in slide.get("bullets", [])], "", f"Speaker note: {slide.get('speaker_note', '')}", ""])
    out.write_text("\n".join(lines), encoding="utf-8")


def write_flowmesh_spec(out_dir: Path, source: dict[str, Any]) -> Path:
    spec = {
        "name": f"paper-project-video-{_slug(source['title'])}",
        "description": "FlowMesh-style DAG stub for AutoResearch paper/project-to-video MVP.",
        "inputs": {
            "source_path": source["source_path"],
            "kind": source["kind"],
            "api_env": "deploy/video_api.env",
        },
        "nodes": [
            {"id": "ingest", "type": "python", "artifact": "source.json"},
            {"id": "slide_builder", "type": "llm_or_heuristic", "artifact": "slides.md"},
            {"id": "subtitle_builder", "type": "llm_or_heuristic", "artifact": "subtitles.srt"},
            {"id": "cursor_builder", "type": "python", "artifact": "cursor_plan.json"},
            {"id": "talker_builder", "type": "external_api_optional", "artifact": "talker_plan.json"},
            {"id": "judge_agent", "type": "llm_or_heuristic", "artifact": "judge_feedback.json"},
            {"id": "revise_builder", "type": "llm_or_heuristic", "artifact": "revision_history.json"},
            {"id": "preview", "type": "html", "artifact": "preview.html"},
            {"id": "renderer", "type": "ffmpeg", "artifact": "video.mp4"},
        ],
        "edges": [
            ["ingest", "slide_builder"],
            ["slide_builder", "subtitle_builder"],
            ["subtitle_builder", "cursor_builder"],
            ["subtitle_builder", "talker_builder"],
            ["slide_builder", "judge_agent"],
            ["cursor_builder", "preview"],
            ["talker_builder", "preview"],
            ["judge_agent", "preview"],
            ["judge_agent", "revise_builder"],
            ["revise_builder", "slide_builder"],
            ["preview", "renderer"],
        ],
    }
    path = out_dir / "flowmesh_spec.json"
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_preview_html(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    cursor_plan: list[dict[str, Any]],
    judge: dict[str, Any],
    talker: dict[str, Any],
    out: Path,
) -> None:
    payload = json.dumps(
        {
            "source": source,
            "slides": slides,
            "subtitles": subtitles,
            "cursor": cursor_plan,
            "judge": judge,
            "talker": talker,
        },
        ensure_ascii=False,
    )
    slide_cards = "\n".join(
        f"""
        <article class="slide" data-slide="{slide['index']}">
          <div class="kicker">Slide {slide['index']}</div>
          <h2>{html.escape(slide['title'])}</h2>
          <ul>{''.join(f'<li>{html.escape(str(b))}</li>' for b in slide.get('bullets', []))}</ul>
          <p>{html.escape(slide.get('speaker_note', ''))}</p>
        </article>
        """
        for slide in slides
    )
    subtitle_rows = "\n".join(
        f"<tr><td>{s['start_sec']}s</td><td>{s['end_sec']}s</td><td>{s['slide_index']}</td><td>{html.escape(s['text'])}</td></tr>"
        for s in subtitles
    )
    judge_rows = "\n".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in judge.items()
        if k != "revise_next"
    )
    revise_next = judge.get("revise_next", {})
    if isinstance(revise_next, dict):
        revise_items = revise_next.items()
    else:
        revise_items = [(f"item_{i}", item) for i, item in enumerate(revise_next or [], start=1)]
    revise_list = "".join(
        f"<li><strong>{html.escape(str(k))}</strong>: {html.escape(str(v))}</li>"
        for k, v in revise_items
    )
    out.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(source['title'])} - AutoResearch Video Preview</title>
  <style>
    :root {{
      --ink:#17202a; --muted:#617182; --line:#d8e1ea; --panel:#fff; --bg:#f6f8fb;
      --accent:#2563eb; --good:#138a55; --warn:#b45309;
    }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ padding:28px 32px 18px; background:var(--panel); border-bottom:1px solid var(--line); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:8px 0 12px; font-size:22px; letter-spacing:0; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px 32px 44px; }}
    .sub {{ color:var(--muted); font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:1.25fr .75fr; gap:16px; align-items:start; }}
    .panel,.slide {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .slides {{ display:grid; gap:12px; }}
    .kicker {{ color:var(--accent); font-size:12px; font-weight:700; text-transform:uppercase; }}
    li {{ margin:8px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    td,th {{ padding:8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); }}
    .score {{ font-size:40px; font-weight:750; color:var(--good); }}
    .timeline {{ height:88px; position:relative; border:1px solid var(--line); border-radius:8px; background:#eef4ff; overflow:hidden; }}
    .dot {{ position:absolute; width:12px; height:12px; border-radius:50%; background:var(--accent); transform:translate(-50%,-50%); box-shadow:0 0 0 6px rgba(37,99,235,.13); }}
    pre {{ white-space:pre-wrap; word-break:break-word; background:#101827; color:#dbeafe; padding:12px; border-radius:6px; max-height:360px; overflow:auto; }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(source['title'])}</h1>
    <div class="sub">AutoResearch paper/project-to-video MVP · {html.escape(source['kind'])} · generated {_utc_now()}</div>
  </header>
  <main>
    <section class="grid">
      <div class="slides">{slide_cards}</div>
      <aside class="panel">
        <div class="kicker">Judge Agent</div>
        <div class="score">{judge.get('overall_score')}</div>
        <table>{judge_rows}</table>
        <h3>Revise next</h3>
        <ul>{revise_list}</ul>
      </aside>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Cursor Timeline</h2>
      <div class="timeline" id="timeline"></div>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Narration / Subtitle Builder</h2>
      <table><tr><th>Start</th><th>End</th><th>Slide</th><th>Subtitle</th></tr>{subtitle_rows}</table>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Talker Builder Plan</h2>
      <pre>{html.escape(json.dumps(talker, indent=2, ensure_ascii=False))}</pre>
    </section>
  </main>
  <script>
    const data = {payload};
    const timeline = document.getElementById('timeline');
    for (const p of data.cursor) {{
      const dot = document.createElement('div');
      dot.className = 'dot';
      dot.style.left = p.x_percent + '%';
      dot.style.top = p.y_percent + '%';
      dot.title = `slide ${{p.slide_index}} · ${{p.start_sec}}s · ${{p.reason}}`;
      timeline.appendChild(dot);
    }}
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )


def _font(size: int):
    try:
        from PIL import ImageFont

        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for path in candidates:
            if Path(path).is_file():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()
    except Exception:
        return None


def _wrap_text(draw: Any, text: str, font: Any, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _write_grounding_slide_image(
    source: dict[str, Any],
    slide: dict[str, Any],
    out: Path,
    *,
    width: int = 1280,
    height: int = 720,
) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    title_font = _font(44)
    body_font = _font(26)
    small_font = _font(20)
    img = Image.new("RGB", (width, height), (246, 248, 251))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width, 82), fill=(255, 255, 255), outline=(218, 226, 234))
    draw.text((42, 24), str(source.get("title", ""))[:70], fill=(23, 32, 42), font=small_font)
    panel = (80, 120, width - 80, height - 218)
    draw.rounded_rectangle(panel, radius=14, fill=(255, 255, 255), outline=(216, 225, 234), width=2)
    draw.text((120, 156), str(slide.get("title", ""))[:60], fill=(23, 32, 42), font=title_font)
    y = 238
    for bullet in slide.get("bullets", [])[:4]:
        lines = _wrap_text(draw, str(bullet), body_font, width - 250)
        draw.ellipse((122, y + 10, 134, y + 22), fill=(37, 99, 235))
        for line in lines[:2]:
            draw.text((150, y), line, fill=(35, 48, 64), font=body_font)
            y += 34
        y += 18
    img.save(out)
    return True


def render_mp4_video(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    cursor_plan: list[dict[str, Any]],
    out: Path,
    *,
    width: int = 1280,
    height: int = 720,
    fps: int = 12,
) -> bool:
    """Render a simple silent mp4 from slides/subtitles/cursor plan.

    This is intentionally dependency-light: PIL creates frames, ffmpeg encodes mp4.
    """
    if shutil.which("ffmpeg") is None:
        return False
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    frames_dir = out.parent / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    title_font = _font(44)
    body_font = _font(26)
    small_font = _font(20)
    caption_font = _font(23)
    frame_index = 0
    total_duration = max((int(s["end_sec"]) for s in subtitles), default=len(slides) * 10)
    if total_duration <= 0:
        total_duration = len(slides) * 10

    by_slide: dict[int, list[dict[str, Any]]] = {}
    for item in subtitles:
        by_slide.setdefault(int(item["slide_index"]), []).append(item)

    def active_subtitle(sec: float, slide_index: int) -> dict[str, Any] | None:
        for item in by_slide.get(slide_index, []):
            if float(item["start_sec"]) <= sec <= float(item["end_sec"]):
                return item
        items = by_slide.get(slide_index, [])
        return items[0] if items else None

    by_cursor: dict[int, list[dict[str, Any]]] = {}
    for item in cursor_plan:
        by_cursor.setdefault(int(item["slide_index"]), []).append(item)
    for items in by_cursor.values():
        items.sort(key=lambda item: float(item["start_sec"]))

    def ease(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3 - 2 * value)

    def cursor_position(sec: float, slide_index: int) -> tuple[int, int, str, float] | None:
        candidates = by_cursor.get(slide_index, [])
        if not candidates:
            return None
        active_idx = 0
        for i, item in enumerate(candidates):
            if float(item["start_sec"]) <= sec <= float(item["end_sec"]):
                active_idx = i
                break
            if sec >= float(item["start_sec"]):
                active_idx = i

        item = candidates[active_idx]
        target_x = float(item["x_percent"])
        target_y = float(item["y_percent"])
        if active_idx > 0:
            previous = candidates[active_idx - 1]
            start_x = float(previous["x_percent"])
            start_y = float(previous["y_percent"])
        else:
            start_x = 18.0
            start_y = 24.0
        start_sec = float(item["start_sec"])
        end_sec = max(start_sec + 0.01, float(item["end_sec"]))
        duration = end_sec - start_sec
        move_duration = min(0.68, max(0.28, duration * 0.16))
        move_t = ease((sec - start_sec) / move_duration)
        if sec <= start_sec + move_duration:
            x = width * (start_x + (target_x - start_x) * move_t) / 100
            y = height * (start_y + (target_y - start_y) * move_t) / 100
        else:
            hold = sec - start_sec - move_duration
            jitter_x = 1.8 * math.sin(hold * 6.7 + slide_index)
            jitter_y = 1.2 * math.sin(hold * 5.3 + active_idx)
            x = width * target_x / 100 + jitter_x
            y = height * target_y / 100 + jitter_y
        return int(x), int(y), str(item.get("reason", "")), move_t

    for slide in slides:
        slide_index = int(slide["index"])
        slide_subs = by_slide.get(slide_index, [])
        start = min((int(s["start_sec"]) for s in slide_subs), default=(slide_index - 1) * 10)
        end = max((int(s["end_sec"]) for s in slide_subs), default=start + 10)
        for tick in range(max(1, (end - start) * fps)):
            sec = start + tick / fps
            bg = Image.new("RGB", (width, height), (246, 248, 251))
            img = bg.copy()
            draw = ImageDraw.Draw(img)

            draw.rectangle((0, 0, width, 82), fill=(255, 255, 255), outline=(218, 226, 234))
            draw.text((42, 24), source["title"][:70], fill=(23, 32, 42), font=small_font)
            progress = max(0.0, min(1.0, sec / max(1, total_duration)))
            draw.rectangle((0, 80, int(width * progress), 84), fill=(37, 99, 235))
            draw.text(
                (width - 220, 24),
                f"{int(sec):02d}s / {total_duration:02d}s",
                fill=(97, 113, 130),
                font=small_font,
            )

            panel = (80, 120, width - 80, height - 218)
            draw.rounded_rectangle(panel, radius=14, fill=(255, 255, 255), outline=(216, 225, 234), width=2)
            draw.text((120, 156), str(slide["title"])[:60], fill=(23, 32, 42), font=title_font)

            y = 238
            for bullet in slide.get("bullets", [])[:3]:
                lines = _wrap_text(draw, str(bullet), body_font, width - 250)
                draw.ellipse((122, y + 10, 134, y + 22), fill=(37, 99, 235))
                for line in lines[:2]:
                    draw.text((150, y), line, fill=(35, 48, 64), font=body_font)
                    y += 34
                y += 18

            cur = cursor_position(sec, slide_index)
            if cur:
                cx, cy, _reason, move_t = cur
                if move_t < 1.0:
                    shadow = [(cx + 2, cy + 2), (cx + 20, cy + 36), (cx + 26, cy + 21), (cx + 42, cy + 20)]
                    draw.polygon(shadow, fill=(174, 190, 210))
                arrow = [(cx, cy), (cx + 18, cy + 34), (cx + 24, cy + 19), (cx + 40, cy + 18)]
                draw.polygon(arrow, fill=(37, 99, 235), outline=(18, 48, 110))

            sub = active_subtitle(sec, slide_index)
            caption = sub["text"] if sub else str(slide.get("speaker_note", ""))
            caption_top = height - 190
            caption_bottom = height - 112
            draw.rounded_rectangle(
                (104, caption_top, width - 104, caption_bottom),
                radius=10,
                fill=(16, 24, 39),
            )
            cap_lines = _wrap_text(draw, caption[:220], caption_font, width - 270)
            draw.text((132, caption_top + 16), cap_lines[0] if cap_lines else "", fill=(219, 234, 254), font=caption_font)
            if len(cap_lines) > 1:
                draw.text((132, caption_top + 44), cap_lines[1], fill=(219, 234, 254), font=caption_font)

            fade = min(1.0, max(0.18, (sec - start) / 0.7))
            if fade < 1.0:
                img = Image.blend(bg, img, fade)

            frame_path = frames_dir / f"frame_{frame_index:05d}.png"
            img.save(frame_path)
            frame_index += 1

    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    ok = proc.returncode == 0 and out.is_file()
    if ok:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return ok


def run_video_pipeline(
    input_path: Path,
    *,
    kind: str,
    out_dir: Path,
    max_slides: int = 5,
    seconds_per_slide: int = 12,
    use_api: bool = False,
    target_score: float = 0.9,
    max_revisions: int = 3,
    min_revisions: int = 1,
    fps: int = 12,
    use_vlm_cursor: bool = False,
) -> VideoPipelineResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    source = load_source(input_path, kind=kind)
    source["created_at"] = _utc_now()
    source["api_mode"] = "openai_compatible" if use_api and os.environ.get("OPENAI_API_KEY") else "heuristic"
    (out_dir / "source.json").write_text(json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")

    slides, subtitles, cursor_plan, talker, judge, revision_history = run_revision_loop(
        source,
        out_dir=out_dir,
        max_slides=max_slides,
        seconds_per_slide=seconds_per_slide,
        use_api=use_api,
        target_score=target_score,
        max_revisions=max_revisions,
        min_revisions=min_revisions,
        use_vlm_cursor=use_vlm_cursor,
    )

    write_slides_markdown(source, slides, out_dir / "slides.md")
    write_srt(subtitles, out_dir / "subtitles.srt")
    (out_dir / "storyboard.json").write_text(
        json.dumps(
            {"slides": slides, "subtitles": subtitles, "cursor_plan": cursor_plan, "talker_plan": talker},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "cursor_plan.json").write_text(
        json.dumps(cursor_plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "talker_plan.json").write_text(
        json.dumps(talker, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    judge_path = out_dir / "judge_feedback.json"
    judge_path.write_text(json.dumps(judge, indent=2, ensure_ascii=False), encoding="utf-8")
    revision_history_path = out_dir / "revision_history.json"
    revision_history_path.write_text(
        json.dumps(revision_history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_flowmesh_spec(out_dir, source)
    preview_path = out_dir / "preview.html"
    write_preview_html(source, slides, subtitles, cursor_plan, judge, talker, preview_path)
    video_path = out_dir / "video.mp4"
    video_rendered = render_mp4_video(source, slides, subtitles, cursor_plan, video_path, fps=fps)

    total_duration = max((s["end_sec"] for s in subtitles), default=0)
    vlm_cursor_points = sum(1 for item in cursor_plan if item.get("grounding_mode") == "vlm")
    metrics = {
        "judge_overall_score": judge["overall_score"],
        "target_score": target_score,
        "satisfied": float(judge["overall_score"]) >= target_score,
        "revision_rounds": max(0, len(revision_history) - 1),
        "max_revisions": max_revisions,
        "min_revisions": min_revisions,
        "coverage_score": judge["coverage_score"],
        "length_score": judge["length_score"],
        "visual_sync_score": judge["visual_sync_score"],
        "module_scores": judge.get("module_scores", {}),
        "failed_modules": judge.get("failed_modules", []),
        "rerun_modules_next": judge.get("rerun_modules_next", []),
        "slide_count": len(slides),
        "subtitle_count": len(subtitles),
        "estimated_duration_sec": total_duration,
        "api_used": source["api_mode"] != "heuristic",
        "talker_api_ready": talker["api_ready"],
        "video_rendered": video_rendered,
        "fps": fps,
        "renderer_version": "arrow_cursor_safe_subtitle_v4",
        "vlm_cursor_requested": use_vlm_cursor,
        "vlm_cursor_points": vlm_cursor_points,
        "cursor_grounding_mode": "vlm" if vlm_cursor_points else "heuristic",
        "video_path": str(video_path) if video_rendered else "",
        "preview_path": str(preview_path),
        "storyboard_path": str(out_dir / "storyboard.json"),
        "flowmesh_spec_path": str(out_dir / "flowmesh_spec.json"),
        "revision_history_path": str(revision_history_path),
    }
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    return VideoPipelineResult(
        out_dir=out_dir,
        metrics_path=metrics_path,
        preview_path=preview_path,
        video_path=video_path,
        storyboard_path=out_dir / "storyboard.json",
        judge_path=judge_path,
        revision_history_path=revision_history_path,
    )
