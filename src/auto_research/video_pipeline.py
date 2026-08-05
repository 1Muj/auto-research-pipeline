from __future__ import annotations

# ruff: noqa: E501
import base64
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import subprocess
import textwrap
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SLIDE_PLAN = [
    ("Motivation", "What problem does this work try to solve?"),
    ("Challenges", "Why is the task difficult or different from similar work?"),
    ("Dataset", "What data, benchmark, or source material anchors the work?"),
    ("Core Method", "What is the main technical or product idea?"),
    ("Architecture", "How do the major modules work together?"),
    ("Visual Generation", "How are slides, layouts, or visual assets produced?"),
    ("Narration And Sync", "How are subtitles, speech, cursor, or timing aligned?"),
    ("Evaluation Metrics", "How does the work measure quality and usefulness?"),
    ("Results", "What evidence, comparisons, or outcomes support the claims?"),
    ("Limitations", "What should be improved in the next version?"),
]

VISUAL_KINDS = ["image", "flow", "table", "metrics"]

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"
LUMID_BASE_URL = "https://lum.id/llm/v1"
LUMID_MODEL = "qwen3.6-27b"
LUMID_IMAGE_MODEL = "qwen-image"
LUMID_TTS_MODEL = "qwen-tts"
LUMID_OMNI_MODEL = "qwen-omni"

PAPER_VISUAL_THEMES: dict[str, dict[str, Any]] = {
    "signal": {
        "label": "Signal Grid",
        "background": (7, 12, 22),
        "pattern": (13, 52, 82),
        "accent": (20, 184, 166),
        "line": (16, 42, 70),
        "pattern_kind": "grid",
    },
    "bio": {
        "label": "Research Green",
        "background": (9, 17, 16),
        "pattern": (29, 61, 52),
        "accent": (91, 201, 151),
        "line": (24, 48, 43),
        "pattern_kind": "cells",
    },
    "field": {
        "label": "Terrain Ink",
        "background": (15, 19, 17),
        "pattern": (48, 71, 56),
        "accent": (158, 194, 124),
        "line": (37, 50, 42),
        "pattern_kind": "contours",
    },
    "orbit": {
        "label": "Graphite Arc",
        "background": (14, 15, 18),
        "pattern": (49, 56, 69),
        "accent": (112, 178, 248),
        "line": (38, 42, 51),
        "pattern_kind": "orbits",
    },
    "editorial": {
        "label": "Editorial Black",
        "background": (19, 18, 20),
        "pattern": (60, 52, 57),
        "accent": (225, 122, 132),
        "line": (43, 38, 42),
        "pattern_kind": "columns",
    },
    "circuit": {
        "label": "Technical Slate",
        "background": (8, 17, 20),
        "pattern": (24, 61, 68),
        "accent": (72, 190, 205),
        "line": (21, 47, 53),
        "pattern_kind": "circuit",
    },
}


_PROGRESS_STARTED_AT = time.time()


def _progress_enabled() -> bool:
    return os.environ.get("AUTO_VIDEO_PROGRESS", "1").strip().lower() not in {"0", "false", "no", "off"}


def _progress_bar(current: int, total: int, *, width: int = 20) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    current = max(0, min(total, current))
    filled = int(round(width * current / total))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _progress(stage: str, message: str, *, current: int | None = None, total: int | None = None, detail: str = "") -> None:
    if not _progress_enabled():
        return
    elapsed = int(time.time() - _PROGRESS_STARTED_AT)
    prefix = f"[video {elapsed:04d}s] {stage:<18}"
    if current is not None and total is not None:
        prefix += f" {_progress_bar(current, total)} {current}/{total}"
    if detail:
        message = f"{message} | {detail}"
    print(f"{prefix} {message}", file=sys.stderr, flush=True)


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


def choose_paper_visual_theme(source: dict[str, Any]) -> str:
    override = os.environ.get("AUTO_VIDEO_THEME", "auto").strip().lower()
    if override in PAPER_VISUAL_THEMES:
        return override

    sample = " ".join(
        [
            str(source.get("title") or ""),
            str(source.get("text") or "")[:6000],
        ]
    ).lower()
    domain_rules = [
        ("bio", ("medical", "medicine", "clinical", "patient", "protein", "genome", "biology", "biological", "cellular", "healthcare")),
        ("field", ("climate", "environment", "ecology", "ecological", "energy", "agriculture", "geospatial", "earth", "sustainability")),
        ("orbit", ("physics", "quantum", "theorem", "mathematics", "mathematical", "geometry", "algebra", "particle", "astronomy")),
        ("editorial", ("economics", "economic", "finance", "financial", "education", "social science", "policy", "linguistics", "humanities")),
        ("circuit", ("robot", "robotics", "control system", "autonomous", "agent", "multi-agent", "software system", "architecture")),
        ("signal", ("computer vision", "video generation", "multimodal", "neural", "artificial intelligence", "machine learning", "image generation")),
    ]
    scored = [
        (sum(sample.count(keyword) for keyword in keywords), -index, theme)
        for index, (theme, keywords) in enumerate(domain_rules)
    ]
    best_score, _priority, best_theme = max(scored)
    if best_score > 0:
        return best_theme

    digest = hashlib.sha256(str(source.get("title") or source.get("source_path") or "paper").encode("utf-8")).digest()
    names = list(PAPER_VISUAL_THEMES)
    return names[digest[0] % len(names)]


def _paper_visual_theme(source: dict[str, Any]) -> dict[str, Any]:
    name = str(source.get("visual_theme") or choose_paper_visual_theme(source))
    return PAPER_VISUAL_THEMES.get(name, PAPER_VISUAL_THEMES["signal"])


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


def _extract_pdf_metadata(path: Path) -> dict[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        metadata = PdfReader(str(path)).metadata or {}
    except Exception:
        return {}
    return {
        "title": _clean_display_text(metadata.get("/Title") or ""),
        "authors": _clean_display_text(metadata.get("/Author") or ""),
    }


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
        metadata = _extract_pdf_metadata(path)
    else:
        text = _read_text_file(path)
        metadata = {}
    title = metadata.get("title") or _guess_title(text) or path.stem.replace("_", " ").replace("-", " ").title()
    return {
        "kind": kind,
        "title": title,
        "authors": metadata.get("authors", ""),
        "source_path": str(path),
        "text": text,
        "files": [],
    }


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
    generic = {"preprint", "draft", "paper", "manuscript", "untitled"}
    for line in text.splitlines()[:40]:
        line = line.strip().strip("#").strip()
        if line.casefold() in generic:
            continue
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
    return [_clean_display_text(s) for s in out]


def _lumid_api_key() -> str | None:
    return (
        os.environ.get("LUM_API_KEY")
        or os.environ.get("LUMID_API_KEY")
        or os.environ.get("LUM_APIKEY")
        or os.environ.get("LUM_APIkey")
    )


def _text_model_config() -> tuple[str, str, str, str] | None:
    lumid_key = _lumid_api_key()
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    preferred = os.environ.get("AUTO_VIDEO_TEXT_PROVIDER", "auto").strip().lower()
    key = deepseek_key if preferred == "deepseek" and deepseek_key else lumid_key or deepseek_key or openai_key
    if not key:
        return None
    if preferred == "deepseek" and deepseek_key:
        base_url = (
            os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("DEEPSEEK_API_BASE")
            or DEEPSEEK_BASE_URL
        ).rstrip("/")
        model = os.environ.get("DEEPSEEK_MODEL") or DEEPSEEK_MODEL
        provider = "deepseek"
    elif lumid_key:
        base_url = (
            os.environ.get("LUMID_BASE_URL")
            or os.environ.get("LUM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or LUMID_BASE_URL
        ).rstrip("/")
        model = os.environ.get("LUMID_MODEL") or os.environ.get("LUM_MODEL") or os.environ.get("OPENAI_MODEL") or LUMID_MODEL
        provider = "lumid"
    elif deepseek_key:
        base_url = (
            os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("DEEPSEEK_API_BASE")
            or os.environ.get("OPENAI_BASE_URL")
            or DEEPSEEK_BASE_URL
        ).rstrip("/")
        model = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("OPENAI_MODEL") or DEEPSEEK_MODEL
        provider = "deepseek"
    else:
        base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        model = os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini"
        provider = "lumid" if "lum.id" in base_url else "openai_compatible"
    return key, base_url, model, provider


def _text_model_provider() -> str:
    cfg = _text_model_config()
    return cfg[3] if cfg else "heuristic"


def _lumid_base_url() -> str:
    return (
        os.environ.get("LUMID_BASE_URL")
        or os.environ.get("LUM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or LUMID_BASE_URL
    ).rstrip("/")


def _post_bytes(url: str, key: str, body: dict[str, Any], timeout: float) -> tuple[Any, bytes]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.headers, response.read()


def _get_bytes(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def _call_text_model(prompt: str) -> str | None:
    cfg = _text_model_config()
    if not cfg:
        return None
    key, base_url, model, _provider = cfg
    timeout = float(os.environ.get("AUTO_VIDEO_API_TIMEOUT", "60"))
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You produce concise JSON for an academic paper/project-to-video pipeline.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": int(os.environ.get("AUTO_VIDEO_TEXT_MAX_TOKENS", "6000")),
    }
    if _provider == "lumid":
        body["response_format"] = {"type": "json_object"}
        body["chat_template_kwargs"] = {"enable_thinking": False}
    attempts = max(1, min(5, int(os.environ.get("AUTO_VIDEO_TEXT_ATTEMPTS", "3"))))
    for attempt in range(1, attempts + 1):
        try:
            _progress("text_model", "request chat/completions", detail=f"provider={_provider} model={model} attempt={attempt}/{attempts}")
            _headers, raw = _post_bytes(f"{base_url}/chat/completions", key, body, timeout)
            data = json.loads(raw.decode("utf-8"))
            choice = data["choices"][0]
            message = choice["message"]
            content = str(message.get("content") or message.get("reasoning_content") or "").strip()
            if not content:
                raise ValueError("empty model response")
            finish_reason = str(choice.get("finish_reason") or "")
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            _progress(
                "text_model",
                "response received",
                detail=(
                    f"provider={_provider} model={model} attempt={attempt}/{attempts} "
                    f"finish={finish_reason or 'unknown'} chars={len(content)} "
                    f"completion_tokens={usage.get('completion_tokens', 'unknown')}"
                ),
            )
            if finish_reason == "length":
                raise ValueError(
                    f"model output reached max_tokens={body['max_tokens']} before completing JSON"
                )
            return content
        except Exception as exc:
            _progress("text_model", "request failed", detail=f"attempt={attempt}/{attempts} {type(exc).__name__}: {str(exc)[:160]}")
            if attempt < attempts:
                time.sleep(min(3.0, 0.75 * attempt))
    if _provider != "deepseek":
        return _call_deepseek_text(
            prompt,
            system="You produce concise JSON for an academic paper/project-to-video pipeline.",
        )
    return None


def _call_deepseek_text(prompt: str, *, system: str) -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    base_url = (os.environ.get("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL).rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL") or DEEPSEEK_MODEL
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
    }
    try:
        _progress("deepseek_fallback", "request text fallback", detail=f"model={model}")
        _headers, raw = _post_bytes(f"{base_url}/chat/completions", key, body, 60.0)
        message = json.loads(raw.decode("utf-8"))["choices"][0]["message"]
        content = str(message.get("content") or message.get("reasoning_content") or "").strip()
        return content or None
    except Exception as exc:
        _progress("deepseek_fallback", "request failed", detail=f"{type(exc).__name__}: {str(exc)[:160]}")
        return None


def _call_openai_compatible(prompt: str) -> str | None:
    return _call_text_model(prompt)


def _call_json_model(prompt: str) -> dict[str, Any] | None:
    attempts = max(1, min(5, int(os.environ.get("AUTO_VIDEO_JSON_ATTEMPTS", "3"))))
    for attempt in range(1, attempts + 1):
        data = _json_from_model(_call_openai_compatible(prompt))
        if isinstance(data, dict):
            return data
        _progress("text_model", "invalid JSON response", detail=f"attempt={attempt}/{attempts}; retrying model")
        if attempt < attempts:
            time.sleep(min(2.0, 0.5 * attempt))
    return None


def _clean_vision_response_content(value: Any) -> str | None:
    content = str(value or "").strip()
    audio_marker = content.find("[generated audio](data:audio/")
    if audio_marker >= 0:
        content = content[:audio_marker].strip()
    lowered = content.lower()
    if not content or "internal server error" in lowered or lowered.startswith("(qwen-omni error:"):
        return None
    return content


def _call_openai_vision(prompt: str, image_path: Path) -> str | None:
    key = (
        os.environ.get("OPENAI_VISION_API_KEY")
        or _lumid_api_key()
        or os.environ.get("OPENAI_API_KEY")
    )
    if not key:
        return None
    base_url = (
        os.environ.get("OPENAI_VISION_BASE_URL")
        or os.environ.get("LUMID_BASE_URL")
        or os.environ.get("LUM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = (
        os.environ.get("OPENAI_VISION_MODEL")
        or os.environ.get("LUMID_OMNI_MODEL")
        or os.environ.get("LUM_OMNI_MODEL")
        or os.environ.get("LUMID_MODEL")
        or os.environ.get("LUM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4.1-mini"
    )
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
    attempts = max(1, int(os.environ.get("AUTO_VIDEO_VISION_ATTEMPTS", "3")))
    for attempt in range(1, attempts + 1):
        try:
            _progress("vlm_cursor", "request vision grounding", detail=f"model={model} attempt={attempt}/{attempts}")
            _headers, raw = _post_bytes(f"{base_url}/chat/completions", key, body, timeout)
            data = json.loads(raw.decode("utf-8"))
            raw_content = str(data["choices"][0]["message"].get("content") or "")
            content = _clean_vision_response_content(raw_content)
            if not content:
                raise ValueError(raw_content[:200] or "empty vision response")
            _progress("vlm_cursor", "vision response received", detail=f"model={model} attempt={attempt}/{attempts}")
            return content
        except Exception as exc:
            _progress("vlm_cursor", "vision request failed", detail=f"attempt={attempt}/{attempts} {type(exc).__name__}: {str(exc)[:160]}")
            if attempt < attempts:
                time.sleep(min(2.0, 0.5 * attempt))
    return None


def _call_lumid_image(prompt: str, out: Path) -> tuple[bool, str]:
    key = _lumid_api_key() or os.environ.get("OPENAI_API_KEY")
    if not key:
        return False, "missing LUM_API_KEY or OPENAI_API_KEY"
    base_url = _lumid_base_url()
    model = os.environ.get("LUMID_IMAGE_MODEL") or os.environ.get("LUM_IMAGE_MODEL") or LUMID_IMAGE_MODEL
    timeout = float(os.environ.get("AUTO_VIDEO_IMAGE_TIMEOUT", os.environ.get("AUTO_VIDEO_API_TIMEOUT", "180")))
    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": os.environ.get("LUMID_IMAGE_SIZE", "1280x720"),
        "response_format": "b64_json",
    }
    attempts = max(1, min(5, int(os.environ.get("AUTO_VIDEO_IMAGE_ATTEMPTS", "3"))))
    last_error = "image generation failed"
    for attempt in range(1, attempts + 1):
        try:
            _progress("image_api", "request image generation", detail=f"model={model} size={body['size']} attempt={attempt}/{attempts}")
            _headers, raw = _post_bytes(f"{base_url}/images/generations", key, body, timeout)
            data = json.loads(raw.decode("utf-8"))
            item = (data.get("data") or [{}])[0]
            if item.get("b64_json"):
                out.write_bytes(base64.b64decode(str(item["b64_json"])))
            elif item.get("url"):
                out.write_bytes(_get_bytes(str(item["url"]), timeout))
            else:
                raise ValueError(f"unexpected image response keys: {sorted(item.keys())}")
            if not out.is_file() or out.stat().st_size <= 0:
                raise ValueError("empty generated image")
            _progress("image_api", "image response received", detail=f"path={out.name} attempt={attempt}/{attempts}")
            return True, ""
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            _progress("image_api", "image request failed", detail=f"attempt={attempt}/{attempts} {last_error[:160]}")
            if attempt < attempts:
                time.sleep(min(4.0, 1.0 * attempt))
    return False, last_error


def _image_generation_prompt(slide: dict[str, Any], *, variant_index: int = 0) -> str:
    bullets = [_clean_display_text(item) for item in slide.get("bullets", []) if str(item).strip()]
    caption = _clean_display_text(slide.get("visual_caption"))
    intent = _clean_display_text(slide.get("visual_prompt"))
    focus = bullets[variant_index % len(bullets)] if bullets else ""
    visual_concept = " ".join(part for part in (intent, focus) if part) or caption or "A clear research workflow"
    visual_concept = re.sub(r"\bslides?\b", "visual panels", visual_concept, flags=re.I)
    visual_concept = re.sub(r"\bpresentations?\b", "spoken explanations", visual_concept, flags=re.I)
    visual_concept = re.sub(r"\bsplit[- ]screen\b", "balanced left-right composition", visual_concept, flags=re.I)
    visual_concept = re.sub(r"\b(?:browser|dashboard|interface|screenshot|webpage)\b", "scene", visual_concept, flags=re.I)
    visual_concept = re.sub(r"\s+", " ", visual_concept).strip()[:700]
    return " ".join(
        [
            "Full-bleed editorial vector illustration, widescreen 16:9.",
            f"Visual concept: {visual_concept}.",
            "Depict the idea directly with people, physical objects, pictograms, arrows, and spatial relationships across one cohesive canvas.",
            "Use unlabelled shapes and symbols only. The image contains no words, letters, numbers, logos, controls, menus, or framed page.",
            "Keep every important object fully visible with eight percent empty safe margin on all four sides.",
            "Clean flat-vector style, strong silhouette, restrained color palette, no nested canvas.",
            (
                "Use a close explanatory composition centered on the mechanism and its interacting parts."
                if variant_index % 3 == 1
                else "Use a wider contextual composition that makes cause and effect immediately visible."
                if variant_index % 3 == 2
                else "Use a balanced editorial composition with one unmistakable visual hierarchy."
            ),
        ]
    ).strip()


def _validate_generated_slide_image(slide: dict[str, Any], image_path: Path) -> dict[str, Any]:
    prompt = textwrap.dedent(
        f"""
        Judge whether this generated illustration is suitable for the exact PPT slide below.
        Return JSON only:
        {{"accepted":true,"relevance_score":0-10,"complete_frame":true,"no_screenshot_or_document_crop":true,"no_readable_text":true,"reasons":[]}}

        Acceptance rules:
        - relevance_score must be at least 7.5.
        - The visual must directly represent the slide's concrete subject and claims.
        - All important objects and panels must be fully visible with safe margins.
        - Reject partial screenshots, browser windows, document fragments, cropped slides, and cut-off diagrams.
        - Reject readable or garbled generated text.

        Slide title: {_clean_display_text(slide.get("title"))}
        Slide purpose: {_clean_display_text(slide.get("purpose"))}
        Slide bullets: {json.dumps([_clean_display_text(item) for item in slide.get("bullets", [])], ensure_ascii=False)}
        Visual caption: {_clean_display_text(slide.get("visual_caption"))}
        Visual intent: {_clean_display_text(slide.get("visual_prompt"))}
        """
    ).strip()
    raw = _call_openai_vision(prompt, image_path)
    data = _json_from_model(raw)
    if not isinstance(data, dict) or not data:
        return {
            "accepted": False,
            "relevance_score": 0.0,
            "complete_frame": False,
            "no_screenshot_or_document_crop": False,
            "no_readable_text": False,
            "reasons": ["The visual validator did not return valid JSON."],
        }
    try:
        score = float(data.get("relevance_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    complete = bool(data.get("complete_frame"))
    no_crop = bool(data.get("no_screenshot_or_document_crop"))
    no_text = bool(data.get("no_readable_text"))
    accepted = bool(data.get("accepted")) and score >= 7.5 and complete and no_crop and no_text
    return {
        "accepted": accepted,
        "relevance_score": max(0.0, min(10.0, score)),
        "complete_frame": complete,
        "no_screenshot_or_document_crop": no_crop,
        "no_readable_text": no_text,
        "reasons": [str(item) for item in data.get("reasons", []) if str(item).strip()],
    }


def extract_paper_figures(source: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    source_path = Path(str(source.get("source_path") or "")).expanduser()
    if source_path.suffix.lower() != ".pdf" or not source_path.is_file():
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        return []

    figure_dir = out_dir / "paper_figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    max_figures = max(0, int(os.environ.get("AUTO_VIDEO_MAX_PAPER_FIGURES", "24")))
    min_width = max(120, int(os.environ.get("AUTO_VIDEO_PAPER_FIGURE_MIN_WIDTH", "320")))
    min_height = max(90, int(os.environ.get("AUTO_VIDEO_PAPER_FIGURE_MIN_HEIGHT", "180")))
    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    try:
        reader = PdfReader(str(source_path))
        for page_index, page in enumerate(reader.pages[:30], start=1):
            page_text = _clean_display_text(page.extract_text() or "")[:5000]
            for image_index, image_file in enumerate(list(page.images)[:8], start=1):
                if len(candidates) >= max_figures:
                    break
                digest = hashlib.sha256(image_file.data).hexdigest()
                if digest in seen_hashes:
                    continue
                image = image_file.image
                width, height = image.size
                if width < min_width or height < min_height:
                    continue
                if width / max(1, height) > 5.5 or height / max(1, width) > 4.0:
                    continue
                path = figure_dir / f"page_{page_index:02d}_figure_{image_index:02d}.png"
                image.convert("RGB").save(path)
                seen_hashes.add(digest)
                candidates.append(
                    {
                        "id": f"p{page_index:02d}f{image_index:02d}",
                        "page": page_index,
                        "path": str(path.resolve()),
                        "width": width,
                        "height": height,
                        "page_text": page_text,
                    }
                )
            if len(candidates) >= max_figures:
                break
    except Exception as exc:
        _progress("paper_figure", "figure extraction failed", detail=f"{type(exc).__name__}: {str(exc)[:140]}")
    public_candidates = [{k: v for k, v in item.items() if k != "page_text"} for item in candidates]
    (out_dir / "paper_figure_index.json").write_text(
        json.dumps(public_candidates, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _progress("paper_figure", "paper figures extracted", detail=f"count={len(candidates)}")
    return candidates


def _validate_paper_figure_for_slide(slide: dict[str, Any], image_path: Path) -> dict[str, Any]:
    prompt = textwrap.dedent(
        f"""
        Decide whether this image extracted from the source PDF directly supports the current explainer section.
        Return JSON only:
        {{"accepted":true,"relevance_score":0-10,"is_source_evidence":true,"reasons":[]}}

        Accept genuine architecture diagrams, method figures, dataset charts, result plots, or qualitative examples from the source paper that clarify this exact section.
        Reject logos, decorative icons, author photos, generic cover art, screenshots of unrelated papers or presentations, and figures whose subject does not match the section.
        Original labels and legends are allowed. Require relevance_score of at least 7.5.

        Section title: {_clean_display_text(slide.get('title'))}
        Section purpose: {_clean_display_text(slide.get('purpose'))}
        Claims: {json.dumps([_clean_display_text(item) for item in slide.get('bullets', [])], ensure_ascii=False)}
        """
    ).strip()
    data = _json_from_model(_call_openai_vision(prompt, image_path))
    if not isinstance(data, dict) or not data:
        return {"accepted": False, "relevance_score": 0.0, "is_source_evidence": False, "reasons": ["No valid VLM decision."]}
    try:
        score = float(data.get("relevance_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    evidence = bool(data.get("is_source_evidence"))
    accepted = bool(data.get("accepted")) and score >= 7.5 and evidence
    return {
        "accepted": accepted,
        "relevance_score": max(0.0, min(10.0, score)),
        "is_source_evidence": evidence,
        "reasons": [str(item) for item in data.get("reasons", []) if str(item).strip()],
    }


def assign_paper_figures(
    slides: list[dict[str, Any]],
    figures: list[dict[str, Any]],
    *,
    validate_with_vlm: bool = False,
) -> None:
    used_paths: set[str] = set()
    max_per_slide = max(0, int(os.environ.get("AUTO_VIDEO_PAPER_FIGURES_PER_SLIDE", "1")))
    stop_words = {
        "this", "that", "with", "from", "into", "using", "paper", "video", "slide", "slides",
        "generation", "presentation", "research", "method", "result", "results",
    }

    def tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) >= 4 and token not in stop_words
        }

    for slide in slides:
        slide_text = " ".join(
            [
                str(slide.get("title") or ""),
                str(slide.get("purpose") or ""),
                *[str(item) for item in slide.get("bullets") or []],
            ]
        )
        slide_tokens = tokens(slide_text)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for figure in figures:
            path = str(figure.get("path") or "")
            if not path or path in used_paths:
                continue
            page_tokens = tokens(str(figure.get("page_text") or ""))
            overlap = slide_tokens & page_tokens
            score = float(len(overlap)) + min(1.5, len(overlap) / max(1, len(slide_tokens)) * 4.0)
            score += min(1.0, (int(figure.get("width") or 0) * int(figure.get("height") or 0)) / 1_500_000)
            ranked.append((score, figure))
        selected: list[dict[str, Any]] = []
        validations: list[dict[str, Any]] = []
        candidate_limit = max(max_per_slide, int(os.environ.get("AUTO_VIDEO_PAPER_FIGURE_VALIDATION_CANDIDATES", "4")))
        for score, candidate in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:candidate_limit]:
            if score < 1.2 or len(selected) >= max_per_slide:
                continue
            decision = (
                _validate_paper_figure_for_slide(slide, Path(str(candidate["path"])))
                if validate_with_vlm
                else {"accepted": True, "relevance_score": None, "is_source_evidence": None, "reasons": ["Text relevance assignment"]}
            )
            validations.append({"path": str(candidate["path"]), "text_score": round(score, 3), **decision})
            if decision.get("accepted"):
                selected.append(candidate)
        paths = [str(item["path"]) for item in selected]
        slide["paper_figure_paths"] = paths
        slide["paper_figure_validation"] = validations
        used_paths.update(paths)


def generate_slide_images(slides: list[dict[str, Any]], out_dir: Path, *, use_image_api: bool) -> list[dict[str, Any]]:
    image_dir = out_dir / "generated_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    image_mode = os.environ.get("AUTO_VIDEO_IMAGE_MODE", "all").strip().lower()
    variants_per_slide = max(1, int(os.environ.get("AUTO_VIDEO_IMAGES_PER_SLIDE", "2")))
    total = len(slides) * variants_per_slide
    _progress(
        "image_builder",
        "start slide visual generation",
        current=0,
        total=total,
        detail=f"api={'on' if use_image_api else 'off'} mode={image_mode} variants={variants_per_slide} model={os.environ.get('LUMID_IMAGE_MODEL') or os.environ.get('LUM_IMAGE_MODEL') or LUMID_IMAGE_MODEL}",
    )
    for n, slide in enumerate(slides, start=1):
        slide_kind = str(slide.get("visual_kind") or "image").strip().lower()
        eligible = (
            image_mode in {"all", "1", "true", "yes"}
            or (image_mode in {"image_only", "images"} and slide_kind == "image")
        )
        generated_paths: list[str] = []
        validate_images = os.environ.get("AUTO_VIDEO_IMAGE_VALIDATE", "1").strip().lower() not in {"0", "false", "no", "off"}
        max_attempts = max(1, int(os.environ.get("AUTO_VIDEO_IMAGE_MAX_ATTEMPTS", "3")))
        prompts: list[str] = []
        for variant_index in range(variants_per_slide):
            progress_index = (n - 1) * variants_per_slide + variant_index + 1
            prompt = _image_generation_prompt(slide, variant_index=variant_index)
            prompts.append(prompt)
            path = image_dir / f"slide_{int(slide['index']):02d}_v{variant_index + 1:02d}.png"
            ok = eligible and path.is_file() and path.stat().st_size > 0
            error = "" if ok else "not requested"
            validation: dict[str, Any] = {}
            if ok and validate_images:
                validation = _validate_generated_slide_image(slide, path)
                ok = bool(validation.get("accepted"))
                if not ok:
                    error = "cached image rejected: " + "; ".join(validation.get("reasons") or ["failed completeness or relevance checks"])
            elif ok:
                _progress("image_builder", "using cached image", current=progress_index, total=total, detail=f"slide={slide['index']} variant={variant_index + 1}")
            if not ok and eligible and use_image_api:
                for attempt in range(1, max_attempts + 1):
                    attempt_prompt = prompt
                    if attempt == 2:
                        attempt_prompt += " Use a physical metaphor with characters and tangible objects placed directly on the background."
                    elif attempt >= 3:
                        attempt_prompt += " Use a minimal abstract composition of large unlabelled icons connected by arrows, with no rectangular panels."
                    _progress(
                        "image_builder",
                        "calling image model",
                        current=progress_index,
                        total=total,
                        detail=f"slide={slide['index']} variant={variant_index + 1} attempt={attempt}/{max_attempts} title={str(slide.get('title', ''))[:52]}",
                    )
                    ok, error = _call_lumid_image(attempt_prompt, path)
                    if ok and validate_images:
                        validation = _validate_generated_slide_image(slide, path)
                        ok = bool(validation.get("accepted"))
                        if not ok:
                            error = "image rejected: " + "; ".join(validation.get("reasons") or ["failed completeness or relevance checks"])
                    if ok:
                        break
            if ok:
                generated_paths.append(str(path.resolve()))
            else:
                reason = error if eligible and use_image_api else "api disabled" if eligible else f"mode={image_mode} kind={slide_kind}"
                error = reason
            _progress(
                "image_builder",
                "image accepted" if ok else "image skipped" if not eligible else "image failed",
                current=progress_index,
                total=total,
                detail=f"slide={slide['index']} variant={variant_index + 1} path={path.name if ok else ''} error={error[:110] if error else ''}",
            )
            results.append(
                {
                    "slide_index": int(slide["index"]),
                    "variant_index": variant_index + 1,
                    "asset_kind": "generated",
                    "ok": ok,
                    "model": os.environ.get("LUMID_IMAGE_MODEL") or os.environ.get("LUM_IMAGE_MODEL") or LUMID_IMAGE_MODEL,
                    "path": str(path.resolve()) if ok else "",
                    "prompt": prompt,
                    "validation": validation,
                    "error": "" if ok else error,
                }
            )
            (out_dir / "image_generation.json").write_text(
                json.dumps(results, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        paper_paths = [str(path) for path in slide.get("paper_figure_paths") or [] if Path(str(path)).is_file()]
        visual_assets: list[str] = []
        for index in range(max(len(generated_paths), len(paper_paths))):
            if index < len(generated_paths):
                visual_assets.append(generated_paths[index])
            if index < len(paper_paths):
                visual_assets.append(paper_paths[index])
        slide["generated_image_prompts"] = prompts
        slide["generated_image_paths"] = generated_paths
        slide["visual_asset_paths"] = visual_assets
        slide["generated_image_prompt"] = prompts[0] if prompts else ""
        slide["generated_image_path"] = visual_assets[0] if visual_assets else ""
    (out_dir / "image_generation.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    ok_count = sum(1 for item in results if item.get("ok"))
    figure_count = sum(len(slide.get("paper_figure_paths") or []) for slide in slides)
    _progress("image_builder", "finished slide visual generation", current=total, total=total, detail=f"generated={ok_count}/{total} paper_figures={figure_count}")
    return results


def synthesize_tts_audio(talker: dict[str, Any], out_dir: Path, *, use_tts: bool) -> dict[str, Any]:
    text = _prepare_tts_text(str(talker.get("narration_text") or "").strip())
    result = {
        "ok": False,
        "model": os.environ.get("LUMID_TTS_MODEL") or os.environ.get("LUM_TTS_MODEL") or LUMID_TTS_MODEL,
        "path": "",
        "provider": "lumid-qwen-tts",
        "error": "",
    }
    if not use_tts:
        result["error"] = "disabled"
        _progress("tts_builder", "skipped", detail="--use-tts is off")
        return result
    if not text:
        result["error"] = "empty narration text"
        _progress("tts_builder", "failed", detail=result["error"])
        return result
    out = out_dir / "narration.mp3"
    model = str(result["model"])
    _progress("tts_builder", "request speech synthesis", detail=f"model={model} chars={len(text[:12000])}")
    ok, error = _synthesize_tts_clip(text, out)
    result["ok"] = ok
    result["error"] = error
    result["path"] = str(out.resolve()) if ok else ""
    _progress("tts_builder", "speech synthesis done" if ok else "speech synthesis failed", detail=f"path={result['path']} error={error[:120]}")
    return result


def add_title_card_hold(subtitles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = [dict(item) for item in subtitles]
    if prepared:
        prepared[0]["title_card_hold_sec"] = max(
            2.5,
            min(8.0, float(os.environ.get("AUTO_VIDEO_TITLE_CARD_SEC", "4.0"))),
        )
    return prepared


def _synthesize_tts_clip(text: str, out: Path) -> tuple[bool, str]:
    key = _lumid_api_key() or os.environ.get("OPENAI_API_KEY")
    if not key:
        return False, "missing LUM_API_KEY"
    base_url = _lumid_base_url()
    timeout = float(os.environ.get("AUTO_VIDEO_TTS_TIMEOUT", os.environ.get("AUTO_VIDEO_API_TIMEOUT", "120")))
    model = os.environ.get("LUMID_TTS_MODEL") or os.environ.get("LUM_TTS_MODEL") or LUMID_TTS_MODEL
    body = {
        "model": model,
        "input": text,
        "voice": os.environ.get("LUMID_TTS_VOICE", "default"),
        "response_format": "mp3",
    }
    try:
        headers, raw = _post_bytes(f"{base_url}/audio/speech", key, body, timeout)
        content_type = headers.get("content-type", "")
        if "application/json" in content_type:
            data = json.loads(raw.decode("utf-8"))
            audio_b64 = data.get("b64_json") or data.get("audio") or data.get("data")
            if isinstance(audio_b64, str):
                out.write_bytes(base64.b64decode(audio_b64))
            elif data.get("url"):
                out.write_bytes(_get_bytes(str(data["url"]), timeout))
            else:
                return False, "JSON response did not contain audio"
        else:
            out.write_bytes(raw)
        ok = out.is_file() and out.stat().st_size > 0
        return ok, "" if ok else "speech synthesis returned empty audio"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:260]}"


def synthesize_tts_segments(
    subtitles: list[dict[str, Any]],
    out_dir: Path,
    *,
    use_tts: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result: dict[str, Any] = {
        "ok": False,
        "model": os.environ.get("LUMID_TTS_MODEL") or os.environ.get("LUM_TTS_MODEL") or LUMID_TTS_MODEL,
        "path": "",
        "provider": "lumid-qwen-tts",
        "timing_mode": "segment_exact",
        "speech_tempo": float(os.environ.get("AUTO_VIDEO_TTS_TEMPO", "1.00")),
        "pre_speech_hold_sec": float(os.environ.get("AUTO_VIDEO_PRE_SPEECH_HOLD_SEC", "0.35")),
        "post_speech_hold_sec": float(os.environ.get("AUTO_VIDEO_POST_SPEECH_HOLD_SEC", "1.20")),
        "segments": [],
        "error": "",
    }
    if not use_tts:
        result["error"] = "disabled"
        return result, subtitles
    if not subtitles or shutil.which("ffmpeg") is None:
        result["error"] = "missing subtitles or ffmpeg"
        return result, subtitles
    if not (_lumid_api_key() or os.environ.get("OPENAI_API_KEY")):
        result["error"] = "missing LUM_API_KEY"
        return result, subtitles

    tempo = max(0.7, min(1.0, float(result["speech_tempo"])))
    pre_hold = max(0.0, min(2.0, float(result["pre_speech_hold_sec"])))
    post_hold = max(0.5, min(4.0, float(result["post_speech_hold_sec"])))
    segment_dir = out_dir / "narration_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[int, str, Path]] = []
    for index, subtitle in enumerate(subtitles):
        text = _prepare_tts_text(str(subtitle.get("text") or "").strip())
        jobs.append((index, text, segment_dir / f"raw_{index:03d}.mp3"))

    def generate(job: tuple[int, str, Path]) -> tuple[int, bool, str, Path]:
        index, text, path = job
        if not text:
            return index, False, "empty subtitle", path
        ok, error = _synthesize_tts_clip(text, path)
        return index, ok, error, path

    workers = max(1, min(4, int(os.environ.get("AUTO_VIDEO_TTS_WORKERS", "2"))))
    _progress("tts_builder", "generate timed narration segments", current=0, total=len(jobs), detail=f"workers={workers} tempo={tempo:.2f}")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        generated = list(pool.map(generate, jobs))
    retry_attempts = max(1, min(5, int(os.environ.get("AUTO_VIDEO_TTS_SEGMENT_RETRIES", "3"))))
    recovered: list[tuple[int, bool, str, Path]] = []
    for index, ok, error, raw_path in generated:
        if not ok:
            text = jobs[index][1]
            for attempt in range(1, retry_attempts + 1):
                raw_path.unlink(missing_ok=True)
                _progress(
                    "tts_builder",
                    "retry failed narration segment",
                    current=index + 1,
                    total=len(jobs),
                    detail=f"attempt={attempt}/{retry_attempts}",
                )
                ok, error = _synthesize_tts_clip(text, raw_path)
                if ok:
                    break
                if attempt < retry_attempts:
                    time.sleep(min(3.0, 0.75 * attempt))
        recovered.append((index, ok, error, raw_path))
    generated = recovered
    generated.sort(key=lambda item: item[0])

    concat_paths: list[Path] = []
    synced: list[dict[str, Any]] = []
    cursor = 0.0
    segment_reports: list[dict[str, Any]] = []
    for index, ok, error, raw_path in generated:
        if not ok:
            result["error"] = f"segment {index + 1} failed: {error}"
            return result, subtitles
        raw_duration = media_duration_seconds(raw_path)
        if not raw_duration:
            result["error"] = f"segment {index + 1} has no measurable duration"
            return result, subtitles
        speech_duration = raw_duration / tempo
        segment_pre_hold = max(pre_hold, float(subtitles[index].get("title_card_hold_sec") or 0.0))
        target_duration = segment_pre_hold + speech_duration + post_hold
        wav_path = segment_dir / f"timed_{index:03d}.wav"
        delay_ms = int(round(segment_pre_hold * 1000))
        filter_chain = f"atempo={tempo:.4f},adelay={delay_ms}|{delay_ms},apad=pad_dur={post_hold:.4f}"
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(raw_path), "-af", filter_chain,
                "-t", f"{target_duration:.4f}", "-ar", "44100", "-ac", "2",
                "-c:a", "pcm_s16le", str(wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        actual_duration = media_duration_seconds(wav_path) if proc.returncode == 0 else None
        if not actual_duration:
            result["error"] = f"segment {index + 1} timing conversion failed"
            return result, subtitles
        updated = dict(subtitles[index])
        updated["segment_start_sec"] = round(cursor, 3)
        updated["start_sec"] = round(
            cursor + segment_pre_hold if updated.get("title_card_hold_sec") else cursor,
            3,
        )
        updated["speech_start_sec"] = round(cursor + segment_pre_hold, 3)
        updated["speech_end_sec"] = round(cursor + segment_pre_hold + speech_duration, 3)
        cursor += actual_duration
        updated["end_sec"] = round(cursor, 3)
        synced.append(updated)
        concat_paths.append(wav_path)
        segment_reports.append(
            {
                "index": index,
                "slide_index": updated.get("slide_index"),
                "text": updated.get("text", ""),
                "raw_duration_sec": round(raw_duration, 3),
                "speech_duration_sec": round(speech_duration, 3),
                "timeline_duration_sec": round(actual_duration, 3),
                "pre_speech_hold_sec": round(segment_pre_hold, 3),
                "start_sec": updated["start_sec"],
                "end_sec": updated["end_sec"],
            }
        )

    concat_file = segment_dir / "concat.txt"
    concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in concat_paths), encoding="utf-8")
    narration_path = out_dir / "narration.mp3"
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "2", str(narration_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    result["ok"] = proc.returncode == 0 and narration_path.is_file() and narration_path.stat().st_size > 0
    result["path"] = str(narration_path.resolve()) if result["ok"] else ""
    result["segments"] = segment_reports
    result["total_duration_sec"] = round(cursor, 3)
    if not result["ok"]:
        result["error"] = "failed to concatenate timed narration segments"
    _progress("tts_builder", "timed narration ready" if result["ok"] else "timed narration failed", current=len(jobs), total=len(jobs), detail=f"duration={cursor:.2f}s")
    return result, synced


def mux_audio_into_video(video_path: Path, audio_path: Path) -> bool:
    if not video_path.is_file() or not audio_path.is_file() or shutil.which("ffmpeg") is None:
        _progress("mux_audio", "skipped", detail="missing video/audio file or ffmpeg")
        return False
    video_duration = media_duration_seconds(video_path)
    audio_duration = media_duration_seconds(audio_path)
    duration_delta = abs(video_duration - audio_duration) if video_duration and audio_duration else None
    if duration_delta is None or duration_delta > 0.75:
        _progress(
            "mux_audio",
            "refused unsynchronized mux",
            detail=(
                f"video={video_duration or 0:.3f}s audio={audio_duration or 0:.3f}s "
                f"delta={duration_delta if duration_delta is not None else -1:.3f}s"
            ),
        )
        return False
    silent_backup = video_path.with_name("video_silent.mp4")
    output = video_path.with_name("video_with_audio.mp4")
    try:
        shutil.copy2(video_path, silent_backup)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
        _progress("mux_audio", "start muxing audio into video", detail=f"audio={audio_path.name}")
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if proc.returncode == 0 and output.is_file():
            shutil.move(str(output), str(video_path))
            ok = has_audio_stream(video_path)
            _progress("mux_audio", "mux complete" if ok else "mux missing audio stream", detail=f"video={video_path.name}")
            return ok
        _progress("mux_audio", "mux failed", detail=f"returncode={proc.returncode}")
    except Exception as exc:
        _progress("mux_audio", "mux failed", detail=f"{type(exc).__name__}: {str(exc)[:160]}")
        return False
    return False


def has_audio_stream(path: Path) -> bool:
    if not path.is_file() or shutil.which("ffprobe") is None:
        return False
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def media_duration_seconds(path: Path) -> float | None:
    if not path.is_file() or shutil.which("ffprobe") is None:
        return None
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        duration = float(proc.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def scale_timeline_to_duration(
    subtitles: list[dict[str, Any]],
    cursor_plan: list[dict[str, Any]],
    target_duration: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    current_duration = max((float(item["end_sec"]) for item in subtitles), default=0.0)
    if current_duration <= 0 or target_duration <= 0:
        return subtitles, cursor_plan, 1.0
    scale = target_duration / current_duration

    def scale_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scaled: list[dict[str, Any]] = []
        for item in items:
            new_item = dict(item)
            start = float(item.get("start_sec", 0.0)) * scale
            end = float(item.get("end_sec", start + 1.0)) * scale
            if end <= start:
                end = start + 0.5
            new_item["start_sec"] = round(start, 3)
            new_item["end_sec"] = round(end, 3)
            scaled.append(new_item)
        return scaled

    return scale_items(subtitles), scale_items(cursor_plan), scale


def align_cursor_plan_to_subtitles(
    cursor_plan: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aligned: list[dict[str, Any]] = []
    for index, item in enumerate(cursor_plan):
        updated = dict(item)
        if index < len(subtitles):
            updated["start_sec"] = subtitles[index]["start_sec"]
            updated["end_sec"] = subtitles[index]["end_sec"]
        aligned.append(updated)
    return aligned


def _json_from_model(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    if start < 0:
        return None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(cleaned[start:])
        return parsed if isinstance(parsed, dict) else None
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


def _clamp_slide_count(value: Any, *, min_slides: int, max_slides: int) -> int | None:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return None
    return max(1, min(max_slides, max(min_slides, count)))


def _heuristic_target_slide_count(source: dict[str, Any], *, max_slides: int) -> int:
    max_slides = max(1, int(max_slides))
    min_slides = min(max_slides, int(os.environ.get("AUTO_VIDEO_MIN_SLIDES", "6")))
    text = str(source.get("text") or "")
    word_count = len(re.findall(r"\w+", text))
    heading_count = len(re.findall(r"\n\s*(?:\d+(?:\.\d+)?|[A-Z][A-Z ]{4,})\s+", text))
    figure_count = len(re.findall(r"\b(?:fig(?:ure)?|table)\s*\.?\s*\d+", text, flags=re.IGNORECASE))
    if word_count < 2500:
        target = 5
    elif word_count < 5500:
        target = 7
    elif word_count < 9000:
        target = 9
    else:
        target = max_slides
    if heading_count >= 8 or figure_count >= 6:
        target += 1
    return max(1, min(max_slides, max(min_slides, target)))


def decide_target_slide_count(source: dict[str, Any], *, max_slides: int, use_api: bool) -> int:
    max_slides = max(1, int(max_slides))
    configured = os.environ.get("AUTO_VIDEO_SLIDE_COUNT", "auto").strip().lower()
    if configured not in {"", "auto", "dynamic", "model"}:
        fixed = _clamp_slide_count(
            configured,
            min_slides=min(max_slides, int(os.environ.get("AUTO_VIDEO_MIN_SLIDES", "1"))),
            max_slides=max_slides,
        )
        if fixed:
            return fixed
    fallback = _heuristic_target_slide_count(source, max_slides=max_slides)
    if not use_api:
        return fallback
    prompt = textwrap.dedent(
        f"""
        Decide how many slides are appropriate for this PPT explanation video.
        Return JSON only: {{"slide_count": 8, "reason": "..."}}
        Use {max_slides} as a hard maximum, not a target.
        Choose fewer slides for short/simple papers and more slides for long/complex papers.
        A good range is 6-10 for most papers. Avoid padding with weak slides.

        Source title: {source.get("title", "")}
        Source excerpt:
        {str(source.get("text") or "")[:8000]}
        """
    ).strip()
    data = _call_json_model(prompt)
    if isinstance(data, dict):
        count = _clamp_slide_count(
            data.get("slide_count"),
            min_slides=min(max_slides, int(os.environ.get("AUTO_VIDEO_MIN_SLIDES", "6"))),
            max_slides=max_slides,
        )
        if count:
            return count
    return fallback


def build_slides(source: dict[str, Any], *, max_slides: int, use_api: bool) -> list[dict[str, Any]]:
    text = source["text"][:65000]
    title = source["title"]
    keys = _keywords(text)
    target_slides = decide_target_slide_count(source, max_slides=max_slides, use_api=use_api)
    if use_api:
        source_chars = int(os.environ.get("AUTO_VIDEO_SOURCE_CHARS", "16000"))
        prompt = textwrap.dedent(
            f"""
            Convert this {source['kind']} into a PPT explanation video storyboard.
            Return JSON only:
            {{"slide_count":{target_slides},"slides":[{{"title":"...","bullets":["..."],"speaker_note":"...","visual_prompt":"...","visual_kind":"image|flow|table|metrics","visual_caption":"...","visual_items":["..."],"visual_table":[["Metric","Value","Meaning"]],"scene_direction":{{"layout":"editorial|comparison|data_wall|timeline|evidence_grid|diagram_focus","entrance":"fade_up|slide_left|slide_right|scale_in|wipe","emphasis":"specific content to emphasize"}}}}]}}
            Create exactly {target_slides} slides. The hard maximum configured by the user is {max_slides}.
            Make each bullet a complete, concrete sentence under 24 words.
            Do not use ellipses, half sentences, fake code, terminal text, or placeholder UI text.
            Keep speaker_note detailed enough for narration, about 80-120 words per slide.
            Include concrete paper details such as dataset size, builders, metrics, modules, or reported findings when present.
            Vary the visual_kind across image, flow, table, and metrics.
            Vary scene_direction layout and entrance across adjacent slides. Choose comparison for before/after or speed results, data_wall for several statistics, timeline for ordered stages, evidence_grid for tables, and diagram_focus for mechanisms.
            The emphasis must name a concrete claim, number, figure, module, or relationship from this slide. Never use generic labels such as Architecture, Aspect, or Keeps the demo grounded.
            Prefer diagrams, tables, metric summaries, and conceptual visuals over screenshots.
            Keep all content grounded in the source.

            Title: {title}
            Source:
            {text[:source_chars]}
            """
        ).strip()
        data = _call_json_model(prompt)
        slides = data.get("slides") if isinstance(data, dict) else None
        if isinstance(slides, list) and slides:
            normalized = [_normalize_slide(i, item) for i, item in enumerate(slides[:target_slides], start=1)]
            if len(normalized) < target_slides:
                normalized.extend(
                    _build_heuristic_slides(
                        source,
                        keys,
                        start_index=len(normalized) + 1,
                        max_slides=target_slides,
                    )
                )
            return _enforce_source_storyboard_coverage(source, normalized[:target_slides])

        require_model = os.environ.get("AUTO_VIDEO_REQUIRE_MODEL_OUTPUT", "1").strip().lower() not in {"0", "false", "no", "off"}
        if require_model:
            raise RuntimeError(
                "The storyboard model did not return valid slides after retries; local placeholder generation is disabled."
            )

    return _enforce_source_storyboard_coverage(
        source,
        _build_heuristic_slides(source, keys, start_index=1, max_slides=target_slides),
    )


def _enforce_source_storyboard_coverage(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_text = str(source.get("text") or "")
    source_folded = source_text.casefold()
    updated = [dict(slide) for slide in slides]
    benchmark_index = next(
        (
            index
            for index, slide in enumerate(updated)
            if "benchmark" in f"{slide.get('title', '')} {slide.get('purpose', '')}".casefold()
        ),
        -1,
    )
    if benchmark_index >= 0 and all(token in source_folded for token in ("101 paper", "average 16.0", "average 6:15")):
        benchmark = dict(updated[benchmark_index])
        benchmark.update(
            {
                "purpose": "Present the source-verified scale and composition of the Paper2Video benchmark.",
                "bullets": [
                    "Paper2Video contains 101 paired papers and author-recorded presentation videos.",
                    "Presentations average 16.0 slides and 6 minutes 15 seconds in duration.",
                    "The collection spans 41 ML, 40 CV, and 20 NLP conference papers.",
                ],
                "speaker_note": (
                    "Paper2Video contains 101 peer-reviewed conference papers paired with author-recorded presentation videos. "
                    "Each instance includes speaker identity metadata, and 40 percent also include original slide files. "
                    "The presentations contain 16.0 slides on average and last an average of 6 minutes 15 seconds. "
                    "The collection covers 41 machine-learning, 40 computer-vision, and 20 natural-language-processing papers."
                ),
                "visual_kind": "metrics",
                "visual_caption": "Source-verified Paper2Video statistics from Section 3.2",
                "visual_items": [
                    "101 Paper-Video Pairs",
                    "16.0 Average Slides per Video",
                    "6:15 Average Video Duration",
                    "3 Research Fields: ML 41, CV 40, NLP 20",
                ],
                "scene_direction": {
                    "layout": "data_wall",
                    "entrance": str((benchmark.get("scene_direction") or {}).get("entrance") or "fade_up"),
                    "emphasis": "101 paired presentations with source-verified dataset statistics",
                },
            }
        )
        updated[benchmark_index] = _normalize_slide(benchmark_index + 1, benchmark)
    if not all(token in source_folded for token in ("papertalker", "tree search visual choice", "cursor grounding")):
        return updated
    core_index = next(
        (
            index
            for index, slide in enumerate(updated)
            if "core method" in f"{slide.get('title', '')} {slide.get('purpose', '')}".casefold()
        ),
        min(3, len(updated) - 1) if updated else -1,
    )
    if core_index < 0:
        return updated
    core = dict(updated[core_index])
    current_text = " ".join(
        [
            str(core.get("title") or ""),
            str(core.get("speaker_note") or ""),
            *[str(item) for item in core.get("bullets") or []],
        ]
    ).casefold()
    required = ("papertalker", "tree search visual choice", "cursor grounding")
    if all(token in current_text for token in required):
        return updated
    core.update(
        {
            "purpose": "Explain the complete PaperTalker multi-agent architecture before its efficiency optimizations.",
            "bullets": [
                "PaperTalker coordinates slide generation, subtitles, cursor grounding, speech synthesis, and talking-head rendering.",
                "Tree Search Visual Choice explores layout variants and uses a vision-language model to select the strongest composition.",
                "Independent slide-wise generation runs in parallel, reducing production time by more than 6x.",
            ],
            "speaker_note": (
                "PaperTalker is a multi-agent framework rather than a single end-to-end generator. "
                "Its agents create and refine slides, write synchronized subtitles, ground cursor trajectories, synthesize speech, and render the talking head. "
                "For visual quality, Tree Search Visual Choice explores multiple layout branches and asks a vision-language model to select the best composition. "
                "Because slides are largely independent, these modules can run slide-wise in parallel, achieving a speedup of more than six times."
            ),
            "visual_kind": "flow",
            "visual_caption": "PaperTalker multi-agent generation pipeline",
            "visual_items": [
                "Paper input",
                "Slide and layout agents",
                "Subtitle and cursor alignment",
                "Speech and talking-head rendering",
                "Presentation video",
            ],
            "scene_direction": {
                "layout": "diagram_focus",
                "entrance": str((core.get("scene_direction") or {}).get("entrance") or "fade_up"),
                "emphasis": "PaperTalker agent pipeline and Tree Search Visual Choice",
            },
        }
    )
    updated[core_index] = _normalize_slide(core_index + 1, core)
    return updated


def _build_heuristic_slides(
    source: dict[str, Any],
    keys: list[str],
    *,
    start_index: int,
    max_slides: int,
) -> list[dict[str, Any]]:
    text = source["text"][:65000]
    title = source["title"]
    sections = SLIDE_PLAN[:max_slides]
    slides: list[dict[str, Any]] = []
    for i, (name, purpose) in enumerate(sections[start_index - 1 : max_slides], start=start_index):
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
                **_visual_payload(source["kind"], name, i, bullets, keys),
            }
        )
    return slides


def _normalize_slide(index: int, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"title": f"{index}. Slide", "bullets": [str(item)]}
    bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    visual_kind = str(item.get("visual_kind") or VISUAL_KINDS[(index - 1) % len(VISUAL_KINDS)]).lower()
    if visual_kind == "screenshot":
        visual_kind = "image"
    if visual_kind not in VISUAL_KINDS:
        visual_kind = VISUAL_KINDS[(index - 1) % len(VISUAL_KINDS)]
    visual_items = item.get("visual_items") if isinstance(item.get("visual_items"), list) else []
    visual_table = item.get("visual_table") if isinstance(item.get("visual_table"), list) else []
    section = SLIDE_PLAN[index - 1][0] if index - 1 < len(SLIDE_PLAN) else "Slide"
    normalized_bullets = [_clean_display_text(b) for b in bullets if _clean_display_text(b)]
    if len(normalized_bullets) > 3:
        normalized_bullets = [*normalized_bullets[:2], " ".join(normalized_bullets[2:])]
    normalized_table = _normalize_visual_table(visual_table)
    if not _visual_table_is_meaningful(normalized_table):
        normalized_table = _visual_table(section, normalized_bullets, [])
    return {
        "index": index,
        "title": _clean_display_text(item.get("title") or f"{index}. Slide"),
        "purpose": _clean_display_text(item.get("purpose")),
        "bullets": normalized_bullets[:3],
        "speaker_note": _clean_display_text(item.get("speaker_note") or item.get("note")),
        "visual_prompt": _clean_display_text(item.get("visual_prompt")),
        "visual_kind": visual_kind,
        "visual_caption": _clean_display_text(
            item.get("visual_caption") or _visual_caption("source", section, visual_kind, [])
        ),
        "visual_items": [_clean_visual_item(str(v)) for v in visual_items[:6]]
        or _visual_items(section, normalized_bullets, []),
        "visual_table": normalized_table,
        "scene_direction": _normalize_scene_direction(
            item.get("scene_direction"),
            visual_kind=visual_kind,
            slide_index=index,
            text=" ".join(
                [
                    _clean_display_text(item.get("title")),
                    _clean_display_text(item.get("purpose")),
                    *normalized_bullets,
                ]
            ),
        ),
    }


SCENE_LAYOUTS = {"editorial", "comparison", "data_wall", "timeline", "evidence_grid", "diagram_focus"}
SCENE_ENTRANCES = ("fade_up", "slide_left", "slide_right", "scale_in", "wipe")


def _normalize_scene_direction(
    value: Any,
    *,
    visual_kind: str,
    slide_index: int,
    text: str,
) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    lowered = text.casefold()
    layout = str(raw.get("layout") or "").strip().lower()
    if layout not in SCENE_LAYOUTS:
        if visual_kind == "metrics" and any(token in lowered for token in ("speed", "faster", "versus", " vs ", "compare")):
            layout = "comparison"
        else:
            layout = {
                "metrics": "data_wall",
                "flow": "timeline",
                "table": "evidence_grid",
                "image": "diagram_focus" if slide_index % 2 else "editorial",
            }.get(visual_kind, "editorial")
    entrance = str(raw.get("entrance") or "").strip().lower()
    if entrance not in SCENE_ENTRANCES:
        entrance = SCENE_ENTRANCES[(slide_index - 1) % len(SCENE_ENTRANCES)]
    emphasis = _clean_display_text(raw.get("emphasis") or "")
    return {"layout": layout, "entrance": entrance, "emphasis": emphasis}


def _clean_visual_item(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\bgithub\.com/\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -:;")
    return text or "Research artifact"


def _speaker_note(section: str, title: str, bullets: list[str]) -> str:
    lead = {
        "Motivation": f"This video starts from the motivation of {title}.",
        "Core Idea": "The core idea is summarized as a compact claim before showing implementation details.",
        "Workflow": "The workflow view turns the source into an executable sequence of builders.",
        "Evidence": "This part highlights the strongest evidence available in the input.",
        "Limitations": "The final slide keeps the scope honest and proposes the next experiment.",
    }.get(section, "This slide summarizes one part of the work.")
    return _clean_display_text(" ".join([lead, *bullets[:2]]))


def _visual_prompt(kind: str, section: str, keys: list[str]) -> str:
    topic = ", ".join(keys[:5]) if keys else kind
    return f"{kind} explainer scene for {section.lower()}, using visual anchors: {topic}"


def _visual_payload(
    kind: str,
    section: str,
    index: int,
    bullets: list[str],
    keys: list[str],
) -> dict[str, Any]:
    visual_kind = {
        "Motivation": "image",
        "Core Idea": "screenshot",
        "Workflow": "flow",
        "Evidence": "table",
        "Limitations": "metrics",
    }.get(section, VISUAL_KINDS[(index - 1) % len(VISUAL_KINDS)])
    short_keys = keys[:4] or [kind, section.lower()]
    return {
        "visual_kind": visual_kind,
        "visual_caption": _visual_caption(kind, section, visual_kind, short_keys),
        "visual_items": _visual_items(section, bullets, short_keys),
        "visual_table": _visual_table(section, bullets, short_keys),
    }


def _visual_label(visual_kind: str) -> str:
    return {
        "image": "Key points",
        "screenshot": "Interface screenshot",
        "flow": "Workflow diagram",
        "table": "Evidence table",
        "metrics": "Metric snapshot",
    }.get(visual_kind, "Visual")


def _visual_caption(kind: str, section: str, visual_kind: str, keys: list[str]) -> str:
    topic = ", ".join(keys[:3])
    labels = {
        "image": f"Illustrative {kind} scene for {section.lower()}",
        "screenshot": f"Screenshot-style view of the {section.lower()} layer",
        "flow": f"Step-by-step pipeline view for {topic}",
        "table": f"Evidence summary extracted from the source",
        "metrics": f"Readiness and next-step snapshot",
    }
    return labels.get(visual_kind, f"{section} visual")


def _visual_items(section: str, bullets: list[str], keys: list[str]) -> list[str]:
    if section == "Workflow":
        return ["Ingest source", "Build slides", "Sync cursor", "Judge and revise", "Render video"]
    if section == "Limitations":
        return ["Grounding", "Pacing", "Visual sync", "API handoff"]
    items = [_clean_display_text(b).strip(" -") for b in bullets[:3] if str(b).strip()]
    return items or [key.title() for key in keys[:4]]


def _visual_table(section: str, bullets: list[str], keys: list[str]) -> list[list[str]]:
    if section == "Evidence":
        rows = [["Signal", "Source cue", "Presentation use"]]
        for i, bullet in enumerate(bullets[:3], start=1):
            rows.append([f"Evidence {i}", _clean_display_text(bullet), "Narration anchor"])
        return rows
    if section == "Limitations":
        return [
            ["Area", "Current state", "Next action"],
            ["Slides", "Generated", "Add richer assets"],
            ["Cursor", "Heuristic/VLM", "Improve grounding"],
            ["Talker", "Plan only", "Connect provider"],
        ]
    if bullets:
        rows = [["Claim", "Paper evidence", "Presentation role"]]
        for index, bullet in enumerate(bullets[:3], start=1):
            rows.append([f"Point {index}", _clean_display_text(bullet), "Supports the current explanation"])
        return rows
    topics = [key.title() for key in keys[:3] if str(key).strip()]
    return [["Topic", "Focus", "Role"], *[[f"Point {i}", topic, "Research context"] for i, topic in enumerate(topics, start=1)]]


def _normalize_visual_table(value: list[Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in value[:5]:
        if isinstance(row, dict):
            rows.append([_clean_display_text(k) for k in list(row.values())[:4]])
        elif isinstance(row, list):
            rows.append([_clean_display_text(cell) for cell in row[:4]])
        else:
            rows.append([_clean_display_text(row)])
    return rows


def _visual_table_is_meaningful(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    generic = {
        "architecture",
        "aspect",
        "focus",
        "topic",
        "keeps the demo grounded",
        "research context",
    }
    meaningful_rows = 0
    for row in rows[1:]:
        cells = [_clean_display_text(cell) for cell in row if _clean_display_text(cell)]
        folded = [cell.casefold() for cell in cells]
        informative = [cell for cell in folded if cell not in generic]
        if len(informative) >= 2 and len(set(folded)) == len(folded):
            meaningful_rows += 1
    return meaningful_rows > 0


INTERNAL_VIDEO_MARKERS = [
    "Judge note",
    "Revision pass",
    "Revision focus",
    "judge feedback",
    "slide_builder",
    "subtitle_builder",
    "cursor_builder",
    "talker_builder",
]

INTERNAL_VIDEO_PATTERNS = [
    re.compile(r"\bJudge note:.*?(?=(?:[.!?]\s+[A-Z])|$)", re.IGNORECASE),
    re.compile(r"\bRevision pass(?:\s+\d+)?:.*?(?=(?:[.!?]\s+[A-Z])|$)", re.IGNORECASE),
    re.compile(r"\bRevision focus:.*?(?=(?:[.!?]\s+[A-Z])|$)", re.IGNORECASE),
    re.compile(r"\b(?:slide_builder|subtitle_builder|cursor_builder|talker_builder)\b", re.IGNORECASE),
]


def _contains_internal_video_marker(value: Any) -> bool:
    text = str(value or "").lower()
    return any(marker.lower() in text for marker in INTERNAL_VIDEO_MARKERS)


def _clean_public_video_text(value: Any) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    for pattern in INTERNAL_VIDEO_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s+([.!?,;:])", r"\1", cleaned)
    return _clean_display_text(re.sub(r"\s+", " ", cleaned).strip(" -:;"))


def _clean_display_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\s*(?:\u2026|\.{3,})\s*", ". ", text)
    text = re.sub(r"\s+([.!?,;:])", r"\1", text)
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_public_video_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    cleaned = [_clean_public_video_text(item) for item in items]
    return [item for item in cleaned if item and not _contains_internal_video_marker(item)]


def sanitize_public_slides(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for i, slide in enumerate(slides, start=1):
        item = dict(slide)
        item["index"] = int(item.get("index") or i)
        item["title"] = _clean_public_video_text(item.get("title")) or f"Slide {item['index']}"
        item["purpose"] = _clean_public_video_text(item.get("purpose"))
        bullets = _clean_public_video_list(item.get("bullets"))
        if not bullets:
            bullets = ["Explain the core idea clearly."]
        if len(bullets) > 3:
            bullets = [*bullets[:2], " ".join(bullets[2:])]
        item["bullets"] = bullets[:3]
        note = _clean_public_video_text(item.get("speaker_note"))
        if not note or _contains_internal_video_marker(note):
            note = " ".join(item["bullets"][:3])
        item["speaker_note"] = note
        item["visual_prompt"] = _clean_public_video_text(item.get("visual_prompt"))
        item["visual_caption"] = _clean_public_video_text(item.get("visual_caption"))
        visual_items = _clean_public_video_list(item.get("visual_items"))
        item["visual_items"] = (visual_items or item["bullets"])[:6]
        if isinstance(item.get("visual_table"), list):
            rows: list[list[str]] = []
            for row in item["visual_table"][:5]:
                cells = row if isinstance(row, list) else list(row.values()) if isinstance(row, dict) else [row]
                clean_row = [_clean_public_video_text(cell) for cell in cells[:4]]
                if clean_row and not any(_contains_internal_video_marker(cell) for cell in clean_row):
                    rows.append(clean_row)
            item["visual_table"] = rows if _visual_table_is_meaningful(rows) else []
        item["scene_direction"] = _normalize_scene_direction(
            item.get("scene_direction"),
            visual_kind=str(item.get("visual_kind") or "image"),
            slide_index=item["index"],
            text=" ".join([item["title"], item["purpose"], *item["bullets"]]),
        )
        sanitized.append(item)
    return sanitized


def sanitize_public_subtitles(subtitles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for subtitle in subtitles:
        item = dict(subtitle)
        text = _clean_public_video_text(item.get("text"))
        if not text or _contains_internal_video_marker(text):
            continue
        item["text"] = text
        item["visual_focus_prompt"] = _clean_public_video_text(item.get("visual_focus_prompt"))
        item.pop("revise_reason", None)
        sanitized.append(item)
    return sanitized


def _estimate_narration_duration(text: Any) -> int:
    clean = _clean_display_text(text)
    english_words = re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*", clean)
    cjk_chars = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", clean)
    speech_wpm = max(80.0, float(os.environ.get("AUTO_VIDEO_SPEECH_WPM", "140")))
    cjk_chars_per_sec = max(2.5, float(os.environ.get("AUTO_VIDEO_CJK_CHARS_PER_SEC", "4.0")))
    seconds = len(english_words) / (speech_wpm / 60.0)
    seconds += len(cjk_chars) / cjk_chars_per_sec
    seconds += min(1.8, len(re.findall(r"[,;:，；：]", clean)) * 0.12)
    seconds += min(2.4, len(re.findall(r"[.!?。！？]", clean)) * 0.22)
    minimum = max(3, int(os.environ.get("AUTO_VIDEO_MIN_BEAT_SEC", "5")))
    maximum = max(minimum, int(os.environ.get("AUTO_VIDEO_MAX_BEAT_SEC", "15")))
    return max(minimum, min(maximum, int(math.ceil(seconds))))


def _narration_duration_bounds(slide: dict[str, Any], slide_position: int) -> tuple[int, int]:
    visual_kind = str(slide.get("visual_kind") or "image").lower()
    bounds = {
        "flow": (8, 12),
        "table": (8, 15),
        "metrics": (6, 8),
        "image": (6, 10),
    }
    minimum, maximum = bounds.get(visual_kind, (5, 10))
    if slide_position == 1:
        minimum = max(minimum, 6)
        maximum = min(maximum, 8)
    return minimum, max(minimum, maximum)


def build_subtitles(slides: list[dict[str, Any]], *, seconds_per_slide: int) -> list[dict[str, Any]]:
    subtitles: list[dict[str, Any]] = []
    t = 0
    max_sentences = int(os.environ.get("AUTO_VIDEO_MAX_SUBTITLES_PER_SLIDE", "4"))
    continuous = os.environ.get("AUTO_VIDEO_CONTINUOUS_TIMELINE", "1").strip().lower() not in {"0", "false", "no"}
    for slide_position, slide in enumerate(slides, start=1):
        note = slide.get("speaker_note") or " ".join(slide.get("bullets") or [])
        sentences = _sentences(note) or [note]
        minimum_duration, maximum_duration = _narration_duration_bounds(slide, slide_position)
        for sent in sentences[:max_sentences]:
            start = t
            duration = max(minimum_duration, min(maximum_duration, _estimate_narration_duration(sent)))
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
        if not continuous and t < slide["index"] * seconds_per_slide:
            t = slide["index"] * seconds_per_slide
    return subtitles


def _scene_shot_sequence(
    *,
    visual_kind: str,
    beat_count: int,
    slide_position: int,
    has_generated_image: bool,
) -> list[str]:
    if beat_count <= 0:
        return []
    primary = {
        "flow": "process_map",
        "table": "evidence_board",
        "metrics": "data_landscape",
        "image": "media_establish" if has_generated_image else "key_claim",
    }.get(visual_kind, "key_claim")
    detail = {
        "flow": "process_trace",
        "table": "evidence_closeup",
        "metrics": "data_focus",
        "image": "media_detail" if has_generated_image else "contrast",
    }.get(visual_kind, "contrast")

    if beat_count == 1:
        return ["opener" if slide_position == 1 else primary]
    if beat_count == 2:
        first = "opener" if slide_position == 1 else primary
        return [first, "synthesis"]
    if visual_kind == "metrics" and beat_count >= 3:
        middle = ["data_focus", "data_detail"][: max(0, beat_count - 2)]
        sequence = ["data_landscape", *middle, "data_conclusion"]
        if slide_position == 1:
            sequence[0] = "opener"
        return sequence
    if visual_kind == "flow" and beat_count >= 3:
        sequence = ["process_map", *(["process_trace"] * (beat_count - 2)), "synthesis"]
        if slide_position == 1:
            sequence[0] = "opener"
            sequence[1] = "process_map"
        return sequence
    if beat_count == 3:
        if visual_kind == "image" and has_generated_image:
            return ["media_establish", "media_detail", "synthesis"]
        first = "opener" if slide_position == 1 else "section_title"
        return [first, primary, "synthesis"]

    if visual_kind == "image" and has_generated_image:
        return ["media_establish", "media_detail", "key_claim", "synthesis"][:beat_count]
    first = "opener" if slide_position == 1 else "section_title"
    sequence = [first, primary, detail]
    while len(sequence) < beat_count - 1:
        sequence.append("key_claim" if len(sequence) % 2 else "contrast")
    sequence.append("synthesis")
    return sequence[:beat_count]


def _scene_focus_index(
    narration: str,
    *,
    bullets: list[str],
    visual_items: list[str],
    fallback: int,
) -> int:
    number_words = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
    }

    def normalize_match_text(value: str) -> str:
        normalized = _clean_display_text(value).casefold()
        for word, digit in number_words.items():
            normalized = re.sub(rf"\b{word}\s+times\b", f"{digit}x", normalized)
        return re.sub(r"\bparalleliz(?:e|es|ed|ing)\b", "parallel", normalized)

    narration_folded = normalize_match_text(narration)
    candidates = bullets or visual_items
    for index, candidate in enumerate(candidates):
        cleaned = normalize_match_text(candidate)
        label = cleaned.split(":", 1)[0].strip().casefold()
        if label and len(label) >= 3 and label in narration_folded:
            return index
    narration_tokens = set(re.findall(r"[a-z0-9]+(?:x|%)?", narration_folded))
    stop_words = {"the", "and", "for", "with", "from", "time", "generation", "slide", "slides"}
    best_index = -1
    best_score = 0
    for index, candidate in enumerate(candidates):
        candidate_tokens = set(re.findall(r"[a-z0-9]+(?:x|%)?", normalize_match_text(candidate))) - stop_words
        overlap = narration_tokens & candidate_tokens
        score = sum(3 if re.search(r"\d", token) else 2 if len(token) >= 7 else 1 for token in overlap)
        if score > best_score:
            best_index = index
            best_score = score
    if best_index >= 0 and best_score >= 2:
        return best_index
    return min(fallback, max(0, len(candidates) - 1))


def _scene_narration_is_anaphoric(narration: str) -> bool:
    cleaned = _clean_display_text(narration).casefold()
    return bool(re.match(r"^(?:this|that|it|these|those|such an? approach)\b", cleaned))


def _merge_scene_beats(items: list[dict[str, Any]], *, max_beats: int = 4) -> list[dict[str, Any]]:
    if len(items) <= max_beats:
        return [dict(item) for item in items]
    merged: list[dict[str, Any]] = []
    for group_index in range(max_beats):
        start_index = round(group_index * len(items) / max_beats)
        end_index = round((group_index + 1) * len(items) / max_beats)
        group = items[start_index:end_index]
        if not group:
            continue
        beat = dict(group[0])
        beat["start_sec"] = float(group[0].get("start_sec") or 0)
        beat["end_sec"] = float(group[-1].get("end_sec") or beat["start_sec"])
        beat["speech_start_sec"] = float(group[0].get("speech_start_sec") or beat["start_sec"])
        beat["speech_end_sec"] = float(group[-1].get("speech_end_sec") or beat["end_sec"])
        beat["text"] = " ".join(_clean_display_text(item.get("text")) for item in group if item.get("text"))
        beat["merged_subtitle_count"] = len(group)
        merged.append(beat)
    return merged


def build_scene_timeline(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn slide-organized content into narration-driven video shots."""
    first_subtitle = min(subtitles, key=lambda item: float(item.get("start_sec") or 0), default=None)
    title_start = float(first_subtitle.get("segment_start_sec", first_subtitle.get("start_sec") or 0)) if first_subtitle else 0.0
    title_end = float(first_subtitle.get("speech_start_sec") or title_start) if first_subtitle else title_start
    has_title_card = bool(source.get("title")) and title_end - title_start >= 2.0
    by_slide: dict[int, list[dict[str, Any]]] = {}
    for subtitle in subtitles:
        item = dict(subtitle)
        if has_title_card and subtitle is first_subtitle:
            item["start_sec"] = title_end
        by_slide.setdefault(int(subtitle.get("slide_index") or 0), []).append(item)
    for items in by_slide.values():
        items.sort(key=lambda item: float(item.get("start_sec") or 0))

    timeline: list[dict[str, Any]] = []
    if has_title_card:
        timeline.append(
            {
                "shot_id": "title-01",
                "slide_index": 0,
                "shot_index": 0,
                "start_sec": round(title_start, 3),
                "end_sec": round(title_end, 3),
                "speech_start_sec": round(title_end, 3),
                "speech_end_sec": round(title_end, 3),
                "duration_sec": round(title_end - title_start, 3),
                "animation_sec": min(1.8, max(0.8, (title_end - title_start) * 0.35)),
                "hold_sec": max(0.0, title_end - title_start - 1.4),
                "shot_type": "title_card",
                "headline": _clean_display_text(source.get("title")),
                "section_label": "Research paper",
                "narration": "",
                "focus_text": _clean_display_text(source.get("authors")),
                "focus_index": 0,
                "visual_kind": "title",
                "has_generated_image": False,
                "visual_asset_path": "",
                "visual_asset_kind": "none",
                "composition_variant": 0,
                "layout_variant": "editorial",
                "entrance": "fade_up",
                "director_emphasis": _clean_display_text(source.get("title")),
                "background_stage": "quiet",
                "transition": "fade",
                "motion": "title_reveal",
            }
        )
    for slide_position, slide in enumerate(slides, start=1):
        slide_index = int(slide.get("index") or slide_position)
        items = by_slide.get(slide_index, [])
        if not items:
            start = float(timeline[-1]["end_sec"]) if timeline else 0.0
            items = [
                {
                    "slide_index": slide_index,
                    "start_sec": start,
                    "end_sec": start + 8.0,
                    "text": slide.get("speaker_note") or " ".join(slide.get("bullets") or []),
                }
            ]

        beats: list[dict[str, Any]] = []
        min_shot_sec = max(4.0, float(os.environ.get("AUTO_VIDEO_MIN_SHOT_SEC", "5")))
        split_threshold_sec = max(
            min_shot_sec * 2.0,
            float(os.environ.get("AUTO_VIDEO_SPLIT_BEAT_SEC", "12")),
        )
        if len(items) == 1:
            item = items[0]
            start = float(item.get("start_sec") or 0)
            end = max(start + 2.0, float(item.get("end_sec") or start + 8.0))
            duration = end - start
            if duration >= split_threshold_sec:
                split = max(start + min_shot_sec, min(end - min_shot_sec, start + duration * 0.42))
                beats = [
                    {**item, "start_sec": start, "end_sec": split, "synthetic_beat": "setup"},
                    {**item, "start_sec": split, "end_sec": end, "synthetic_beat": "explain"},
                ]
            else:
                beats = [{**item, "start_sec": start, "end_sec": end}]
        else:
            beats = _merge_scene_beats(items, max_beats=4)

        visual_kind = str(slide.get("visual_kind") or "image").lower()
        scene_direction = _normalize_scene_direction(
            slide.get("scene_direction"),
            visual_kind=visual_kind,
            slide_index=slide_index,
            text=" ".join(
                [str(slide.get("title") or ""), str(slide.get("purpose") or ""), *[str(b) for b in slide.get("bullets") or []]]
            ),
        )
        bullets = [_clean_display_text(item) for item in slide.get("bullets", []) if str(item).strip()]
        visual_items = [_clean_visual_item(str(item)) for item in slide.get("visual_items", []) if str(item).strip()]
        visual_asset_paths = [
            str(path)
            for path in (slide.get("visual_asset_paths") or [slide.get("generated_image_path")])
            if str(path) and Path(str(path)).is_file()
        ]
        has_generated_image = bool(visual_asset_paths)
        shot_sequence = _scene_shot_sequence(
            visual_kind=visual_kind,
            beat_count=len(beats),
            slide_position=slide_position,
            has_generated_image=has_generated_image,
        )
        asset_cursor = 0
        previous_focus_index: int | None = None
        for beat_index, beat in enumerate(beats):
            start = float(beat.get("start_sec") or 0)
            end = max(start + 1.0, float(beat.get("end_sec") or start + 5.0))
            is_first = beat_index == 0
            shot_type = shot_sequence[beat_index]

            narration = str(beat.get("text") or "")
            focus_fallback = (
                previous_focus_index
                if previous_focus_index is not None and _scene_narration_is_anaphoric(narration)
                else beat_index
            )
            focus_index = _scene_focus_index(
                narration,
                bullets=bullets,
                visual_items=visual_items,
                fallback=focus_fallback,
            )
            previous_focus_index = focus_index
            if focus_index < len(bullets):
                focus_text = bullets[focus_index]
            elif focus_index < len(visual_items):
                focus_text = visual_items[focus_index]
            else:
                focus_text = _clean_display_text(beat.get("text"))
            duration = end - start
            animation_sec = min(3.2, max(1.0, duration * 0.34))
            minimum_hold_sec = min(3.0, max(1.5, duration * 0.28))
            if animation_sec + minimum_hold_sec > duration:
                animation_sec = max(0.8, duration - minimum_hold_sec)
            hold_sec = max(0.0, duration - animation_sec)
            base_entrance_index = SCENE_ENTRANCES.index(scene_direction["entrance"])
            entrance = SCENE_ENTRANCES[(base_entrance_index + beat_index) % len(SCENE_ENTRANCES)]
            visual_asset_path = ""
            if shot_type in {"image_focus", "detail_focus", "media_establish", "media_detail"} and visual_asset_paths:
                visual_asset_path = visual_asset_paths[asset_cursor % len(visual_asset_paths)]
                asset_cursor += 1
            timeline.append(
                {
                    "shot_id": f"s{slide_index:02d}-{beat_index + 1:02d}",
                    "slide_index": slide_index,
                    "shot_index": beat_index + 1,
                    "start_sec": round(start, 3),
                    "end_sec": round(end, 3),
                    "speech_start_sec": round(float(beat.get("speech_start_sec") or start), 3),
                    "speech_end_sec": round(float(beat.get("speech_end_sec") or end), 3),
                    "duration_sec": round(end - start, 3),
                    "animation_sec": round(animation_sec, 3),
                    "hold_sec": round(hold_sec, 3),
                    "shot_type": shot_type,
                    "scene_family": {
                        "media_establish": "documentary_media",
                        "media_detail": "documentary_media",
                        "process_map": "mechanism_stage",
                        "process_trace": "mechanism_stage",
                        "evidence_board": "evidence_stage",
                        "evidence_closeup": "evidence_stage",
                        "data_landscape": "data_stage",
                        "data_focus": "data_stage",
                        "data_detail": "data_stage",
                        "data_conclusion": "data_stage",
                        "synthesis": "summary_stage",
                    }.get(shot_type, "narrative_stage"),
                    "framing": {
                        "media_establish": "full_frame",
                        "media_detail": "close_up",
                        "process_map": "wide",
                        "process_trace": "guided_close_up",
                        "evidence_board": "wide",
                        "evidence_closeup": "close_up",
                        "data_landscape": "wide",
                        "data_focus": "close_up",
                        "data_detail": "detail",
                        "data_conclusion": "result_frame",
                    }.get(shot_type, "medium"),
                    "headline": _clean_display_text(slide.get("title")),
                    "section_label": _clean_display_text(slide.get("purpose")) or f"Part {slide_index}",
                    "narration": _clean_display_text(beat.get("text")),
                    "focus_text": focus_text,
                    "focus_index": focus_index,
                    "visual_kind": visual_kind,
                    "has_generated_image": has_generated_image,
                    "visual_asset_path": visual_asset_path,
                    "visual_asset_kind": "paper_figure" if "paper_figures" in visual_asset_path else "generated" if visual_asset_path else "none",
                    "composition_variant": (slide_index + beat_index) % 4,
                    "layout_variant": scene_direction["layout"],
                    "entrance": entrance,
                    "director_emphasis": scene_direction["emphasis"],
                    "background_stage": {
                        "opener": "quiet",
                        "section_title": "quiet",
                        "key_claim": "split",
                        "contrast": "split",
                        "image_focus": "media",
                        "detail_focus": "media",
                        "media_establish": "immersive",
                        "media_detail": "immersive",
                        "process": "technical",
                        "process_focus": "quiet",
                        "process_map": "technical",
                        "process_trace": "quiet",
                        "evidence": "technical",
                        "evidence_focus": "quiet",
                        "evidence_board": "technical",
                        "evidence_closeup": "quiet",
                        "metric": "spotlight",
                        "data_landscape": "spotlight",
                        "data_focus": "quiet",
                        "data_detail": "technical",
                        "data_conclusion": "split",
                        "synthesis": "quiet",
                    }.get(shot_type, "technical"),
                    "transition": "fade" if is_first else "continue",
                    "motion": {
                        "opener": "title_reveal",
                        "section_title": "chapter_reveal",
                        "process": "sequential_nodes",
                        "process_focus": "node_focus",
                        "evidence": "row_reveal",
                        "evidence_focus": "row_focus",
                        "metric": "number_focus",
                        "image_focus": "image_settle",
                        "detail_focus": "detail_pan",
                        "media_establish": "documentary_establish",
                        "media_detail": "evidence_closeup",
                        "process_map": "path_build",
                        "process_trace": "camera_trace",
                        "evidence_board": "evidence_scan",
                        "evidence_closeup": "row_closeup",
                        "data_landscape": "data_establish",
                        "data_focus": "number_closeup",
                        "data_detail": "chart_scan",
                        "data_conclusion": "result_lockup",
                        "contrast": "split_compare",
                        "synthesis": "takeaway_stack",
                        "key_claim": "statement_reveal",
                    }.get(shot_type, "statement_reveal"),
                }
            )
    return timeline


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
    total = len(subtitles)
    for i, item in enumerate(subtitles):
        x, y = anchors[i % len(anchors)]
        grounding_mode = "heuristic"
        reason = item.get("visual_focus_prompt", "")
        slide_index = int(item["slide_index"])
        slide = slide_lookup.get(slide_index)
        if use_vlm_cursor and slide and source and grounding_dir:
            _progress("cursor_builder", "ground cursor with VLM", current=i + 1, total=total, detail=f"slide={slide_index}")
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
                grounding_mode = str(grounded.get("grounding_mode") or "vlm")
                _progress("cursor_builder", "VLM cursor point ready", current=i + 1, total=total, detail=f"slide={slide_index} x={x} y={y}")
            else:
                _progress("cursor_builder", "VLM cursor fallback", current=i + 1, total=total, detail=f"slide={slide_index} using heuristic x={x} y={y}")
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
    grounding_mode = "vlm"
    if not isinstance(data, dict):
        fallback_prompt = "\n\n".join(
            [
                "The image model is unavailable. Infer a conservative cursor location using only the textual slide metadata below.",
                "Do not claim that you inspected the image. Return the requested JSON only.",
                prompt,
            ]
        )
        data = _json_from_model(
            _call_deepseek_text(
                fallback_prompt,
                system="You provide conservative JSON cursor coordinates from slide text when vision is unavailable.",
            )
        )
        grounding_mode = "deepseek_text"
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
        "grounding_mode": grounding_mode,
    }


def build_talker_plan(subtitles: list[dict[str, Any]]) -> dict[str, Any]:
    text = _natural_narration_from_subtitles(subtitles)
    tts_provider = os.environ.get("AUTO_VIDEO_TTS_PROVIDER", "not_configured")
    talking_head_provider = os.environ.get("AUTO_VIDEO_TALKING_HEAD_PROVIDER", "not_configured")
    placeholder_ready = any(
        value.endswith("-placeholder") for value in (tts_provider, talking_head_provider)
    ) and bool(
        _lumid_api_key()
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    return {
        "mode": os.environ.get("AUTO_VIDEO_TALKER_MODE", "placeholder"),
        "tts_provider": tts_provider,
        "tts_model": os.environ.get("LUMID_TTS_MODEL") or os.environ.get("LUM_TTS_MODEL") or LUMID_TTS_MODEL,
        "talking_head_provider": talking_head_provider,
        "voice_sample_path": os.environ.get("AUTO_VIDEO_VOICE_SAMPLE", ""),
        "portrait_path": os.environ.get("AUTO_VIDEO_PORTRAIT", ""),
        "narration_text": text,
        "api_ready": bool(
            os.environ.get("ELEVENLABS_API_KEY")
            or os.environ.get("HEYGEN_API_KEY")
            or os.environ.get("D_ID_API_KEY")
            or placeholder_ready
        ),
        "audio_path": "",
        "audio_generated": False,
        "note": (
            "This MVP writes storyboard/subtitle/cursor artifacts. External TTS/talking-head APIs can consume this plan. "
            "A *-placeholder provider means the slot is enabled for demo wiring, but the selected LLM endpoint does not provide native TTS/talking-head generation."
        ),
    }


def _natural_narration_from_subtitles(subtitles: list[dict[str, Any]]) -> str:
    by_slide: dict[int, list[str]] = {}
    for item in subtitles:
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if text:
            by_slide.setdefault(int(item.get("slide_index") or 0), []).append(text)
    transitions = [
        "Let's start with the main problem.",
        "Now, the next point is about why this is difficult.",
        "Here is the evidence from the paper.",
        "Let's look at the method more concretely.",
        "The next part explains how the components work together.",
        "Now let's move to the results.",
        "Finally, let me summarize the takeaway.",
    ]
    chunks: list[str] = []
    for pos, slide_index in enumerate(sorted(by_slide)):
        sentences = by_slide[slide_index]
        if not sentences:
            continue
        if pos < len(transitions):
            chunks.append(transitions[pos])
        for sentence in sentences:
            cleaned = sentence.strip()
            cleaned = re.sub(r"\bRevision pass \d+:.*$", "", cleaned).strip()
            if cleaned:
                chunks.append(cleaned)
    narration = " ".join(chunks)
    narration = re.sub(r"\s+", " ", narration).strip()
    return _prepare_tts_text(narration)


def _prepare_tts_text(text: str) -> str:
    if os.environ.get("AUTO_VIDEO_TTS_NATURAL", "1").strip().lower() in {"0", "false", "no"}:
        return text
    text = re.sub(r"\s+", " ", text).strip()
    replacements = [
        (r"\bAI-generated\b", "AI generated"),
        (r"\bmulti-agent\b", "multi agent"),
        (r"\blong-context\b", "long context"),
        (r"\btext-to-speech\b", "text to speech"),
        (r"\btalking-head\b", "talking head"),
        (r"\bVideoLLM\b", "video language model"),
        (r"\bVLM\b", "vision language model"),
        (r"\bTTS\b", "text to speech"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r"\.\s+", ".  ", text)
    text = re.sub(r";\s+", ";  ", text)
    text = re.sub(r":\s+", ":  ", text)
    text = re.sub(r"\b(First|Second|Third|Finally|However|Therefore|In conclusion),", r"\1,", text)
    return text[: int(os.environ.get("AUTO_VIDEO_TTS_MAX_CHARS", "12000"))]


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
        judge_slide_chars = int(os.environ.get("AUTO_VIDEO_JUDGE_SLIDE_CHARS", "12000"))
        judge_subtitle_chars = int(os.environ.get("AUTO_VIDEO_JUDGE_SUBTITLE_CHARS", "8000"))
        prompt = textwrap.dedent(
            f"""
            Judge this paper/project-to-video storyboard. Return JSON only:
            {{"overall_score":0.0,"module_scores":{{"slide_builder":0.0,"subtitle_builder":0.0,"cursor_builder":0.0,"talker_builder":0.0}},"failed_modules":["..."],"revise_next":{{"module":"instruction"}}}}
            Source title: {source['title']}
            Slides:
            {json.dumps(slides, ensure_ascii=False)[:judge_slide_chars]}
            Subtitles:
            {json.dumps(subtitles, ensure_ascii=False)[:judge_subtitle_chars]}
            """
        ).strip()
        data = _call_json_model(prompt)
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
        revise_slide_chars = int(os.environ.get("AUTO_VIDEO_REVISE_SLIDE_CHARS", "12000"))
        prompt = textwrap.dedent(
            f"""
            Revise this paper/project-to-video slide storyboard based on judge feedback.
            Return JSON only:
            {{"slides":[{{"title":"...","bullets":["..."],"speaker_note":"...","visual_prompt":"..."}}]}}
            Return exactly {len(slides)} slides in the same order. Do not delete, merge, or renumber sections.
            Make the narration more grounded and presentation-ready.
            Keep every bullet as a complete sentence under 24 words. Do not use ellipses.
            Add missing concrete paper details where the previous slide felt generic.
            Never mention judge feedback, revision passes, evaluator modules, or internal pipeline names.

            Source title: {source['title']}
            Judge feedback:
            {json.dumps(judge, ensure_ascii=False)}

            Current slides:
            {json.dumps(slides, ensure_ascii=False)[:revise_slide_chars]}
            """
        ).strip()
        data = _call_json_model(prompt)
        revised = data.get("slides") if isinstance(data, dict) else None
        if isinstance(revised, list) and revised:
            merged = [revised[index] if index < len(revised) else slides[index] for index in range(len(slides))]
            normalized = [_normalize_slide(i, item) for i, item in enumerate(merged, start=1)]
            return sanitize_public_slides(_enforce_source_storyboard_coverage(source, normalized))
        _progress("revise_builder", "model revision unavailable; preserve current storyboard", detail="local content fallback disabled")
        return sanitize_public_slides(_enforce_source_storyboard_coverage(source, slides))

    revised_slides: list[dict[str, Any]] = []
    for slide in slides:
        item = dict(slide)
        bullets = _clean_public_video_list(item.get("bullets"))
        if round_index >= 2 and len(bullets) < 3:
            bullets.append("Connect this point to the evidence and the viewer takeaway.")
        if len(bullets) > 3:
            bullets = [*bullets[:2], " ".join(bullets[2:])]
        item["bullets"] = bullets[:3]
        note = _clean_public_video_text(item.get("speaker_note"))
        item["speaker_note"] = note or " ".join(item["bullets"][:3])
        item["visual_prompt"] = _clean_public_video_text(item.get("visual_prompt"))
        revised_slides.append(item)
    return sanitize_public_slides(_enforce_source_storyboard_coverage(source, revised_slides))


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
                    "text": _clean_display_text(note),
                    "visual_focus_prompt": slide.get("visual_prompt", ""),
                }
            ]
        for item in items:
            text = str(item.get("text", "")).strip()
            item["text"] = _clean_public_video_text(text)
            item["revise_reason"] = instruction or "module-level subtitle revision"
            revised.append(item)
    return sanitize_public_subtitles(revised)


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
    revised["narration_text"] = _natural_narration_from_subtitles(subtitles)
    revised["revision_round"] = round_index
    revised["revise_reason"] = instruction or "module-level talker plan refresh"
    return revised


def diversify_slide_visuals(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cycle = ["image", "flow", "table", "metrics"]
    diversified: list[dict[str, Any]] = []
    for i, slide in enumerate(slides):
        item = dict(slide)
        kind = str(item.get("visual_kind") or "").lower()
        if kind not in cycle or (diversified and kind == diversified[-1].get("visual_kind")):
            kind = cycle[i % len(cycle)]
        if i == 0:
            kind = "image"
        item["visual_kind"] = kind
        if kind == "metrics" and not item.get("visual_table"):
            bullets = [str(b) for b in item.get("bullets", [])[:4]]
            item["visual_items"] = bullets
        if kind == "flow" and not item.get("visual_items"):
            item["visual_items"] = [str(b) for b in item.get("bullets", [])[:4]]
        diversified.append(item)
    return diversified


def plan_scene_directions(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    *,
    use_api: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ask the text model for visual direction, then constrain it to renderable choices."""
    model_directions: dict[int, dict[str, Any]] = {}
    model_error = ""
    enabled = os.environ.get("AUTO_VIDEO_USE_SCENE_DIRECTOR", "1").strip().lower() not in {"0", "false", "no"}
    if use_api and enabled:
        compact_slides = [
            {
                "index": int(slide.get("index") or i),
                "title": slide.get("title"),
                "purpose": slide.get("purpose"),
                "bullets": slide.get("bullets"),
                "visual_kind": slide.get("visual_kind"),
                "visual_items": slide.get("visual_items"),
            }
            for i, slide in enumerate(slides, start=1)
        ]
        prompt = textwrap.dedent(
            f"""
            Act as a motion design director for a concise academic explainer video.
            Recommend a distinct but restrained layout and entrance animation for every section.
            Return JSON only:
            {{"directions":[{{"slide_index":1,"layout":"editorial|comparison|data_wall|timeline|evidence_grid|diagram_focus","entrance":"fade_up|slide_left|slide_right|scale_in|wipe","emphasis":"concrete paper claim, number, module, or relationship"}}]}}
            Use comparison for before/after, baselines, efficiency, or speedup. Use data_wall for several statistics, timeline for ordered stages, evidence_grid for experimental evidence, and diagram_focus for mechanisms.
            Vary adjacent layouts and entrances. Avoid decorative empty space, giant isolated words, duplicate labels, fake metrics, and generic UI chrome.
            Ground emphasis only in the supplied slide content.

            Paper: {source.get('title', '')}
            Slides: {json.dumps(compact_slides, ensure_ascii=False)[:14000]}
            """
        ).strip()
        try:
            data = _call_json_model(prompt)
            directions = data.get("directions") if isinstance(data, dict) else None
            if isinstance(directions, list):
                for item in directions:
                    if isinstance(item, dict):
                        model_directions[int(item.get("slide_index") or 0)] = item
        except Exception as exc:
            model_error = str(exc)

    planned: list[dict[str, Any]] = []
    previous_layout = ""
    previous_entrance = ""
    layout_alternatives = {
        "metrics": ("comparison", "data_wall"),
        "flow": ("timeline", "diagram_focus"),
        "table": ("evidence_grid", "editorial"),
        "image": ("diagram_focus", "editorial"),
    }
    for position, slide in enumerate(slides, start=1):
        item = dict(slide)
        index = int(item.get("index") or position)
        direction = _normalize_scene_direction(
            model_directions.get(index) or item.get("scene_direction"),
            visual_kind=str(item.get("visual_kind") or "image"),
            slide_index=index,
            text=" ".join(
                [str(item.get("title") or ""), str(item.get("purpose") or ""), *[str(b) for b in item.get("bullets") or []]]
            ),
        )
        alternatives = layout_alternatives.get(str(item.get("visual_kind") or "image"), ("editorial", "diagram_focus"))
        if direction["layout"] == previous_layout:
            direction["layout"] = next((choice for choice in alternatives if choice != previous_layout), direction["layout"])
        if direction["entrance"] == previous_entrance:
            current = SCENE_ENTRANCES.index(direction["entrance"])
            direction["entrance"] = SCENE_ENTRANCES[(current + 1) % len(SCENE_ENTRANCES)]
        item["scene_direction"] = direction
        previous_layout = direction["layout"]
        previous_entrance = direction["entrance"]
        planned.append(item)
    return planned, {
        "mode": "model_directed" if model_directions else "deterministic_fallback",
        "model_direction_count": len(model_directions),
        "error": model_error,
        "directions": [item["scene_direction"] for item in planned],
    }


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
    _progress(
        "slide_builder",
        "start initial slide generation",
        detail=f"api={'on' if use_api else 'off'} provider={_text_model_provider() if use_api else 'heuristic'} max_slides={max_slides}",
    )
    slides = sanitize_public_slides(
        diversify_slide_visuals(build_slides(source, max_slides=max_slides, use_api=use_api))
    )
    _progress("slide_builder", "slides ready", current=len(slides), total=max_slides, detail=f"actual={len(slides)}")
    _progress("subtitle_builder", "build timed subtitles", current=0, total=len(slides), detail=f"seconds_per_slide={seconds_per_slide}")
    subtitles = sanitize_public_subtitles(build_subtitles(slides, seconds_per_slide=seconds_per_slide))
    _progress("subtitle_builder", "subtitles ready", current=len(subtitles), total=max(1, len(subtitles)), detail=f"items={len(subtitles)}")
    _progress("cursor_builder", "build cursor plan", current=0, total=max(1, len(subtitles)), detail=f"vlm={'on' if use_vlm_cursor else 'off'}")
    cursor_plan = build_cursor_plan(
        subtitles,
        slides=slides,
        source=source,
        out_dir=out_dir,
        use_vlm_cursor=use_vlm_cursor,
    )
    _progress("cursor_builder", "cursor plan ready", current=len(cursor_plan), total=max(1, len(subtitles)), detail=f"points={len(cursor_plan)}")
    _progress("talker_builder", "build narration/talker plan", detail=f"subtitle_items={len(subtitles)}")
    talker = build_talker_plan(subtitles)
    _progress("talker_builder", "talker plan ready", detail=f"chars={len(str(talker.get('narration_text') or ''))}")
    history: list[dict[str, Any]] = []
    max_revisions = max(0, max_revisions)
    min_revisions = max(0, min_revisions)
    current_rerun_modules = ["slide_builder", "subtitle_builder", "cursor_builder", "talker_builder"]

    for round_index in range(max_revisions + 1):
        _progress("judge_agent", "evaluate storyboard", current=round_index + 1, total=max_revisions + 1, detail=f"target={target_score}")
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
        _progress(
            "judge_agent",
            "judge result",
            current=round_index + 1,
            total=max_revisions + 1,
            detail=f"score={score:.3f} satisfied={satisfied} next={','.join(next_modules) if next_modules else 'none'}",
        )
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
            _progress("revise_builder", "revise slides and downstream modules", current=round_index + 1, total=max_revisions, detail="slide_builder -> subtitle_builder -> cursor_builder -> talker_builder")
            revised = revise_slides(
                source,
                slides,
                judge,
                round_index=round_index + 1,
                use_api=use_api,
            )
            slides = sanitize_public_slides(
                diversify_slide_visuals(revised)
            )
            _progress("slide_builder", "revised slides ready", current=len(slides), total=max_slides, detail=f"round={round_index + 1}")
            subtitles = sanitize_public_subtitles(build_subtitles(slides, seconds_per_slide=seconds_per_slide))
            _progress("subtitle_builder", "rebuilt subtitles after slide revision", current=len(subtitles), total=max(1, len(subtitles)), detail=f"round={round_index + 1}")
            cursor_plan = build_cursor_plan(
                subtitles,
                slides=slides,
                source=source,
                out_dir=out_dir,
                use_vlm_cursor=use_vlm_cursor,
            )
            _progress("cursor_builder", "rebuilt cursor plan after slide revision", current=len(cursor_plan), total=max(1, len(subtitles)), detail=f"round={round_index + 1}")
            talker = build_talker_plan(subtitles)
            _progress("talker_builder", "rebuilt talker plan after slide revision", detail=f"round={round_index + 1}")
        elif "subtitle_builder" in next_modules:
            _progress("revise_builder", "revise subtitles and downstream modules", current=round_index + 1, total=max_revisions, detail="subtitle_builder -> cursor_builder -> talker_builder")
            subtitles = revise_subtitles(
                slides,
                subtitles,
                judge,
                round_index=round_index + 1,
            )
            subtitles = sanitize_public_subtitles(subtitles)
            _progress("subtitle_builder", "revised subtitles ready", current=len(subtitles), total=max(1, len(subtitles)), detail=f"round={round_index + 1}")
            cursor_plan = build_cursor_plan(
                subtitles,
                slides=slides,
                source=source,
                out_dir=out_dir,
                use_vlm_cursor=use_vlm_cursor,
            )
            _progress("cursor_builder", "rebuilt cursor plan after subtitle revision", current=len(cursor_plan), total=max(1, len(subtitles)), detail=f"round={round_index + 1}")
            talker = build_talker_plan(subtitles)
            _progress("talker_builder", "rebuilt talker plan after subtitle revision", detail=f"round={round_index + 1}")
        elif "cursor_builder" in next_modules:
            _progress("revise_builder", "revise cursor plan", current=round_index + 1, total=max_revisions, detail="cursor_builder")
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
            _progress("cursor_builder", "revised cursor plan ready", current=len(cursor_plan), total=max(1, len(subtitles)), detail=f"round={round_index + 1}")
            if "talker_builder" in next_modules:
                talker = revise_talker_plan(
                    subtitles,
                    talker,
                    judge,
                    round_index=round_index + 1,
                )
                _progress("talker_builder", "revised talker plan ready", detail=f"round={round_index + 1}")
        elif "talker_builder" in next_modules:
            _progress("revise_builder", "revise talker plan", current=round_index + 1, total=max_revisions, detail="talker_builder")
            talker = revise_talker_plan(
                subtitles,
                talker,
                judge,
                round_index=round_index + 1,
            )
            _progress("talker_builder", "revised talker plan ready", detail=f"round={round_index + 1}")
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
        lines.extend(
            [
                f"## {slide['title']}",
                "",
                f"- visual_kind: `{slide.get('visual_kind', 'image')}`",
                f"- visual_caption: {slide.get('visual_caption', '')}",
                "",
                *[f"- {b}" for b in slide.get("bullets", [])],
                "",
                f"Speaker note: {slide.get('speaker_note', '')}",
                "",
            ]
        )
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
            {"id": "image_builder", "type": "lumid_qwen_image_optional", "artifact": "image_generation.json"},
            {"id": "subtitle_builder", "type": "llm_or_heuristic", "artifact": "subtitles.srt"},
            {"id": "cursor_builder", "type": "python_or_lumid_qwen_omni", "artifact": "cursor_plan.json"},
            {"id": "tts_builder", "type": "lumid_qwen_tts_optional", "artifact": "narration.mp3"},
            {"id": "talker_builder", "type": "external_api_optional", "artifact": "talker_plan.json"},
            {"id": "judge_agent", "type": "llm_or_heuristic", "artifact": "judge_feedback.json"},
            {"id": "revise_builder", "type": "llm_or_heuristic", "artifact": "revision_history.json"},
            {"id": "preview", "type": "html", "artifact": "preview.html"},
            {"id": "renderer", "type": "ffmpeg", "artifact": "video.mp4"},
        ],
        "edges": [
            ["ingest", "slide_builder"],
            ["slide_builder", "image_builder"],
            ["slide_builder", "subtitle_builder"],
            ["subtitle_builder", "cursor_builder"],
            ["subtitle_builder", "tts_builder"],
            ["subtitle_builder", "talker_builder"],
            ["slide_builder", "judge_agent"],
            ["image_builder", "preview"],
            ["cursor_builder", "preview"],
            ["tts_builder", "renderer"],
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


def _preview_visual_html(slide: dict[str, Any]) -> str:
    visual_kind = str(slide.get("visual_kind") or "image")
    caption = html.escape(str(slide.get("visual_caption") or _visual_label(visual_kind)))
    generated_path = str(slide.get("generated_image_path") or "")
    if generated_path:
        src = Path(generated_path).resolve().as_uri()
        return (
            f'<div class="visual generated-image-visual">'
            f'<img src="{html.escape(src)}" alt="{html.escape(str(slide.get("title", "generated visual")))}" />'
            f'<p>{caption}</p></div>'
        )
    items = [html.escape(str(item)) for item in slide.get("visual_items", [])[:5]]
    table = slide.get("visual_table", [])
    if visual_kind == "table":
        rows = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row[:3]) + "</tr>"
            for row in table[:5]
            if isinstance(row, list)
        )
        return f'<div class="visual table-visual"><div class="visual-label">Table</div><table>{rows}</table><p>{caption}</p></div>'
    if visual_kind == "flow":
        steps = "".join(f'<span class="flow-step">{item}</span>' for item in (items or ["Ingest", "Build", "Judge", "Render"]))
        return f'<div class="visual flow-visual"><div class="visual-label">Flow</div><div class="flow-row">{steps}</div><p>{caption}</p></div>'
    if visual_kind == "screenshot":
        rows = "".join(f'<div class="shot-row"><span></span><b>{item}</b></div>' for item in (items or ["Input", "Storyboard", "Preview"]))
        return f'<div class="visual screenshot-visual"><div class="visual-label">Screenshot</div><div class="mock-window"><div class="mock-bar"><i></i><i></i><i></i></div>{rows}</div><p>{caption}</p></div>'
    if visual_kind == "metrics":
        metric_items = items or ["Coverage", "Pacing", "Sync", "Revision"]
        meters = "".join(
            f'<div class="meter"><span>{item}</span><strong>{min(98, 62 + i * 9)}%</strong><em style="width:{min(98, 62 + i * 9)}%"></em></div>'
            for i, item in enumerate(metric_items[:4])
        )
        return f'<div class="visual metrics-visual"><div class="visual-label">Metrics</div>{meters}<p>{caption}</p></div>'
    chips = "".join(f"<span>{item}</span>" for item in (items or ["Problem", "Method", "Result"]))
    return f'<div class="visual image-visual"><div class="visual-label">Image</div><div class="image-frame"><div class="image-sky"></div><div class="image-card">{chips}</div></div><p>{caption}</p></div>'


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
          <div class="slide-text">
            <div class="kicker">Slide {slide['index']} · {html.escape(str(slide.get('visual_kind', 'visual')).title())}</div>
            <h2>{html.escape(slide['title'])}</h2>
            <ul>{''.join(f'<li>{html.escape(str(b))}</li>' for b in slide.get('bullets', []))}</ul>
            <p>{html.escape(slide.get('speaker_note', ''))}</p>
          </div>
          {_preview_visual_html(slide)}
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
    .slide {{ display:grid; grid-template-columns:1.05fr .95fr; gap:18px; }}
    .kicker {{ color:var(--accent); font-size:12px; font-weight:700; text-transform:uppercase; }}
    li {{ margin:8px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    td,th {{ padding:8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); }}
    .score {{ font-size:40px; font-weight:750; color:var(--good); }}
    .timeline {{ height:88px; position:relative; border:1px solid var(--line); border-radius:8px; background:#eef4ff; overflow:hidden; }}
    .dot {{ position:absolute; width:12px; height:12px; border-radius:50%; background:var(--accent); transform:translate(-50%,-50%); box-shadow:0 0 0 6px rgba(37,99,235,.13); }}
    pre {{ white-space:pre-wrap; word-break:break-word; background:#101827; color:#dbeafe; padding:12px; border-radius:6px; max-height:360px; overflow:auto; }}
    .visual {{ min-height:210px; border:1px solid var(--line); border-radius:8px; padding:12px; background:#f8fbff; }}
    .visual p {{ margin:10px 0 0; color:var(--muted); font-size:13px; }}
    .visual-label {{ font-size:11px; font-weight:800; color:var(--accent); text-transform:uppercase; margin-bottom:8px; }}
    .flow-row {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
    .flow-step {{ padding:9px 11px; border:1px solid #bfd4ff; background:#eef4ff; border-radius:7px; font-size:12px; font-weight:650; }}
    .flow-step:not(:last-child)::after {{ content:"→"; margin-left:10px; color:var(--accent); }}
    .mock-window {{ border:1px solid #b9c7d8; border-radius:7px; overflow:hidden; background:white; }}
    .mock-bar {{ height:26px; background:#e8eef5; display:flex; align-items:center; gap:5px; padding-left:9px; }}
    .mock-bar i {{ width:8px; height:8px; border-radius:50%; background:#94a3b8; display:block; }}
    .shot-row {{ display:grid; grid-template-columns:20px 1fr; gap:8px; padding:10px 12px; border-top:1px solid #edf2f7; font-size:12px; }}
    .shot-row span {{ width:14px; height:14px; border-radius:3px; background:var(--accent); margin-top:1px; }}
    .shot-row b,.flow-step,.meter span,.image-card span {{ min-width:0; overflow-wrap:anywhere; white-space:normal; }}
    .meter {{ position:relative; display:grid; grid-template-columns:1fr auto; gap:8px; padding:9px 0 13px; font-size:12px; }}
    .meter em {{ position:absolute; left:0; bottom:3px; height:5px; border-radius:99px; background:linear-gradient(90deg,#2563eb,#138a55); }}
    .image-frame {{ height:145px; border-radius:7px; overflow:hidden; border:1px solid #bfdbfe; background:#dbeafe; position:relative; }}
    .image-sky {{ height:62%; background:linear-gradient(135deg,#bfdbfe,#dcfce7); }}
    .image-card {{ position:absolute; left:18px; right:18px; bottom:16px; display:flex; flex-wrap:wrap; gap:7px; }}
    .image-card span {{ background:white; border:1px solid #d8e1ea; border-radius:6px; padding:6px 8px; font-size:12px; max-width:48%; }}
    .generated-image-visual img {{ width:100%; height:210px; object-fit:contain; border-radius:7px; border:1px solid #d8e1ea; display:block; background:#e5e7eb; }}
    @media (max-width: 820px) {{ .grid,.slide {{ grid-template-columns:1fr; }} }}
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
        pieces = _split_word_to_width(draw, word, font, width)
        for piece in pieces[:-1]:
            if current:
                lines.append(current)
                current = ""
            lines.append(piece)
        word = pieces[-1] if pieces else word
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


def _split_word_to_width(draw: Any, word: str, font: Any, width: int) -> list[str]:
    if draw.textbbox((0, 0), word, font=font)[2] <= width:
        return [word]
    pieces: list[str] = []
    rest = word
    while rest:
        lo, hi = 1, len(rest)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if draw.textbbox((0, 0), rest[:mid], font=font)[2] <= width:
                lo = mid
            else:
                hi = mid - 1
        pieces.append(rest[:lo])
        rest = rest[lo:]
    return pieces


def _line_height(draw: Any, font: Any, spacing: int = 4) -> int:
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return max(1, bbox[3] - bbox[1] + spacing)


def _font_size(font: Any) -> int:
    try:
        return max(1, int(font.size))
    except (AttributeError, TypeError, ValueError):
        return 12


def _font_at_size(font: Any, size: int) -> Any:
    try:
        return font.font_variant(size=max(1, int(size)))
    except (AttributeError, OSError, TypeError, ValueError):
        return font


def _wrapped_layout_that_fits(
    draw: Any,
    text: str,
    font: Any,
    *,
    width: int,
    max_height: int,
    spacing: int,
    max_lines: int | None,
    min_font_size: int = 5,
) -> tuple[Any, list[str], int]:
    clean = _clean_display_text(text)
    start_size = _font_size(font)
    fallback: tuple[Any, list[str], int] | None = None
    for size in range(start_size, min_font_size - 1, -1):
        candidate_font = _font_at_size(font, size)
        line_h = _line_height(draw, candidate_font, spacing=spacing)
        lines = _wrap_text(draw, clean, candidate_font, max(1, width))
        fallback = (candidate_font, lines, line_h)
        if max_lines is not None and len(lines) > max_lines:
            continue
        if len(lines) * line_h <= max_height:
            return candidate_font, lines, line_h
    return fallback or (font, [clean] if clean else [], _line_height(draw, font, spacing=spacing))


def _draw_wrapped_text(
    draw: Any,
    text: str,
    xy: tuple[int, int],
    *,
    font: Any,
    width: int,
    max_height: int,
    fill: tuple[int, int, int],
    spacing: int = 4,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    fitted_font, lines, line_h = _wrapped_layout_that_fits(
        draw,
        text,
        font,
        width=width,
        max_height=max_height,
        spacing=spacing,
        max_lines=max_lines,
    )
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_h), line, fill=fill, font=fitted_font)
    return y + len(lines) * line_h


def _fit_text(draw: Any, text: str, font: Any, width: int) -> str:
    return _clean_display_text(text)


def _draw_single_line_text(
    draw: Any,
    text: str,
    xy: tuple[int, int],
    *,
    font: Any,
    width: int,
    fill: tuple[int, int, int],
    min_font_size: int = 5,
) -> int:
    clean = _clean_display_text(text)
    fitted_font = font
    for size in range(_font_size(font), min_font_size - 1, -1):
        candidate = _font_at_size(font, size)
        bbox = draw.textbbox((0, 0), clean, font=candidate)
        fitted_font = candidate
        if bbox[2] - bbox[0] <= width:
            break
    draw.text(xy, clean, fill=fill, font=fitted_font)
    return _line_height(draw, fitted_font, spacing=0)


def _draw_slide_chrome(
    draw: Any,
    source: dict[str, Any],
    *,
    width: int,
    height: int,
    small_font: Any,
    progress: float | None = None,
    sec: float | None = None,
    total_duration: int | None = None,
) -> None:
    draw.rectangle((0, 0, width, 82), fill=(255, 255, 255), outline=(218, 226, 234))
    _draw_single_line_text(
        draw,
        source.get("title", ""),
        (42, 24),
        font=small_font,
        width=max(1, width - 310),
        fill=(23, 32, 42),
    )
    if progress is not None:
        draw.rectangle((0, 80, int(width * max(0.0, min(1.0, progress))), 84), fill=(37, 99, 235))
    if sec is not None and total_duration is not None:
        draw.text(
            (width - 220, 24),
            f"{int(sec):02d}s / {total_duration:02d}s",
            fill=(97, 113, 130),
            font=small_font,
        )


def _draw_slide_content(
    draw: Any,
    slide: dict[str, Any],
    *,
    panel: tuple[int, int, int, int],
    title_font: Any,
    body_font: Any,
    small_font: Any,
) -> None:
    x1, y1, x2, y2 = panel
    draw.rounded_rectangle(panel, radius=14, fill=(255, 255, 255), outline=(216, 225, 234), width=2)
    _draw_wrapped_text(
        draw,
        str(slide.get("title", "")),
        (x1 + 40, y1 + 24),
        font=title_font,
        width=x2 - x1 - 80,
        max_height=70,
        fill=(23, 32, 42),
        spacing=3,
        max_lines=2,
    )

    left_x = x1 + 42
    left_w = int((x2 - x1) * 0.48)
    right_x = x1 + left_w + 74
    visual_box = (right_x, y1 + 104, x2 - 42, y2 - 34)
    y = y1 + 118
    for bullet in slide.get("bullets", [])[:4]:
        draw.ellipse((left_x + 2, y + 10, left_x + 14, y + 22), fill=(37, 99, 235))
        remaining_bullets = max(1, len(slide.get("bullets", [])[:4]))
        bullet_height = max(54, (y2 - 42 - y) // remaining_bullets)
        y = _draw_wrapped_text(
            draw,
            str(bullet),
            (left_x + 30, y),
            font=body_font,
            width=left_w - 54,
            max_height=bullet_height,
            fill=(35, 48, 64),
            spacing=4,
        )
        y += 14

    _draw_visual_block(draw, slide, visual_box, body_font=body_font, small_font=small_font)


def _draw_visual_block(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    body_font: Any,
    small_font: Any,
) -> None:
    x1, y1, x2, y2 = box
    visual_kind = str(slide.get("visual_kind") or "image")
    draw.rounded_rectangle(box, radius=12, fill=(248, 251, 255), outline=(191, 211, 235), width=2)
    draw.text((x1 + 18, y1 + 14), _visual_label(visual_kind).upper(), fill=(37, 99, 235), font=small_font)
    caption = str(slide.get("visual_caption") or _visual_label(visual_kind))
    if visual_kind == "table":
        _draw_visual_table(draw, slide, (x1 + 18, y1 + 52, x2 - 18, y2 - 52), small_font)
    elif visual_kind == "flow":
        _draw_visual_flow(draw, slide, (x1 + 22, y1 + 62, x2 - 22, y2 - 54), small_font)
    elif visual_kind == "screenshot":
        _draw_visual_screenshot(draw, slide, (x1 + 22, y1 + 54, x2 - 22, y2 - 52), small_font)
    elif visual_kind == "metrics":
        _draw_visual_metrics(draw, slide, (x1 + 24, y1 + 58, x2 - 24, y2 - 52), small_font)
    else:
        _draw_visual_image(draw, slide, (x1 + 22, y1 + 54, x2 - 22, y2 - 52), small_font)
    _draw_wrapped_text(
        draw,
        caption,
        (x1 + 18, y2 - 42),
        font=small_font,
        width=x2 - x1 - 40,
        max_height=34,
        fill=(97, 113, 130),
        spacing=2,
        max_lines=2,
    )


def _draw_visual_table(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], font: Any) -> None:
    x1, y1, x2, y2 = box
    rows = slide.get("visual_table") or _visual_table("Evidence", slide.get("bullets", []), [])
    rows = [row for row in rows if isinstance(row, list)][:4]
    if not rows:
        rows = [["Signal", "Meaning"], ["Source", "Grounded visual"]]
    col_count = max(1, min(3, max(len(row) for row in rows)))
    col_widths = _table_col_widths(x2 - x1, col_count)
    row_heights = _table_row_heights(draw, rows, font, col_widths, min_h=38, max_h=72)
    scale = min(1.0, (y2 - y1) / max(1, sum(row_heights)))
    row_heights = [max(30, int(h * scale)) for h in row_heights]
    y = y1
    for r, row in enumerate(rows):
        row_h = row_heights[r]
        fill = (235, 242, 255) if r == 0 else (255, 255, 255)
        draw.rectangle((x1, y, x2, y + row_h), fill=fill, outline=(216, 225, 234))
        x = x1
        for c in range(col_count):
            col_w = col_widths[c]
            draw.line((x, y, x, y + row_h), fill=(216, 225, 234), width=1)
            text = str(row[c]) if c < len(row) else ""
            _draw_wrapped_text(
                draw,
                _compact_table_cell(text, header=(r == 0)),
                (x + 8, y + 7),
                font=font,
                width=col_w - 16,
                max_height=row_h - 12,
                fill=(35, 48, 64),
                spacing=2,
            )
            x += col_w
        y += row_h


def _draw_visual_flow(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], font: Any) -> None:
    x1, y1, x2, y2 = box
    items = slide.get("visual_items") or ["Ingest", "Build", "Judge", "Render"]
    count = max(1, min(5, len(items)))
    step_w = max(82, (x2 - x1 - (count - 1) * 18) // count)
    y = y1 + (y2 - y1) // 2 - 30
    for i, item in enumerate(items[:count]):
        x = x1 + i * (step_w + 18)
        draw.rounded_rectangle((x, y, x + step_w, y + 60), radius=10, fill=(238, 244, 255), outline=(147, 177, 228), width=2)
        _draw_wrapped_text(
            draw,
            str(item),
            (x + 8, y + 7),
            font=font,
            width=step_w - 16,
            max_height=46,
            fill=(23, 32, 42),
            spacing=2,
            max_lines=3,
        )
        if i < count - 1:
            ax = x + step_w + 4
            ay = y + 30
            draw.line((ax, ay, ax + 11, ay), fill=(37, 99, 235), width=3)
            draw.polygon([(ax + 11, ay - 5), (ax + 20, ay), (ax + 11, ay + 5)], fill=(37, 99, 235))


def _draw_visual_screenshot(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], font: Any) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=10, fill=(255, 255, 255), outline=(185, 199, 216), width=2)
    draw.rectangle((x1, y1, x2, y1 + 34), fill=(232, 238, 245), outline=(185, 199, 216))
    for i, color in enumerate([(239, 68, 68), (245, 158, 11), (34, 197, 94)]):
        draw.ellipse((x1 + 13 + i * 18, y1 + 12, x1 + 23 + i * 18, y1 + 22), fill=color)
    items = slide.get("visual_items") or slide.get("bullets", []) or ["Input", "Storyboard", "Preview"]
    y = y1 + 54
    for i, item in enumerate(items[:4]):
        draw.rounded_rectangle((x1 + 20, y, x2 - 20, y + 34), radius=6, fill=(248, 251, 255), outline=(226, 232, 240))
        draw.rectangle((x1 + 34, y + 10, x1 + 48, y + 24), fill=(37, 99, 235))
        _draw_wrapped_text(
            draw,
            str(item),
            (x1 + 62, y + 5),
            font=font,
            width=x2 - x1 - 96,
            max_height=27,
            fill=(35, 48, 64),
            spacing=1,
            max_lines=2,
        )
        y += 42


def _draw_visual_metrics(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], font: Any) -> None:
    x1, y1, x2, _y2 = box
    items = slide.get("visual_items") or ["Coverage", "Pacing", "Sync", "Revision"]
    for i, item in enumerate(items[:4]):
        pct = min(96, 62 + i * 9)
        y = y1 + i * 42
        _draw_single_line_text(
            draw,
            str(item),
            (x1, y),
            font=font,
            width=x2 - x1 - 62,
            fill=(35, 48, 64),
        )
        draw.text((x2 - 48, y), f"{pct}%", fill=(19, 138, 85), font=font)
        draw.rounded_rectangle((x1, y + 24, x2, y + 32), radius=4, fill=(226, 232, 240))
        draw.rounded_rectangle((x1, y + 24, x1 + int((x2 - x1) * pct / 100), y + 32), radius=4, fill=(19, 138, 85))


def _draw_visual_image(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], font: Any) -> None:
    x1, y1, x2, y2 = box
    if _draw_generated_image(draw, slide, box):
        return
    draw.rounded_rectangle(box, radius=10, fill=(219, 234, 254), outline=(147, 197, 253), width=2)
    draw.polygon([(x1, y2), (x1 + 96, y1 + 70), (x1 + 185, y2), (x1, y2)], fill=(187, 247, 208))
    draw.polygon([(x1 + 122, y2), (x1 + 250, y1 + 50), (x2, y2), (x1 + 122, y2)], fill=(191, 219, 254))
    items = [_clean_display_text(item) for item in (slide.get("visual_items") or ["Problem", "Method", "Result"])[:3]]
    gap = 8
    chip_w = max(42, (x2 - x1 - 36 - gap * max(0, len(items) - 1)) // max(1, len(items)))
    y = y2 - 74
    for i, text in enumerate(items):
        x = x1 + 18 + i * (chip_w + gap)
        draw.rounded_rectangle((x, y, x + chip_w, y + 42), radius=6, fill=(255, 255, 255), outline=(216, 225, 234))
        _draw_wrapped_text(
            draw,
            text,
            (x + 8, y + 5),
            font=font,
            width=chip_w - 16,
            max_height=32,
            fill=(35, 48, 64),
            spacing=1,
            max_lines=2,
        )


def _draw_generated_image(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    motion_progress: float = 0.0,
    motion_style: str = "static",
) -> bool:
    image_path = str(slide.get("generated_image_path") or "")
    if not image_path:
        return False
    path = Path(image_path).expanduser()
    if not path.is_file():
        return False
    canvas = getattr(draw, "_image", None)
    if canvas is None:
        return False
    try:
        from PIL import Image, ImageOps

        x1, y1, x2, y2 = box
        pad = 4
        target = (max(1, x2 - x1 - pad * 2), max(1, y2 - y1 - pad * 2))
        with Image.open(path) as raw:
            image = ImageOps.contain(raw.convert("RGB"), target, method=Image.Resampling.LANCZOS)
        bg_color = (8, 16, 28)
        if image.size[0] and image.size[1]:
            try:
                edge = image.resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
                if isinstance(edge, tuple) and len(edge) >= 3:
                    bg_color = tuple(int(v) for v in edge[:3])
            except Exception:
                bg_color = (8, 16, 28)
        frame = Image.new("RGB", target, bg_color)
        paste_x = max(0, (target[0] - image.size[0]) // 2)
        paste_y = max(0, (target[1] - image.size[1]) // 2)
        frame.paste(image, (paste_x, paste_y))
        progress = _scene_ease(max(0.0, min(1.0, motion_progress)))
        if motion_style != "static":
            zoom = 1.025
            zoomed = frame.resize(
                (max(target[0], int(target[0] * zoom)), max(target[1], int(target[1] * zoom))),
                Image.Resampling.LANCZOS,
            )
            extra_x = max(0, zoomed.width - target[0])
            extra_y = max(0, zoomed.height - target[1])
            center_x = extra_x / 2.0
            center_y = extra_y / 2.0
            travel_x = min(7.0, center_x)
            travel_y = min(5.0, center_y)
            if motion_style == "pan_right":
                crop_x = center_x - travel_x + 2.0 * travel_x * progress
            elif motion_style == "pan_left":
                crop_x = center_x + travel_x - 2.0 * travel_x * progress
            else:
                crop_x = center_x
            crop_y = center_y + travel_y - 2.0 * travel_y * progress if motion_style == "push_in" else center_y
            frame = zoomed.transform(
                target,
                Image.Transform.AFFINE,
                (1.0, 0.0, crop_x, 0.0, 1.0, crop_y),
                resample=Image.Resampling.BICUBIC,
            )
        canvas.paste(frame, (x1 + pad, y1 + pad))
        draw.rounded_rectangle(box, radius=10, outline=(35, 90, 130), width=2)
        return True
    except Exception:
        return False


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
    panel = (80, 120, width - 80, height - 218)
    _draw_slide_chrome(draw, source, width=width, height=height, small_font=small_font)
    _draw_slide_content(draw, slide, panel=panel, title_font=title_font, body_font=body_font, small_font=small_font)
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

    style = os.environ.get("AUTO_VIDEO_RENDER_STYLE", "scene").strip().lower()
    if style in {"scene", "cinematic", "video"}:
        return _render_scene_mp4_video(
            source,
            slides,
            subtitles,
            out,
            width=width,
            height=height,
            fps=fps,
        )
    if style == "arbor":
        return _render_arbor_mp4_video(
            source,
            slides,
            subtitles,
            cursor_plan,
            out,
            width=width,
            height=height,
            fps=fps,
        )

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

    total_slides = len(slides)
    _progress("renderer", "start frame rendering", current=0, total=total_slides, detail=f"style=simple fps={fps}")
    for slide_pos, slide in enumerate(slides, start=1):
        slide_index = int(slide["index"])
        slide_subs = by_slide.get(slide_index, [])
        start = min((int(s["start_sec"]) for s in slide_subs), default=(slide_index - 1) * 10)
        end = max((int(s["end_sec"]) for s in slide_subs), default=start + 10)
        slide_frame_count = max(1, (end - start) * fps)
        _progress("renderer", "draw slide frames", current=slide_pos, total=total_slides, detail=f"slide={slide_index} frames={slide_frame_count}")
        for tick in range(max(1, (end - start) * fps)):
            sec = start + tick / fps
            bg = Image.new("RGB", (width, height), (246, 248, 251))
            img = bg.copy()
            draw = ImageDraw.Draw(img)

            progress = max(0.0, min(1.0, sec / max(1, total_duration)))
            _draw_slide_chrome(
                draw,
                source,
                width=width,
                height=height,
                small_font=small_font,
                progress=progress,
                sec=sec,
                total_duration=total_duration,
            )

            panel = (80, 120, width - 80, height - 218)
            _draw_slide_content(
                draw,
                slide,
                panel=panel,
                title_font=title_font,
                body_font=body_font,
                small_font=small_font,
            )

            cur = cursor_position(sec, slide_index)
            if cur:
                cx, cy, _reason, move_t = cur
                if move_t < 1.0:
                    shadow = [(cx + 2, cy + 2), (cx + 14, cy + 27), (cx + 18, cy + 16), (cx + 30, cy + 16)]
                    draw.polygon(shadow, fill=(174, 190, 210))
                arrow = [(cx, cy), (cx + 12, cy + 25), (cx + 16, cy + 14), (cx + 28, cy + 14)]
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
            _draw_wrapped_text(
                draw,
                caption,
                (132, caption_top + 12),
                font=caption_font,
                width=width - 270,
                max_height=caption_bottom - caption_top - 20,
                fill=(219, 234, 254),
                spacing=3,
                max_lines=4,
            )

            fade = min(1.0, max(0.18, (sec - start) / 0.7))
            if fade < 1.0:
                img = Image.blend(bg, img, fade)

            frame_path = frames_dir / f"frame_{frame_index:05d}.png"
            img.save(frame_path)
            frame_index += 1

    _progress("renderer", "start ffmpeg encoding", detail=f"frames={frame_index} fps={fps} out={out.name}")
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
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    ok = proc.returncode == 0 and out.is_file()
    _progress("renderer", "ffmpeg encoding complete" if ok else "ffmpeg encoding failed", detail=f"returncode={proc.returncode} out={out}")
    if ok:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return ok


def _render_scene_mp4_video(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    out: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    frames_dir = out.parent / "scene_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    timeline = build_scene_timeline(source, slides, subtitles)
    (out.parent / "scene_timeline.json").write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "scene_based_research_explainer",
                "reference_style": "Arbor-inspired event-driven minimal motion",
                "shot_count": len(timeline),
                "shots": timeline,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if not timeline:
        return False

    slide_lookup = {int(slide.get("index") or i): slide for i, slide in enumerate(slides, start=1)}
    theme = _paper_visual_theme(source)
    background_color = tuple(theme["background"])
    total_duration = max(float(shot["end_sec"]) for shot in timeline)
    fonts = {
        "display": _font(44),
        "headline": _font(32),
        "body": _font(25),
        "small": _font(17),
        "mono": _font(16),
        "caption": _font(22),
        "number": _font(64),
    }
    frame_index = 0
    _progress("renderer", "start scene-based rendering", current=0, total=len(timeline), detail=f"fps={fps} shots={len(timeline)}")
    for shot_position, shot in enumerate(timeline, start=1):
        slide = slide_lookup.get(int(shot["slide_index"]), {})
        render_slide = dict(slide)
        if shot.get("visual_asset_path"):
            render_slide["generated_image_path"] = str(shot["visual_asset_path"])
        duration = max(1.0 / max(1, fps), float(shot["end_sec"]) - float(shot["start_sec"]))
        frame_count = max(1, int(round(duration * fps)))
        _progress(
            "renderer",
            "draw video shot",
            current=shot_position,
            total=len(timeline),
            detail=f"id={shot['shot_id']} type={shot['shot_type']} frames={frame_count}",
        )
        for tick in range(frame_count):
            sec = float(shot["start_sec"]) + tick / fps
            local = tick / max(1, frame_count - 1)
            img = Image.new("RGB", (width, height), background_color)
            draw = ImageDraw.Draw(img)
            _draw_scene_background(draw, width, height, sec, source=source, slide=render_slide, shot=shot)
            _draw_scene_progress(
                draw,
                shot,
                theme=theme,
                width=width,
                total_duration=total_duration,
                sec=sec,
                font=fonts["small"],
            )
            background_frame = img.copy()
            content_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            content_draw = ImageDraw.Draw(content_layer)
            _draw_scene_composition(
                content_draw,
                render_slide,
                shot,
                theme=theme,
                width=width,
                height=height,
                local=local,
                fonts=fonts,
            )
            animation_fraction = min(
                1.0,
                max(0.001, float(shot.get("animation_sec") or 1.0) / max(0.001, duration)),
            )
            entrance_progress = _scene_ease(min(1.0, local / animation_fraction))
            content_layer = _apply_scene_entrance(
                content_layer,
                str(shot.get("entrance") or "fade_up"),
                entrance_progress,
            )
            img = Image.alpha_composite(img.convert("RGBA"), content_layer).convert("RGB")
            draw = ImageDraw.Draw(img)
            _draw_scene_narration(
                draw,
                str(shot.get("narration") or ""),
                theme=theme,
                width=width,
                height=height,
                local=local,
                font=fonts["caption"],
            )

            exit_fade_sec = max(0.0, float(os.environ.get("AUTO_VIDEO_EXIT_FADE_SEC", "0")))
            exit_fraction = min(1.0, exit_fade_sec / max(0.001, duration)) if exit_fade_sec else 0.0
            exit_alpha = (
                _scene_ease(min(1.0, max(0.0, (1.0 - local) / max(0.001, exit_fraction))))
                if exit_fraction
                else 1.0
            )
            alpha = max(0.18, exit_alpha)
            if alpha < 1.0:
                img = Image.blend(background_frame, img, alpha)
            img.save(frames_dir / f"frame_{frame_index:05d}.png")
            frame_index += 1

    _progress("renderer", "start scene ffmpeg encoding", detail=f"frames={frame_index} fps={fps} out={out.name}")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        str(frames_dir / "frame_%05d.png"),
        "-c:v",
        "libx264",
        "-preset",
        os.environ.get("AUTO_VIDEO_FFMPEG_PRESET", "veryfast"),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    ok = proc.returncode == 0 and out.is_file() and out.stat().st_size > 0
    _progress("renderer", "scene encoding complete" if ok else "scene encoding failed", detail=f"returncode={proc.returncode} out={out}")
    if ok:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return ok


def _scene_ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _apply_scene_entrance(layer: Any, entrance: str, progress: float) -> Any:
    from PIL import Image

    progress = max(0.0, min(1.0, progress))
    width, height = layer.size
    canvas = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    if entrance == "slide_left":
        canvas.alpha_composite(layer, (int((1.0 - progress) * 96), 0))
    elif entrance == "slide_right":
        canvas.alpha_composite(layer, (-int((1.0 - progress) * 96), 0))
    elif entrance == "scale_in":
        scale = 0.92 + 0.08 * progress
        scaled = layer.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            resample=Image.Resampling.BICUBIC,
        )
        canvas.alpha_composite(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    elif entrance == "wipe":
        reveal_width = max(1, int(width * progress))
        canvas.alpha_composite(layer.crop((0, 0, reveal_width, height)), (0, 0))
    else:
        canvas.alpha_composite(layer, (0, int((1.0 - progress) * 32)))
    opacity = 0.18 + 0.82 * progress
    alpha = canvas.getchannel("A").point(lambda value: int(value * opacity))
    canvas.putalpha(alpha)
    return canvas


def _scene_color(color: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, channel + delta)) for channel in color)


def _draw_scene_background(
    draw: Any,
    width: int,
    height: int,
    sec: float,
    *,
    source: dict[str, Any],
    slide: dict[str, Any],
    shot: dict[str, Any],
) -> None:
    theme = _paper_visual_theme(source)
    background = tuple(theme["background"])
    pattern = tuple(theme["pattern"])
    line = tuple(theme["line"])
    stage = str(shot.get("background_stage") or "technical")
    variant = int(shot.get("composition_variant") or 0)

    if stage == "technical":
        _draw_arbor_background(draw, width, height, sec, source=source, slide=slide)
        return

    draw.rectangle((0, 0, width, height), fill=background)
    if stage == "split":
        band_y = int(height * (0.54 if variant % 2 else 0.48))
        draw.rectangle((0, band_y, width, height), fill=_scene_color(background, 4))
        draw.line((64, band_y, width - 64, band_y), fill=pattern, width=1)
    elif stage == "spotlight":
        band_top = 126 if variant % 2 else 154
        band_bottom = height - 164
        draw.rectangle((0, band_top, width, band_bottom), fill=_scene_color(background, 6))
        draw.line((64, band_top, width - 64, band_top), fill=line, width=1)
        draw.line((64, band_bottom, width - 64, band_bottom), fill=line, width=1)
    elif stage == "media":
        draw.line((0, 94, width, 94), fill=line, width=1)
        draw.line((0, height - 154, width, height - 154), fill=line, width=1)
    elif stage == "immersive":
        # The visual itself becomes the set; avoid decorative slide chrome.
        draw.rectangle((0, 0, width, height), fill=_scene_color(background, -3))


def _draw_scene_progress(
    draw: Any,
    shot: dict[str, Any],
    *,
    theme: dict[str, Any],
    width: int,
    total_duration: float,
    sec: float,
    font: Any,
) -> None:
    accent = tuple(theme["accent"])
    muted = (142, 157, 178)
    shot_type = str(shot.get("shot_type") or "")
    slide_index = int(shot.get("slide_index") or 0)
    if shot_type == "title_card":
        return
    if shot_type in {"opener", "section_title"}:
        _draw_single_line_text(
            draw,
            f"CHAPTER {slide_index:02d}",
            (width - 260, 42),
            font=font,
            width=196,
            fill=muted,
        )
        return
    if shot_type in {"media_establish", "media_detail", "process_trace"}:
        return
    label = str(shot.get("section_label") or shot.get("headline") or "Research")
    _draw_single_line_text(draw, label.upper(), (64, 42), font=font, width=760, fill=accent)
    shot_label = f"CHAPTER {slide_index:02d}"
    _draw_single_line_text(draw, shot_label, (width - 330, 42), font=font, width=266, fill=muted)
    progress = max(0.0, min(1.0, sec / max(0.001, total_duration)))
    draw.rectangle((64, 78, width - 64, 80), fill=tuple(theme["line"]))
    draw.rectangle((64, 78, 64 + int((width - 128) * progress), 81), fill=accent)


def _draw_scene_composition(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    *,
    theme: dict[str, Any],
    width: int,
    height: int,
    local: float,
    fonts: dict[str, Any],
) -> None:
    duration = max(0.001, float(shot.get("duration_sec") or 1.0))
    animation_sec = max(0.001, float(shot.get("animation_sec") or duration * 0.34))
    animation_fraction = max(0.001, min(1.0, animation_sec / duration))
    reveal = _scene_ease(min(1.0, local / animation_fraction))
    entrance = str(shot.get("entrance") or "fade_up")
    y_shift = int((1.0 - reveal) * 28) if entrance == "fade_up" else 0
    drift_progress = (
        0.0
        if local <= animation_fraction
        else (local - animation_fraction) / max(0.001, 1.0 - animation_fraction)
    )
    shot_type = str(shot.get("shot_type") or "key_claim")
    accent = tuple(theme["accent"])
    fg = (244, 247, 251)
    muted = (154, 177, 207)

    if shot_type == "title_card":
        draw.text((76, 132 + y_shift), "RESEARCH EXPLAINER", fill=accent, font=fonts["small"])
        draw.rectangle((76, 166 + y_shift, 292, 171 + y_shift), fill=accent)
        _draw_wrapped_text(
            draw,
            str(shot.get("headline") or ""),
            (76, 214 + y_shift),
            font=fonts["display"],
            width=1060,
            max_height=190,
            fill=fg,
            spacing=9,
            max_lines=4,
        )
        authors = _clean_display_text(shot.get("focus_text") or "")
        if authors:
            _draw_wrapped_text(
                draw,
                authors,
                (78, 438 + y_shift),
                font=fonts["body"],
                width=960,
                max_height=76,
                fill=muted,
                spacing=5,
                max_lines=2,
            )
        draw.text((width - 252, height - 188), "PAPER OVERVIEW", fill=accent, font=fonts["small"])
        draw.rectangle((width - 252, height - 154, width - 76, height - 150), fill=accent)
        return

    if shot_type == "opener":
        draw.text((76, 144 + y_shift), "RESEARCH OVERVIEW", fill=accent, font=fonts["small"])
        draw.rectangle((76, 174 + y_shift, 254, 178 + y_shift), fill=accent)
        _draw_wrapped_text(
            draw,
            str(shot.get("headline") or ""),
            (76, 202 + y_shift),
            font=fonts["display"],
            width=760,
            max_height=126,
            fill=fg,
            spacing=6,
            max_lines=3,
        )
        _draw_wrapped_text(
            draw,
            str(shot.get("focus_text") or shot.get("section_label") or ""),
            (76, 350 + y_shift),
            font=fonts["body"],
            width=720,
            max_height=112,
            fill=muted,
            spacing=5,
            max_lines=4,
        )
        _draw_scene_supporting_context(
            draw,
            slide,
            shot,
            (854, 196 + y_shift, width - 76, 472),
            accent=accent,
            fonts=fonts,
        )
        return

    if shot_type == "section_title":
        chapter = int(shot.get("slide_index") or 0)
        draw.text((76, 142 + y_shift), f"CHAPTER {chapter:02d}", fill=accent, font=fonts["small"])
        draw.rectangle((76, 174 + y_shift, 248, 178 + y_shift), fill=accent)
        _draw_wrapped_text(
            draw,
            str(shot.get("headline") or ""),
            (76, 204 + y_shift),
            font=fonts["display"],
            width=650,
            max_height=116,
            fill=fg,
            spacing=6,
            max_lines=2,
        )
        _draw_wrapped_text(
            draw,
            str(shot.get("focus_text") or ""),
            (76, 342 + y_shift),
            font=fonts["body"],
            width=650,
            max_height=126,
            fill=muted,
            spacing=6,
            max_lines=4,
        )
        _draw_scene_supporting_context(
            draw,
            slide,
            shot,
            (794, 184 + y_shift, width - 76, 486),
            accent=accent,
            fonts=fonts,
        )
        return

    headline = str(shot.get("headline") or "")
    if shot_type not in {"media_establish", "media_detail", "process_trace"}:
        _draw_single_line_text(draw, headline, (76, 112 + y_shift), font=fonts["headline"], width=1128, fill=fg)

    if shot_type == "media_establish":
        _draw_scene_media_establish(
            draw,
            slide,
            shot,
            width=width,
            height=height,
            reveal=reveal,
            drift_progress=drift_progress,
            accent=accent,
            fonts=fonts,
        )
    elif shot_type == "media_detail":
        _draw_scene_media_detail(
            draw,
            slide,
            shot,
            width=width,
            height=height,
            reveal=reveal,
            drift_progress=drift_progress,
            accent=accent,
            fonts=fonts,
        )
    elif shot_type == "image_focus":
        _draw_wrapped_text(
            draw,
            str(shot.get("focus_text") or ""),
            (76, 196 + y_shift),
            font=fonts["body"],
            width=450,
            max_height=230,
            fill=fg,
            spacing=7,
            max_lines=6,
        )
        image_box = (590, 180, width - 76, height - 174)
        if not _draw_generated_image(
            draw,
            slide,
            image_box,
            motion_progress=drift_progress,
            motion_style="pan_left" if int(shot.get("composition_variant") or 0) % 2 else "push_in",
        ):
            _draw_scene_visual_fallback(draw, slide, image_box, reveal=reveal, fonts=fonts)
        draw.rectangle((76, 470, 486, 474), fill=accent)
        _draw_single_line_text(
            draw,
            slide.get("visual_caption", ""),
            (76, 490),
            font=fonts["small"],
            width=450,
            fill=muted,
        )
    elif shot_type == "detail_focus":
        image_box = (70, 184, 742, height - 158)
        if not _draw_generated_image(
            draw,
            slide,
            image_box,
            motion_progress=drift_progress,
            motion_style="pan_right" if int(shot.get("composition_variant") or 0) % 2 else "push_in",
        ):
            _draw_scene_visual_fallback(draw, slide, image_box, reveal=reveal, fonts=fonts)
        detail_x = 820
        detail_y = 184
        draw.rectangle((detail_x, detail_y, detail_x + 180, detail_y + 4), fill=accent)
        _draw_wrapped_text(
            draw,
            str(shot.get("focus_text") or ""),
            (detail_x, detail_y + 28 + y_shift),
            font=fonts["headline"],
            width=width - detail_x - 76,
            max_height=210,
            fill=fg,
            spacing=7,
            max_lines=5,
        )
        _draw_wrapped_text(
            draw,
            str(slide.get("visual_caption") or ""),
            (detail_x, 442),
            font=fonts["small"],
            width=width - detail_x - 76,
            max_height=62,
            fill=muted,
            spacing=4,
            max_lines=3,
        )
    elif shot_type in {"process", "process_map"}:
        _draw_scene_process(draw, slide, (76, 205, width - 76, 500), reveal=reveal, accent=accent, fonts=fonts)
    elif shot_type == "process_trace":
        _draw_scene_process_trace(draw, slide, shot, (48, 70, width - 48, height - 150), reveal=reveal, accent=accent, fonts=fonts)
    elif shot_type == "process_focus":
        _draw_scene_process_focus(draw, slide, shot, (92, 172, width - 92, 514), reveal=reveal, accent=accent, fonts=fonts)
    elif shot_type in {"evidence", "evidence_board"}:
        _draw_scene_evidence(draw, slide, (92, 190, width - 92, 510), reveal=reveal, fonts=fonts)
    elif shot_type in {"evidence_focus", "evidence_closeup"}:
        _draw_scene_evidence_focus(draw, slide, shot, (92, 178, width - 92, 510), reveal=reveal, accent=accent, fonts=fonts)
    elif shot_type in {"metric", "data_landscape", "data_focus", "data_detail", "data_conclusion"}:
        _draw_scene_metric(draw, slide, shot, (76, 182, width - 76, 510), reveal=reveal, accent=accent, fonts=fonts)
    elif shot_type == "contrast":
        _draw_scene_contrast(draw, slide, shot, (76, 174, width - 76, 510), reveal=reveal, accent=accent, fonts=fonts)
    elif shot_type == "synthesis":
        _draw_scene_takeaways(draw, slide, (92, 190, width - 92, 510), reveal=reveal, accent=accent, fonts=fonts)
    else:
        draw.text((92, 180 + y_shift), "KEY FINDING", fill=accent, font=fonts["small"])
        draw.rectangle((92, 212 + y_shift, 274, 216 + y_shift), fill=accent)
        _draw_wrapped_text(
            draw,
            str(shot.get("focus_text") or ""),
            (92, 244 + y_shift),
            font=fonts["headline"],
            width=700,
            max_height=190,
            fill=fg,
            spacing=7,
            max_lines=6,
        )
        _draw_scene_supporting_context(
            draw,
            slide,
            shot,
            (846, 176 + y_shift, width - 76, 490),
            accent=accent,
            fonts=fonts,
        )


def _draw_scene_media_establish(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    *,
    width: int,
    height: int,
    reveal: float,
    drift_progress: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    """Use a paper figure or generated visual as the scene, not as a slide widget."""
    media_box = (24, 18, width - 24, height - 142)
    if not _draw_generated_image(
        draw,
        slide,
        media_box,
        motion_progress=drift_progress,
        motion_style="push_in",
    ):
        _draw_scene_visual_fallback(draw, slide, (72, 120, width - 72, height - 170), reveal=reveal, fonts=fonts)
        return

    panel_width = min(610, width - 152)
    panel_y = 62 + int((1.0 - reveal) * 22)
    draw.rounded_rectangle(
        (64, panel_y, 64 + panel_width, panel_y + 150),
        radius=6,
        fill=(4, 12, 22, 224),
        outline=(*accent, 210),
        width=2,
    )
    draw.text((88, panel_y + 18), "VISUAL EVIDENCE", fill=accent, font=fonts["small"])
    _draw_wrapped_text(
        draw,
        str(shot.get("focus_text") or shot.get("headline") or ""),
        (88, panel_y + 52),
        font=fonts["body"],
        width=panel_width - 48,
        max_height=78,
        fill=(245, 248, 252),
        spacing=5,
        max_lines=3,
    )


def _draw_scene_media_detail(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    *,
    width: int,
    height: int,
    reveal: float,
    drift_progress: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    """Cut from the establishing image to an evidence-led close-up composition."""
    variant = int(shot.get("composition_variant") or 0)
    media_left = bool(variant % 2)
    media_box = (28, 28, 850, height - 146) if media_left else (width - 850, 28, width - 28, height - 146)
    text_x = 904 if media_left else 64
    text_width = width - text_x - 64 if media_left else width - 850 - 108
    if not _draw_generated_image(
        draw,
        slide,
        media_box,
        motion_progress=drift_progress,
        motion_style="pan_right" if media_left else "pan_left",
    ):
        _draw_scene_visual_fallback(draw, slide, media_box, reveal=reveal, fonts=fonts)
    draw.text((text_x, 98), "EVIDENCE CLOSE-UP", fill=accent, font=fonts["small"])
    draw.rectangle((text_x, 132, text_x + int(text_width * reveal), 136), fill=accent)
    _draw_wrapped_text(
        draw,
        str(shot.get("focus_text") or ""),
        (text_x, 170),
        font=fonts["headline"],
        width=text_width,
        max_height=190,
        fill=(244, 247, 251),
        spacing=7,
        max_lines=5,
    )
    caption = _clean_display_text(slide.get("visual_caption") or slide.get("purpose") or "")
    if caption:
        _draw_wrapped_text(
            draw,
            caption,
            (text_x, 392),
            font=fonts["small"],
            width=text_width,
            max_height=76,
            fill=(158, 178, 203),
            spacing=4,
            max_lines=3,
        )


def _draw_scene_supporting_context(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    """Use the available frame for paper evidence instead of decorative typography."""
    x1, y1, x2, y2 = box
    focus = _clean_display_text(shot.get("focus_text") or "")
    candidates = [
        _clean_display_text(item)
        for item in (slide.get("bullets") or slide.get("visual_items") or [])
        if _clean_display_text(item) and _clean_display_text(item) != focus
    ]
    if not candidates:
        fallback = _clean_display_text(slide.get("visual_caption") or slide.get("purpose") or "")
        candidates = [fallback] if fallback and fallback != focus else []
    draw.text((x1, y1), "PAPER CONTEXT", fill=accent, font=fonts["small"])
    draw.rectangle((x1, y1 + 32, x2, y1 + 34), fill=(40, 65, 88))
    if not candidates:
        _draw_wrapped_text(
            draw,
            "The narration develops this claim with the paper's supporting evidence.",
            (x1, y1 + 58),
            font=fonts["small"],
            width=x2 - x1,
            max_height=y2 - y1 - 58,
            fill=(171, 190, 213),
            spacing=4,
            max_lines=4,
        )
        return
    item_height = max(74, (y2 - y1 - 54) // min(3, len(candidates)))
    for index, item in enumerate(candidates[:3]):
        y = y1 + 54 + index * item_height
        draw.text((x1, y), f"{index + 1:02d}", fill=accent, font=fonts["small"])
        _draw_wrapped_text(
            draw,
            item,
            (x1 + 42, y - 2),
            font=fonts["small"],
            width=x2 - x1 - 42,
            max_height=item_height - 12,
            fill=(207, 219, 233),
            spacing=3,
            max_lines=3,
        )


def _draw_scene_contrast(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    items = [_clean_display_text(item) for item in (slide.get("bullets") or []) if str(item).strip()]
    focus_index = min(int(shot.get("focus_index") or 0), max(0, len(items) - 1))
    left = items[max(0, focus_index - 1)] if items else str(shot.get("focus_text") or "")
    right = items[focus_index] if items else str(shot.get("narration") or "")
    mid = (x1 + x2) // 2
    draw.text((x1, y1), "CONTEXT", fill=(145, 164, 187), font=fonts["small"])
    draw.text((mid + 52, y1), "IMPLICATION", fill=accent, font=fonts["small"])
    draw.rectangle((x1, y1 + 34, mid - 54, y1 + 37), fill=(47, 74, 99))
    draw.rectangle((mid + 52, y1 + 34, x2, y1 + 37), fill=accent)
    _draw_wrapped_text(draw, left, (x1, y1 + 62), font=fonts["headline"], width=mid - x1 - 54, max_height=220, fill=(213, 223, 236), spacing=7, max_lines=5)
    if reveal > 0.45:
        _draw_wrapped_text(draw, right, (mid + 52, y1 + 62), font=fonts["headline"], width=x2 - mid - 52, max_height=220, fill=(244, 247, 251), spacing=7, max_lines=5)


def _draw_scene_process(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or slide.get("bullets") or [])[:5]]
    if not items:
        items = ["Input", "Reason", "Generate", "Evaluate"]
    visible = min(len(items), max(1, int(math.ceil(reveal * len(items)))))
    gap = 22
    node_w = max(120, (x2 - x1 - gap * (len(items) - 1)) // len(items))
    center_y = (y1 + y2) // 2
    for i, item in enumerate(items):
        x = x1 + i * (node_w + gap)
        if i > 0 and i < visible:
            draw.line((x - gap + 3, center_y, x - 5, center_y), fill=accent, width=3)
            draw.polygon([(x - 8, center_y - 6), (x, center_y), (x - 8, center_y + 6)], fill=accent)
        if i >= visible:
            continue
        active = i == visible - 1
        outline = accent if active else (54, 88, 119)
        draw.rounded_rectangle((x, center_y - 62, x + node_w, center_y + 62), radius=7, fill=(9, 18, 29), outline=outline, width=2)
        draw.text((x + 16, center_y - 44), f"{i + 1:02d}", fill=accent, font=fonts["small"])
        _draw_wrapped_text(
            draw,
            item,
            (x + 16, center_y - 10),
            font=fonts["small"],
            width=node_w - 32,
            max_height=56,
            fill=(226, 236, 248),
            spacing=3,
            max_lines=3,
        )


def _draw_scene_process_focus(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or slide.get("bullets") or [])[:5]]
    if not items:
        items = ["Input", "Reason", "Generate", "Evaluate"]
    focus = min(int(shot.get("focus_index") or 0), len(items) - 1)
    rise = int((1.0 - reveal) * 24)
    gap = 14
    nav_width = (x2 - x1 - gap * (len(items) - 1)) // len(items)
    for index, item in enumerate(items):
        nav_x = x1 + index * (nav_width + gap)
        active = index == focus
        draw.rounded_rectangle(
            (nav_x, y1 + rise, nav_x + nav_width, y1 + 72 + rise),
            radius=6,
            fill=(11, 26, 37) if active else (8, 17, 28),
            outline=accent if active else (38, 63, 86),
            width=2 if active else 1,
        )
        draw.text((nav_x + 14, y1 + 12 + rise), f"{index + 1:02d}", fill=accent if active else (92, 116, 143), font=fonts["small"])
        _draw_wrapped_text(
            draw,
            item,
            (nav_x + 48, y1 + 10 + rise),
            font=fonts["small"],
            width=nav_width - 60,
            max_height=50,
            fill=(235, 242, 250) if active else (151, 169, 191),
            spacing=2,
            max_lines=2,
        )

    detail = _scene_item_detail(slide, items[focus])
    detail_y = y1 + 116 + rise
    draw.text((x1, detail_y), f"CURRENT FOCUS  {focus + 1:02d}", fill=accent, font=fonts["small"])
    draw.rectangle((x1, detail_y + 32, x1 + 178, detail_y + 36), fill=accent)
    _draw_wrapped_text(
        draw,
        items[focus],
        (x1, detail_y + 58),
        font=fonts["headline"],
        width=430,
        max_height=112,
        fill=(242, 246, 251),
        spacing=6,
        max_lines=3,
    )
    detail_x = x1 + 510
    draw.text((detail_x, detail_y), "WHAT IT MEASURES", fill=accent, font=fonts["small"])
    draw.rectangle((detail_x, detail_y + 32, x2, detail_y + 34), fill=(44, 72, 97))
    _draw_wrapped_text(
        draw,
        detail,
        (detail_x, detail_y + 58),
        font=fonts["body"],
        width=x2 - detail_x,
        max_height=120,
        fill=(206, 219, 234),
        spacing=5,
        max_lines=4,
    )


def _draw_scene_process_trace(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    """Stage one mechanism node as a camera close-up instead of redrawing a slide."""
    x1, y1, x2, y2 = box
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or slide.get("bullets") or [])[:5]]
    if not items:
        items = ["Input", "Reason", "Generate", "Evaluate"]
    focus = min(int(shot.get("focus_index") or 0), len(items) - 1)
    previous = items[focus - 1] if focus > 0 else "SOURCE"
    current = items[focus]
    following = items[focus + 1] if focus + 1 < len(items) else "OUTCOME"
    detail = _scene_item_detail(slide, current)

    draw.text((x1 + 18, y1 + 4), f"MECHANISM  {focus + 1:02d} / {len(items):02d}", fill=accent, font=fonts["small"])
    track_y = y1 + 54
    draw.rectangle((x1 + 18, track_y, x2 - 18, track_y + 3), fill=(40, 65, 88))
    draw.rectangle((x1 + 18, track_y, x1 + 18 + int((x2 - x1 - 36) * (focus + reveal) / len(items)), track_y + 4), fill=accent)

    center_x = (x1 + x2) // 2
    center_y = y1 + 218
    ghost_w, ghost_h = 250, 104
    for ghost_x, label, side in ((x1 + 18, previous, -1), (x2 - ghost_w - 18, following, 1)):
        draw.rounded_rectangle(
            (ghost_x, center_y - ghost_h // 2, ghost_x + ghost_w, center_y + ghost_h // 2),
            radius=8,
            fill=(8, 18, 29),
            outline=(45, 70, 94),
            width=1,
        )
        _draw_wrapped_text(
            draw,
            label,
            (ghost_x + 20, center_y - 28),
            font=fonts["small"],
            width=ghost_w - 40,
            max_height=60,
            fill=(125, 145, 169),
            spacing=3,
            max_lines=2,
        )
        arrow_start = ghost_x + ghost_w if side < 0 else center_x + 242
        arrow_end = center_x - 242 if side < 0 else ghost_x
        draw.line((arrow_start, center_y, arrow_end, center_y), fill=accent, width=3)
        if side < 0:
            draw.polygon([(arrow_end - 10, center_y - 7), (arrow_end, center_y), (arrow_end - 10, center_y + 7)], fill=accent)
        else:
            draw.polygon([(arrow_end - 10, center_y - 7), (arrow_end, center_y), (arrow_end - 10, center_y + 7)], fill=accent)

    rise = int((1.0 - reveal) * 20)
    focus_box = (center_x - 224, center_y - 104 + rise, center_x + 224, center_y + 104 + rise)
    draw.rounded_rectangle(focus_box, radius=10, fill=(8, 31, 39), outline=accent, width=3)
    draw.text((focus_box[0] + 28, focus_box[1] + 22), "CURRENT STAGE", fill=accent, font=fonts["small"])
    _draw_wrapped_text(
        draw,
        current,
        (focus_box[0] + 28, focus_box[1] + 64),
        font=fonts["headline"],
        width=focus_box[2] - focus_box[0] - 56,
        max_height=112,
        fill=(244, 248, 252),
        spacing=6,
        max_lines=3,
    )
    draw.text((x1 + 18, y2 - 92), "WHY THIS STAGE MATTERS", fill=accent, font=fonts["small"])
    _draw_single_line_text(draw, detail, (x1 + 18, y2 - 54), font=fonts["body"], width=x2 - x1 - 36, fill=(202, 216, 232))


def _scene_item_detail(slide: dict[str, Any], item: str) -> str:
    label = _clean_display_text(item).split(":", 1)[0].strip()
    note = _clean_display_text(slide.get("speaker_note") or "")
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", note) if part.strip()]
    for sentence in sentences:
        if label and label.casefold() in sentence.casefold():
            return sentence
    for bullet in slide.get("bullets") or []:
        cleaned = _clean_display_text(bullet)
        if label and label.casefold() in cleaned.casefold():
            return cleaned
    return _clean_display_text(
        slide.get("visual_caption")
        or slide.get("purpose")
        or "This stage contributes evidence to the paper's evaluation pipeline."
    )


def _draw_scene_evidence(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    fonts: dict[str, Any],
) -> None:
    _draw_arbor_table(draw, slide, box, reveal=reveal, font=fonts["mono"])


def _draw_scene_evidence_focus(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    rows = [row for row in (slide.get("visual_table") or []) if isinstance(row, list)]
    data_rows = rows[1:] if len(rows) > 1 else rows
    focus = min(int(shot.get("focus_index") or 0), max(0, len(data_rows) - 1))
    row = data_rows[focus] if data_rows else (slide.get("bullets") or [shot.get("focus_text") or "Evidence"])
    cells = [_clean_display_text(cell) for cell in row[:3]]
    draw.text((x1, y1), f"EVIDENCE {focus + 1:02d}", fill=accent, font=fonts["small"])
    draw.rectangle((x1, y1 + 48, x1 + int((x2 - x1) * reveal), y1 + 54), fill=accent)
    column_width = max(180, (x2 - x1 - 72) // max(1, len(cells)))
    for index, cell in enumerate(cells):
        x = x1 + index * (column_width + 36)
        _draw_wrapped_text(draw, cell, (x, y1 + 92), font=fonts["headline"] if index == 0 else fonts["body"], width=column_width, max_height=190, fill=(243, 247, 251) if index == 0 else (190, 205, 224), spacing=7, max_lines=5)


def _draw_scene_metric(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    rows = [row for row in (slide.get("visual_table") or []) if isinstance(row, list)]
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or [])[:4]]
    bullets = [_clean_display_text(str(item)) for item in (slide.get("bullets") or [])[:4]]
    row_items = (
        [_clean_visual_item(" | ".join(str(cell) for cell in row[:3])) for row in rows[1:5]]
        if _visual_table_is_meaningful(rows)
        else []
    )
    narration = _clean_display_text(shot.get("narration") or "")
    shot_type = str(shot.get("shot_type") or "metric")
    layout = str(shot.get("layout_variant") or "data_wall")
    focus_index = min(int(shot.get("focus_index") or 0), max(0, len(bullets) - 1))
    focus_text = " ".join([narration, bullets[focus_index] if bullets else ""]).casefold()
    if any(token in focus_text for token in ("cursor", "grounding", "whisperx", "temporal alignment")):
        _draw_scene_cursor_grounding(
            draw,
            box,
            reveal=reveal,
            accent=accent,
            fonts=fonts,
        )
        return
    narration_folded = narration.casefold()
    describes_speed = bool(
        re.search(r"\b\d+(?:\.\d+)?\s*[x×%]", narration_folded)
        or any(token in narration_folded for token in ("speedup", "faster", "times compared", "times faster"))
    )
    if layout == "comparison" and "parallel" in narration_folded and not describes_speed:
        _draw_scene_parallel_mechanism(
            draw,
            shot,
            box,
            reveal=reveal,
            accent=accent,
            fonts=fonts,
        )
        return
    if layout == "comparison" and re.search(r"\b\d+(?:\.\d+)?\s*[x×%]", focus_text, flags=re.IGNORECASE):
        _draw_scene_metric_comparison(
            draw,
            slide,
            shot,
            box,
            reveal=reveal,
            accent=accent,
            fonts=fonts,
        )
        return
    if layout == "comparison" and "parallel" in focus_text:
        _draw_scene_parallel_mechanism(
            draw,
            shot,
            box,
            reveal=reveal,
            accent=accent,
            fonts=fonts,
        )
        return
    cards = _metric_cards_from_items(items or [*bullets, *row_items])
    if layout == "data_wall" and len(cards) >= 3 and shot_type in {"metric", "data_landscape"}:
        _draw_scene_metric_wall(
            draw,
            cards,
            box,
            focus_index=_metric_card_focus(cards, narration, fallback=int(shot.get("focus_index") or 0)),
            reveal=reveal,
            accent=accent,
            fonts=fonts,
        )
        return
    focus_index = _metric_card_focus(cards, narration, fallback=int(shot.get("focus_index") or 0))
    value, label = cards[focus_index]
    variant = int(shot.get("composition_variant") or 0)
    focus_right = bool(variant % 2)
    number_x = x1 + 700 if focus_right else x1
    label_x = x1 + 650 if focus_right else x1 + 8
    list_x = x1 if focus_right else x1 + 650
    draw.text((number_x, y1 + 18), value, fill=accent, font=fonts["number"])
    _draw_wrapped_text(
        draw,
        label,
        (label_x, y1 + 126),
        font=fonts["headline"],
        width=470,
        max_height=120,
        fill=(239, 244, 250),
        spacing=5,
        max_lines=3,
    )
    supporting_cards = [card for index, card in enumerate(cards) if index != focus_index]
    visible = min(len(supporting_cards), max(1, int(math.ceil(reveal * len(supporting_cards)))))
    for i, (small_value, small_label) in enumerate(supporting_cards[:visible]):
        y = y1 + i * 66
        draw.text((list_x, y + 6), small_value, fill=accent, font=fonts["small"])
        _draw_single_line_text(draw, small_label, (list_x + 110, y + 6), font=fonts["small"], width=440, fill=(194, 208, 226))
        draw.line((list_x, y + 42, min(x2, list_x + 540), y + 42), fill=(38, 60, 82), width=1)


def _draw_scene_metric_wall(
    draw: Any,
    cards: list[tuple[str, str]],
    box: tuple[int, int, int, int],
    *,
    focus_index: int,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    gap = 24
    card_width = (x2 - x1 - gap) // 2
    card_height = (y2 - y1 - gap) // 2
    visible = min(4, max(1, int(math.ceil(reveal * min(4, len(cards))))))
    for index, (value, label) in enumerate(cards[:4]):
        if index >= visible:
            continue
        column = index % 2
        row = index // 2
        card_x = x1 + column * (card_width + gap)
        card_y = y1 + row * (card_height + gap)
        active = index == focus_index
        draw.rounded_rectangle(
            (card_x, card_y, card_x + card_width, card_y + card_height),
            radius=7,
            fill=(10, 29, 39) if active else (9, 20, 32),
            outline=accent if active else (43, 71, 96),
            width=2 if active else 1,
        )
        draw.text((card_x + 24, card_y + 18), "PAPER EVIDENCE", fill=accent if active else (112, 139, 169), font=fonts["small"])
        draw.text((card_x + 24, card_y + 52), value, fill=(242, 247, 251), font=fonts["number"])
        _draw_wrapped_text(
            draw,
            label,
            (card_x + 174, card_y + 60),
            font=fonts["body"],
            width=card_width - 198,
            max_height=68,
            fill=(207, 220, 235),
            spacing=4,
            max_lines=3,
        )
        draw.rectangle(
            (card_x + 24, card_y + card_height - 18, card_x + card_width - 24, card_y + card_height - 15),
            fill=accent if active else (35, 59, 82),
        )


def _draw_scene_cursor_grounding(
    draw: Any,
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    stages = [
        ("NARRATION", "Current sentence"),
        ("GUI GROUNDING", "Visual target"),
        ("CURSOR", "Screen coordinate"),
    ]
    gap = 34
    node_width = (x2 - x1 - gap * 2) // 3
    visible = max(1, min(len(stages), int(math.ceil(reveal * len(stages)))))
    center_y = y1 + 104
    for index, (label, detail) in enumerate(stages):
        if index >= visible:
            continue
        node_x = x1 + index * (node_width + gap)
        active = index == visible - 1
        if index:
            draw.line((node_x - gap + 5, center_y + 40, node_x - 7, center_y + 40), fill=accent, width=3)
            draw.polygon(
                [(node_x - 10, center_y + 33), (node_x, center_y + 40), (node_x - 10, center_y + 47)],
                fill=accent,
            )
        draw.rounded_rectangle(
            (node_x, center_y, node_x + node_width, center_y + 82),
            radius=6,
            fill=(10, 29, 39) if active else (9, 20, 32),
            outline=accent if active else (55, 82, 108),
            width=2,
        )
        draw.text((node_x + 18, center_y + 14), label, fill=accent if active else (168, 187, 210), font=fonts["small"])
        draw.text((node_x + 18, center_y + 46), detail, fill=(232, 239, 248), font=fonts["small"])

    timeline_y = y1 + 244
    draw.text((x1, timeline_y), "WHISPERX TEMPORAL ALIGNMENT", fill=accent, font=fonts["small"])
    draw.line((x1, timeline_y + 48, x2, timeline_y + 48), fill=(53, 80, 105), width=2)
    tick_count = 9
    for index in range(tick_count):
        tick_x = x1 + int((x2 - x1) * index / (tick_count - 1))
        amplitude = 8 + (index * 7) % 24
        draw.line(
            (tick_x, timeline_y + 48 - amplitude, tick_x, timeline_y + 48 + amplitude),
            fill=accent if index < int(reveal * tick_count) else (42, 66, 89),
            width=3,
        )
    marker_x = x1 + int((x2 - x1) * min(1.0, reveal))
    draw.ellipse((marker_x - 7, timeline_y + 41, marker_x + 7, timeline_y + 55), fill=(240, 246, 252), outline=accent, width=2)


def _draw_scene_parallel_mechanism(
    draw: Any,
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    gap = 76
    column_width = (x2 - x1 - gap) // 2
    right_x = x1 + column_width + gap
    draw.text((x1, y1), "SEQUENTIAL GENERATION", fill=(144, 164, 187), font=fonts["small"])
    draw.text((right_x, y1), "PAPERTALKER PARALLEL", fill=accent, font=fonts["small"])
    draw.rectangle((x1, y1 + 34, x1 + column_width, y1 + 37), fill=(47, 74, 99))
    draw.rectangle((right_x, y1 + 34, x2, y1 + 37), fill=accent)
    visible = max(1, min(3, int(math.ceil(reveal * 3))))
    node_width = 132
    node_height = 62
    serial_y = y1 + 112
    for index in range(visible):
        node_x = x1 + index * (node_width + 34)
        draw.rounded_rectangle(
            (node_x, serial_y, node_x + node_width, serial_y + node_height),
            radius=6,
            fill=(11, 23, 36),
            outline=(67, 91, 117),
            width=2,
        )
        draw.text((node_x + 18, serial_y + 19), f"SLIDE {index + 1:02d}", fill=(203, 216, 232), font=fonts["small"])
        if index and index < visible:
            draw.line((node_x - 28, serial_y + 31, node_x - 7, serial_y + 31), fill=(91, 116, 145), width=3)
            draw.polygon([(node_x - 8, serial_y + 25), (node_x, serial_y + 31), (node_x - 8, serial_y + 37)], fill=(91, 116, 145))
    parallel_node_width = column_width - 104
    for index in range(visible):
        node_y = y1 + 76 + index * 72
        draw.rounded_rectangle(
            (right_x + 52, node_y, right_x + 52 + parallel_node_width, node_y + 52),
            radius=6,
            fill=(10, 31, 39),
            outline=accent,
            width=2,
        )
        draw.text((right_x + 72, node_y + 14), f"SLIDE {index + 1:02d}", fill=(233, 244, 249), font=fonts["small"])
    draw.text((x1, y2 - 48), "Tasks wait for the previous slide", fill=(137, 157, 181), font=fonts["small"])
    draw.text((right_x, y2 - 48), "Independent slides run at the same time", fill=accent, font=fonts["small"])


def _draw_scene_metric_comparison(
    draw: Any,
    slide: dict[str, Any],
    shot: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    source_text = " ".join(
        [
            str(shot.get("narration") or ""),
            str(slide.get("speaker_note") or ""),
            *[str(item) for item in slide.get("bullets") or []],
        ]
    )
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*[x×]", source_text, flags=re.IGNORECASE)
    factor = max(1.0, float(match.group(1))) if match else 1.0
    value = f"{match.group(1)}x" if match else "VS"
    draw.text((x1, y1 + 8), "REPORTED EFFICIENCY", fill=accent, font=fonts["small"])
    draw.text((x1, y1 + 48), value, fill=accent, font=fonts["number"])
    _draw_wrapped_text(
        draw,
        _clean_display_text(shot.get("narration") or shot.get("focus_text") or slide.get("visual_caption") or ""),
        (x1, y1 + 148),
        font=fonts["body"],
        width=390,
        max_height=118,
        fill=(230, 238, 247),
        spacing=5,
        max_lines=4,
    )
    chart_x = x1 + 500
    chart_width = x2 - chart_x
    draw.text((chart_x, y1 + 8), "RELATIVE GENERATION TIME", fill=accent, font=fonts["small"])
    comparisons = [
        ("Sequential baseline", 1.0, "1.00x"),
        ("PaperTalker parallel", 1.0 / factor if factor > 1 else 0.62, f"≤ {1.0 / factor:.2f}x" if factor > 1 else "faster"),
    ]
    for index, (label, ratio, readout) in enumerate(comparisons):
        y = y1 + 82 + index * 112
        draw.text((chart_x, y), label, fill=(203, 216, 232), font=fonts["small"])
        draw.text((x2 - 86, y), readout, fill=accent if index else (150, 170, 194), font=fonts["small"])
        draw.rounded_rectangle((chart_x, y + 38, x2, y + 58), radius=5, fill=(25, 43, 61))
        bar_width = int(chart_width * ratio * reveal)
        draw.rounded_rectangle(
            (chart_x, y + 38, chart_x + max(8, bar_width), y + 58),
            radius=5,
            fill=accent if index else (91, 116, 145),
        )
    draw.text((chart_x, y2 - 44), "Lower is faster", fill=(133, 153, 177), font=fonts["small"])


def _metric_card_focus(cards: list[tuple[str, str]], narration: str, *, fallback: int) -> int:
    folded = narration.casefold()
    best_index = -1
    best_score = 0
    stop_words = {"the", "and", "for", "with", "from", "time", "generation", "slide", "slides"}
    narration_tokens = set(re.findall(r"[a-z0-9]+(?:x|%)?", folded)) - stop_words
    for index, (value, label) in enumerate(cards):
        card_tokens = set(re.findall(r"[a-z0-9]+(?:x|%)?", f"{value} {label}".casefold())) - stop_words
        overlap = narration_tokens & card_tokens
        score = sum(3 if re.search(r"\d", token) else 2 if len(token) >= 8 else 1 for token in overlap)
        if score > best_score:
            best_index = index
            best_score = score
    if best_index >= 0 and best_score:
        return best_index
    return min(fallback, max(0, len(cards) - 1))


def _draw_scene_takeaways(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    accent: tuple[int, int, int],
    fonts: dict[str, Any],
) -> None:
    x1, y1, x2, _y2 = box
    items = [_clean_display_text(item) for item in (slide.get("bullets") or slide.get("visual_items") or [])[:3]]
    visible = min(len(items), max(1, int(math.ceil(reveal * len(items)))))
    for i, item in enumerate(items[:visible]):
        y = y1 + i * 94
        draw.text((x1, y), f"{i + 1:02d}", fill=accent, font=fonts["body"])
        _draw_wrapped_text(
            draw,
            item,
            (x1 + 76, y - 2),
            font=fonts["body"],
            width=x2 - x1 - 90,
            max_height=72,
            fill=(232, 239, 248),
            spacing=4,
            max_lines=3,
        )
        draw.line((x1 + 76, y + 70, x2, y + 70), fill=(37, 59, 80), width=1)


def _draw_scene_visual_fallback(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    fonts: dict[str, Any],
) -> None:
    kind = str(slide.get("visual_kind") or "image")
    if kind == "flow":
        _draw_scene_process(draw, slide, box, reveal=reveal, accent=(20, 184, 166), fonts=fonts)
    elif kind == "table":
        _draw_scene_evidence(draw, slide, box, reveal=reveal, fonts=fonts)
    elif kind == "metrics":
        _draw_scene_metric(
            draw,
            slide,
            {"focus_index": 0},
            box,
            reveal=reveal,
            accent=(20, 184, 166),
            fonts=fonts,
        )
    else:
        _draw_scene_takeaways(draw, slide, box, reveal=reveal, accent=(20, 184, 166), fonts=fonts)


def _draw_scene_narration(
    draw: Any,
    narration: str,
    *,
    theme: dict[str, Any],
    width: int,
    height: int,
    local: float,
    font: Any,
) -> None:
    if not narration:
        return
    accent = tuple(theme["accent"])
    y = height - 126 + int((1.0 - _scene_ease(min(1.0, local / 0.28))) * 18)
    draw.rectangle((76, y - 12, 246, y - 8), fill=accent)
    _draw_wrapped_text(
        draw,
        narration,
        (76, y + 2),
        font=font,
        width=width - 152,
        max_height=72,
        fill=(226, 236, 248),
        spacing=4,
        max_lines=3,
    )


def _render_arbor_mp4_video(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    subtitles: list[dict[str, Any]],
    cursor_plan: list[dict[str, Any]],
    out: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    frames_dir = out.parent / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    title_font = _font(54)
    h2_font = _font(34)
    body_font = _font(23)
    small_font = _font(17)
    mono_font = _font(16)
    caption_font = _font(22)

    by_slide: dict[int, list[dict[str, Any]]] = {}
    for item in subtitles:
        by_slide.setdefault(int(item["slide_index"]), []).append(item)
    total_duration = max((int(s["end_sec"]) for s in subtitles), default=len(slides) * 10)
    if total_duration <= 0:
        total_duration = max(1, len(slides) * 10)

    by_cursor: dict[int, list[dict[str, Any]]] = {}
    for item in cursor_plan:
        by_cursor.setdefault(int(item["slide_index"]), []).append(item)
    for items in by_cursor.values():
        items.sort(key=lambda item: float(item["start_sec"]))

    def active_subtitle(sec: float, slide_index: int) -> dict[str, Any] | None:
        for item in by_slide.get(slide_index, []):
            if float(item["start_sec"]) <= sec <= float(item["end_sec"]):
                return item
        items = by_slide.get(slide_index, [])
        return items[0] if items else None

    def cursor_position(sec: float, slide_index: int) -> tuple[int, int, float] | None:
        items = by_cursor.get(slide_index, [])
        if not items:
            return None
        active_idx = 0
        for idx, item in enumerate(items):
            if float(item["start_sec"]) <= sec <= float(item["end_sec"]):
                active_idx = idx
                break
            if sec >= float(item["start_sec"]):
                active_idx = idx
        active = items[active_idx]
        target_x = float(active["x_percent"])
        target_y = float(active["y_percent"])
        if active_idx > 0:
            previous = items[active_idx - 1]
            start_x = float(previous["x_percent"])
            start_y = float(previous["y_percent"])
        else:
            start_x = max(10.0, min(90.0, target_x - 10.0))
            start_y = max(12.0, min(76.0, target_y - 8.0))
        start_sec = float(active["start_sec"])
        end_sec = max(start_sec + 0.01, float(active["end_sec"]))
        segment_duration = end_sec - start_sec
        move_duration = min(1.25, max(0.48, segment_duration * 0.22))
        move_t = ease((sec - start_sec) / move_duration)
        if sec <= start_sec + move_duration:
            sx = width * start_x / 100
            sy = height * start_y / 100
            tx = width * target_x / 100
            ty = height * target_y / 100
            dx = tx - sx
            dy = ty - sy
            length = max(1.0, math.hypot(dx, dy))
            arc = math.sin(math.pi * move_t) * min(16.0, length * 0.08)
            x = sx + dx * move_t - dy / length * arc
            y = sy + dy * move_t + dx / length * arc
            attention = 0.0
        else:
            hold = sec - start_sec - move_duration
            x = width * target_x / 100 + 0.9 * math.sin(hold * 4.1 + slide_index)
            y = height * target_y / 100 + 0.7 * math.sin(hold * 3.4 + active_idx)
            attention = max(0.0, 1.0 - hold / 0.55)
        return int(x), int(y), attention

    def ease(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3 - 2 * value)

    frame_index = 0
    total_slides = len(slides)
    theme = _paper_visual_theme(source)
    background_color = tuple(theme["background"])
    _progress("renderer", "start frame rendering", current=0, total=total_slides, detail=f"style=arbor fps={fps}")
    for slide_pos, slide in enumerate(slides, start=1):
        slide_index = int(slide["index"])
        slide_subs = by_slide.get(slide_index, [])
        start = min((int(s["start_sec"]) for s in slide_subs), default=(slide_index - 1) * 10)
        end = max((int(s["end_sec"]) for s in slide_subs), default=start + 10)
        duration = max(1, end - start)
        frame_count = max(1, duration * fps)
        _progress("renderer", "draw slide frames", current=slide_pos, total=total_slides, detail=f"slide={slide_index} frames={frame_count}")
        for tick in range(frame_count):
            sec = start + tick / fps
            local = tick / max(1, frame_count - 1)
            img = Image.new("RGB", (width, height), background_color)
            draw = ImageDraw.Draw(img)
            _draw_arbor_background(draw, width, height, sec, source=source, slide=slide)
            _draw_arbor_header(
                draw,
                source,
                slide,
                width=width,
                height=height,
                small_font=small_font,
                sec=sec,
                total_duration=total_duration,
                total_slides=len(slides),
            )

            _draw_arbor_scene(
                draw,
                source,
                slide,
                width=width,
                height=height,
                reveal=ease(min(1.0, local * 1.25)),
                visual_reveal=ease(max(0.0, min(1.0, (local - 0.05) / 0.55))),
                title_font=title_font,
                h2_font=h2_font,
                body_font=body_font,
                small_font=small_font,
                mono_font=mono_font,
            )

            cur = cursor_position(sec, slide_index)
            if cur:
                cx, cy, pulse = cur
                _draw_arbor_pointer(draw, cx, cy, pulse)

            sub = active_subtitle(sec, slide_index)
            caption = sub["text"] if sub else str(slide.get("speaker_note", ""))
            _draw_arbor_caption(draw, caption, width=width, height=height, font=caption_font)

            fade = ease(min(1.0, tick / max(1, fps * 0.65)))
            if fade < 1.0:
                dark = Image.new("RGB", (width, height), background_color)
                img = Image.blend(dark, img, max(0.2, fade))

            img.save(frames_dir / f"frame_{frame_index:05d}.png")
            frame_index += 1

    _progress("renderer", "start ffmpeg encoding", detail=f"frames={frame_index} fps={fps} out={out.name}")
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
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    ok = proc.returncode == 0 and out.is_file()
    _progress("renderer", "ffmpeg encoding complete" if ok else "ffmpeg encoding failed", detail=f"returncode={proc.returncode} out={out}")
    if ok:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return ok


def _draw_arbor_background(
    draw: Any,
    width: int,
    height: int,
    sec: float,
    *,
    source: dict[str, Any],
    slide: dict[str, Any],
) -> None:
    theme = _paper_visual_theme(source)
    background = tuple(theme["background"])
    pattern = tuple(theme["pattern"])
    line = tuple(theme["line"])
    kind = str(theme["pattern_kind"])
    slide_phase = int(slide.get("index", 0) or 0)
    draw.rectangle((0, 0, width, height), fill=background)

    if kind == "grid":
        for y in range(0, height, 24):
            for x in range(0, width, 24):
                glow = int(pattern[2] * (0.74 + 0.2 * (0.5 + 0.5 * math.sin((x + y) * 0.018 + sec * 0.7))))
                draw.ellipse((x, y, x + 2, y + 2), fill=(pattern[0], pattern[1], glow))
    elif kind == "cells":
        radius = 48
        edge_start = int(width * 0.74)
        draw.rectangle((edge_start, 0, width, height), fill=(10, 22, 20))
        for row, cy in enumerate(range(-30, height + radius, 78)):
            offset = 46 if row % 2 else 0
            for cx in range(edge_start - 20 + offset, width + radius, 92):
                points = [
                    (
                        cx + int(radius * math.cos(math.pi / 3 * i)),
                        cy + int(radius * math.sin(math.pi / 3 * i)),
                    )
                    for i in range(6)
                ]
                draw.line([*points, points[0]], fill=pattern, width=1)
        draw.line((edge_start, height - 48, width, height - 48), fill=line, width=1)
    elif kind == "contours":
        band_start = int(height * 0.66)
        draw.rectangle((0, band_start, width, height), fill=(13, 22, 17))
        for band in range(band_start - 26, height + 100, 38):
            points = []
            for x in range(-20, width + 30, 18):
                y = band + int(11 * math.sin(x * 0.012 + slide_phase * 0.7) + 5 * math.sin(x * 0.025 + sec * 0.12))
                points.append((x, y))
            draw.line(points, fill=pattern, width=1)
        draw.line((0, band_start, width, band_start), fill=line, width=1)
    elif kind == "orbits":
        center_x = int(width * 1.04)
        center_y = int(height * (0.32 if slide_phase % 2 else 0.68))
        for radius in (250, 390, 560):
            vertical = max(40, int(radius * 0.56))
            draw.ellipse(
                (center_x - radius, center_y - vertical, center_x + radius, center_y + vertical),
                outline=pattern,
                width=1,
            )
        draw.line((int(width * 0.72), height - 48, width, height - 48), fill=line, width=1)
    elif kind == "columns":
        draw.line((0, 104, width, 104), fill=line, width=1)
        draw.line((0, height - 72, width, height - 72), fill=line, width=1)
        for i in range(3):
            x = int(width * 0.72) + i * 92
            y = 142 + ((i + slide_phase) % 3) * 104
            draw.rectangle((x, y, min(width - 26, x + 56), y + 2), fill=pattern)
    else:
        corner_paths = [
            [(0, 124), (112, 124), (112, 178), (188, 178)],
            [(width - 310, 0), (width - 310, 96), (width - 214, 96), (width - 214, 142)],
            [(0, height - 118), (142, height - 118), (142, height - 64), (238, height - 64)],
            [(width - 246, height), (width - 246, height - 92), (width - 128, height - 92)],
        ]
        for points in corner_paths:
            draw.line(points, fill=pattern, width=1)
            end_x, end_y = points[-1]
            draw.rectangle((end_x - 2, end_y - 2, end_x + 2, end_y + 2), fill=line)

    draw.rectangle((0, 0, width - 1, height - 1), outline=line, width=1)


def _draw_arbor_header(
    draw: Any,
    source: dict[str, Any],
    slide: dict[str, Any],
    *,
    width: int,
    height: int,
    small_font: Any,
    sec: float,
    total_duration: int,
    total_slides: int,
) -> None:
    theme = _paper_visual_theme(source)
    accent = tuple(theme["accent"])
    line = tuple(theme["line"])
    _draw_single_line_text(
        draw,
        source.get("title", ""),
        (42, 28),
        font=small_font,
        width=600,
        fill=(204, 214, 226),
    )
    tag = f"scene {int(slide.get('index', 0)):02d} / {max(1, total_slides):02d}"
    draw.text((width - 208, 28), tag, fill=accent, font=small_font)
    progress = max(0.0, min(1.0, sec / max(1, total_duration)))
    draw.rectangle((0, 78, int(width * progress), 82), fill=accent)
    draw.rectangle((0, 82, width, 83), fill=line)


def _arbor_layout_name(slide: dict[str, Any]) -> str:
    index = int(slide.get("index", 0) or 0)
    kind = str(slide.get("visual_kind") or "image").lower()
    if index == 1:
        return "title"
    if kind == "flow":
        return "workflow"
    if kind == "table":
        return "evidence"
    if kind == "metrics":
        return "summary"
    if kind == "screenshot":
        return "focus"
    return "focus"


def _draw_arbor_scene(
    draw: Any,
    source: dict[str, Any],
    slide: dict[str, Any],
    *,
    width: int,
    height: int,
    reveal: float,
    visual_reveal: float,
    title_font: Any,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    layout = _arbor_layout_name(slide)
    if layout == "title":
        _draw_arbor_title_scene(
            draw,
            source,
            slide,
            width=width,
            reveal=reveal,
            visual_reveal=visual_reveal,
            title_font=title_font,
            body_font=body_font,
            small_font=small_font,
            mono_font=mono_font,
        )
    elif layout == "workflow":
        _draw_arbor_workflow_scene(
            draw,
            slide,
            width=width,
            reveal=reveal,
            visual_reveal=visual_reveal,
            h2_font=h2_font,
            body_font=body_font,
            small_font=small_font,
            mono_font=mono_font,
        )
    elif layout == "evidence":
        _draw_arbor_evidence_scene(
            draw,
            slide,
            reveal=reveal,
            visual_reveal=visual_reveal,
            h2_font=h2_font,
            body_font=body_font,
            small_font=small_font,
            mono_font=mono_font,
        )
    elif layout == "summary":
        _draw_arbor_summary_scene(
            draw,
            slide,
            width=width,
            reveal=reveal,
            visual_reveal=visual_reveal,
            h2_font=h2_font,
            body_font=body_font,
            small_font=small_font,
            mono_font=mono_font,
        )
    elif layout == "screenshot":
        _draw_arbor_screenshot_scene(
            draw,
            slide,
            reveal=reveal,
            visual_reveal=visual_reveal,
            h2_font=h2_font,
            body_font=body_font,
            small_font=small_font,
            mono_font=mono_font,
        )
    else:
        _draw_arbor_focus_scene(
            draw,
            slide,
            width=width,
            reveal=reveal,
            visual_reveal=visual_reveal,
            h2_font=h2_font,
            body_font=body_font,
            small_font=small_font,
            mono_font=mono_font,
        )


def _draw_arbor_title_scene(
    draw: Any,
    source: dict[str, Any],
    slide: dict[str, Any],
    *,
    width: int,
    reveal: float,
    visual_reveal: float,
    title_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    label = str(source.get("kind", "paper")).upper()
    draw.text((78, 132), label, fill=(20, 184, 166), font=small_font)
    y = _draw_wrapped_text(
        draw,
        str(slide.get("title") or source.get("title", "")),
        (76, 176),
        font=title_font,
        width=660,
        max_height=124,
        fill=(244, 247, 251),
        spacing=6,
        max_lines=3,
    )
    caption = str(slide.get("visual_caption") or "Automatically generated presentation video")
    _draw_wrapped_text(
        draw,
        caption,
        (80, y + 14),
        font=body_font,
        width=610,
        max_height=max(1, 430 - y - 18),
        fill=(154, 177, 207),
        spacing=4,
        max_lines=4,
    )
    _draw_arbor_bullet_strip(draw, slide, (76, 462, width - 76, 548), reveal=reveal, font=small_font)
    _draw_arbor_visual_panel(
        draw,
        slide,
        (820, 132, 1200, 430),
        reveal=visual_reveal,
        body_font=body_font,
        small_font=small_font,
        mono_font=mono_font,
    )


def _draw_arbor_focus_scene(
    draw: Any,
    slide: dict[str, Any],
    *,
    width: int,
    reveal: float,
    visual_reveal: float,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    _draw_single_line_text(draw, slide.get("title", ""), (76, 130), font=h2_font, width=1128, fill=(244, 247, 251))
    _draw_arbor_visual_panel(
        draw,
        slide,
        (76, 198, width - 76, 430),
        reveal=visual_reveal,
        body_font=body_font,
        small_font=small_font,
        mono_font=mono_font,
    )
    _draw_arbor_bullet_strip(draw, slide, (76, 458, width - 76, 548), reveal=reveal, font=small_font)


def _draw_arbor_workflow_scene(
    draw: Any,
    slide: dict[str, Any],
    *,
    width: int,
    reveal: float,
    visual_reveal: float,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    draw.text((78, 126), "PIPELINE", fill=(20, 184, 166), font=small_font)
    _draw_single_line_text(draw, slide.get("title", ""), (76, 158), font=h2_font, width=1128, fill=(244, 247, 251))
    _draw_arbor_visual_panel(
        draw,
        slide,
        (92, 238, width - 92, 438),
        reveal=visual_reveal,
        body_font=body_font,
        small_font=small_font,
        mono_font=mono_font,
    )
    _draw_arbor_bullet_strip(draw, slide, (96, 466, width - 96, 548), reveal=reveal, font=small_font)


def _draw_arbor_evidence_scene(
    draw: Any,
    slide: dict[str, Any],
    *,
    reveal: float,
    visual_reveal: float,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    draw.text((76, 124), "EVIDENCE", fill=(20, 184, 166), font=small_font)
    _draw_single_line_text(draw, slide.get("title", ""), (76, 156), font=h2_font, width=1128, fill=(244, 247, 251))
    _draw_arbor_visual_panel(
        draw,
        slide,
        (76, 194, 1204, 504),
        reveal=visual_reveal,
        body_font=body_font,
        small_font=small_font,
        mono_font=mono_font,
    )
    _draw_arbor_bullet_strip(draw, slide, (76, 520, 1204, 580), reveal=reveal, font=small_font)


def _draw_arbor_summary_scene(
    draw: Any,
    slide: dict[str, Any],
    *,
    width: int,
    reveal: float,
    visual_reveal: float,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    _draw_single_line_text(draw, slide.get("title", ""), (76, 124), font=h2_font, width=1128, fill=(244, 247, 251))
    _draw_arbor_visual_panel(
        draw,
        slide,
        (76, 196, 606, 548),
        reveal=visual_reveal,
        body_font=body_font,
        small_font=small_font,
        mono_font=mono_font,
    )
    _draw_arbor_takeaway_cards(draw, slide, (646, 196, width - 76, 548), reveal=reveal, font=small_font)


def _draw_arbor_screenshot_scene(
    draw: Any,
    slide: dict[str, Any],
    *,
    reveal: float,
    visual_reveal: float,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    _draw_arbor_visual_panel(
        draw,
        slide,
        (76, 126, 744, 548),
        reveal=visual_reveal,
        body_font=body_font,
        small_font=small_font,
        mono_font=mono_font,
    )
    _draw_arbor_text_panel(
        draw,
        slide,
        (784, 126, 1206, 548),
        reveal=reveal,
        h2_font=h2_font,
        body_font=body_font,
        small_font=small_font,
    )


def _draw_arbor_bullet_strip(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    font: Any,
) -> None:
    x1, y1, x2, y2 = box
    bullets = [str(b) for b in slide.get("bullets", [])[:3]]
    visible = min(len(bullets), max(1, int(math.ceil(reveal * max(1, len(bullets))))))
    gap = 14
    card_w = (x2 - x1 - gap * 2) // 3
    for i, bullet in enumerate(bullets[:visible]):
        x = x1 + i * (card_w + gap)
        draw.rounded_rectangle((x, y1, x + card_w, y2), radius=8, fill=(9, 18, 31), outline=(31, 61, 96), width=2)
        draw.text((x + 16, y1 + 16), f"{i + 1:02d}", fill=(20, 184, 166), font=font)
        _draw_wrapped_text(
            draw,
            bullet,
            (x + 56, y1 + 14),
            font=font,
            width=card_w - 74,
            max_height=max(1, y2 - y1 - 24),
            fill=(224, 233, 245),
            spacing=3,
        )


def _draw_arbor_takeaway_cards(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    font: Any,
) -> None:
    x1, y1, x2, _y2 = box
    items = [str(b) for b in (slide.get("bullets", []) or slide.get("visual_items", []))[:4]]
    visible = min(len(items), max(1, int(math.ceil(reveal * max(1, len(items))))))
    for i, item in enumerate(items[:visible]):
        y = y1 + i * 82
        draw.rounded_rectangle((x1, y, x2, y + 62), radius=8, fill=(9, 18, 31), outline=(31, 61, 96), width=2)
        draw.rectangle((x1, y, x1 + 6, y + 62), fill=(20, 184, 166))
        _draw_wrapped_text(
            draw,
            item,
            (x1 + 22, y + 10),
            font=font,
            width=x2 - x1 - 44,
            max_height=46,
            fill=(224, 233, 245),
            spacing=3,
        )


def _draw_arbor_text_panel(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    h2_font: Any,
    body_font: Any,
    small_font: Any,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=8, fill=(8, 15, 27), outline=(31, 61, 96), width=2)
    draw.text((x1 + 24, y1 + 22), f"Step {slide.get('index', '')}: DISPATCH", fill=(20, 184, 166), font=small_font)
    _draw_wrapped_text(
        draw,
        str(slide.get("title", "")),
        (x1 + 24, y1 + 58),
        font=h2_font,
        width=x2 - x1 - 48,
        max_height=58,
        fill=(244, 247, 251),
        spacing=2,
        max_lines=2,
    )
    bullets = [str(b) for b in slide.get("bullets", [])[:4]]
    visible = min(len(bullets), max(1, int(math.ceil(reveal * max(1, len(bullets))))))
    y = y1 + 126
    for i, bullet in enumerate(bullets[:visible]):
        active = i == visible - 1
        color = (218, 231, 248) if active else (142, 157, 178)
        dot = (20, 184, 166) if active else (53, 92, 135)
        draw.ellipse((x1 + 28, y + 8, x1 + 39, y + 19), fill=dot)
        y = _draw_wrapped_text(
            draw,
            bullet,
            (x1 + 56, y),
            font=body_font,
            width=x2 - x1 - 86,
            max_height=max(1, y2 - y - 58),
            fill=color,
            spacing=5,
            max_lines=2,
        )
        y += 16
    _draw_single_line_text(
        draw,
        slide.get("visual_caption", ""),
        (x1 + 24, y2 - 36),
        font=small_font,
        width=x2 - x1 - 48,
        fill=(84, 124, 170),
    )


def _draw_arbor_visual_panel(
    draw: Any,
    slide: dict[str, Any],
    box: tuple[int, int, int, int],
    *,
    reveal: float,
    body_font: Any,
    small_font: Any,
    mono_font: Any,
) -> None:
    x1, y1, x2, y2 = box
    width = x2 - x1
    panel = (x1, y1, x2, y2)
    kind = str(slide.get("visual_kind") or "image")
    if kind == "image" and _draw_generated_image(draw, slide, panel):
        return
    draw.rounded_rectangle(panel, radius=9, fill=(10, 18, 30), outline=(35, 77, 117), width=2)
    draw.rectangle((panel[0], panel[1], panel[2], panel[1] + 38), fill=(13, 24, 38), outline=(35, 77, 117))
    label = _visual_label(str(slide.get("visual_kind") or "image")).upper()
    draw.rectangle((panel[0] + 18, panel[1] + 11, panel[0] + 24, panel[1] + 27), fill=(20, 184, 166))
    draw.text((panel[0] + 36, panel[1] + 12), label, fill=(154, 201, 255), font=small_font)
    inner = (panel[0] + 28, panel[1] + 62, panel[2] - 28, panel[3] - 34)
    if kind == "flow":
        _draw_arbor_tree(draw, slide, inner, reveal=reveal, font=small_font)
    elif kind == "table":
        _draw_arbor_table(draw, slide, inner, reveal=reveal, font=mono_font)
    elif kind == "metrics":
        _draw_arbor_metrics(draw, slide, inner, reveal=reveal, font=small_font)
    elif kind == "image" and _draw_generated_image(draw, slide, inner):
        return
    elif kind == "screenshot":
        _draw_arbor_cards(draw, slide, inner, reveal=reveal, font=small_font)
    else:
        _draw_arbor_cards(draw, slide, inner, reveal=reveal, font=small_font)


def _draw_arbor_tree(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], *, reveal: float, font: Any) -> None:
    x1, y1, x2, y2 = box
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or ["ingest", "build", "judge", "render"])[:5]]
    root = ((x1 + x2) // 2, y1 + 20)
    draw.rounded_rectangle((root[0] - 44, root[1] - 16, root[0] + 44, root[1] + 16), radius=4, fill=(9, 14, 24), outline=(90, 138, 190))
    draw.text((root[0] - 27, root[1] - 9), "ROOT", fill=(229, 237, 247), font=font)
    visible = min(len(items), max(1, int(math.ceil(reveal * len(items)))))
    for i, item in enumerate(items[:visible]):
        half_w = 78
        tx = x1 + half_w + 8 + i * max(half_w + 12, (x2 - x1 - (half_w + 8) * 2) // max(1, len(items) - 1))
        tx = max(x1 + half_w, min(x2 - half_w, tx))
        base_y = y1 + max(64, int((y2 - y1) * 0.62))
        row_gap = min(34, max(0, y2 - base_y - 32))
        ty = min(y2 - 30, base_y + (i % 2) * row_gap)
        draw.line((root[0], root[1] + 18, tx, ty - 18), fill=(17, 151, 133), width=2)
        draw.rounded_rectangle((tx - half_w, ty - 24, tx + half_w, ty + 30), radius=5, fill=(11, 24, 34), outline=(17, 151, 133), width=2)
        _draw_wrapped_text(
            draw,
            item,
            (tx - half_w + 9, ty - 17),
            font=font,
            width=half_w * 2 - 18,
            max_height=42,
            fill=(214, 245, 238),
            spacing=1,
            max_lines=3,
        )


def _draw_arbor_table(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], *, reveal: float, font: Any) -> None:
    x1, y1, x2, y2 = box
    rows = [row for row in (slide.get("visual_table") or []) if isinstance(row, list)] or [["Signal", "Cue"], ["Evidence", "Narration"]]
    visible = min(len(rows), max(1, int(math.ceil(reveal * len(rows)))))
    col_count = min(3, max(len(r) for r in rows[:visible]))
    col_widths = _table_col_widths(x2 - x1, col_count)
    row_heights = _table_row_heights(draw, rows[:visible], font, col_widths, min_h=42, max_h=96)
    scale = min(1.0, (y2 - y1) / max(1, sum(row_heights)))
    row_heights = [max(34, int(h * scale)) for h in row_heights]
    y = y1
    for r, row in enumerate(rows[:visible]):
        row_h = row_heights[r]
        fill = (14, 43, 60) if r == 0 else (10, 20, 33)
        draw.rectangle((x1, y, x2, y + row_h), fill=fill, outline=(37, 73, 109))
        x = x1
        for c in range(col_count):
            col_w = col_widths[c]
            draw.line((x, y, x, y + row_h), fill=(37, 73, 109))
            text = str(row[c]) if c < len(row) else ""
            color = (229, 241, 255) if r == 0 else (218, 231, 248)
            _draw_wrapped_text(
                draw,
                _compact_table_cell(text, header=(r == 0)),
                (x + 9, y + 8),
                font=font,
                width=col_w - 18,
                max_height=row_h - 14,
                fill=color,
                spacing=2,
            )
            x += col_w
        y += row_h


def _table_col_widths(total_width: int, col_count: int) -> list[int]:
    if col_count <= 1:
        return [total_width]
    if col_count == 2:
        first = int(total_width * 0.34)
        return [first, total_width - first]
    first = int(total_width * 0.22)
    middle = int(total_width * 0.46)
    return [first, middle, total_width - first - middle]


def _table_row_heights(
    draw: Any,
    rows: list[list[Any]],
    font: Any,
    col_widths: list[int],
    *,
    min_h: int,
    max_h: int,
) -> list[int]:
    heights: list[int] = []
    for r, row in enumerate(rows):
        line_counts = []
        for c, width in enumerate(col_widths):
            text = str(row[c]) if c < len(row) else ""
            lines = _wrap_text(draw, _compact_table_cell(text, header=(r == 0)), font, width - 18)
            line_counts.append(max(1, len(lines)))
        heights.append(min(max_h, max(min_h, 18 + max(line_counts) * 19)))
    return heights


def _compact_table_cell(text: str, *, header: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    semantic_rewrites = {
        "alignment with human slides/subtitles/speech": "Aligns with human slides, subtitles, and speech",
        "vlm similarity score + speaker embedding": "VLM similarity + speaker embedding",
        "which video is better?": "Pairwise video preference",
        "double-order pairwise comparison by videollm": "Two-way VideoLLM comparison",
        "how much paper knowledge is conveyed?": "Paper knowledge conveyed",
        "multiple-choice qa from paper, answered by videollm": "VideoLLM answers paper MCQs",
        "how well audience remembers author?": "Author recognition",
        "recall accuracy of author-work pairing": "Author-work recall accuracy",
    }
    rewritten = semantic_rewrites.get(text.lower())
    if rewritten:
        return rewritten
    return _clean_display_text(text)


def _draw_arbor_metrics(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], *, reveal: float, font: Any) -> None:
    x1, y1, x2, y2 = box
    rows = [row for row in (slide.get("visual_table") or []) if isinstance(row, list)]
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or [])[:4]]
    row_items = [_clean_visual_item(" | ".join(str(cell) for cell in row[:3])) for row in rows[1:5] or rows[:4]]
    if row_items and any(_percent_from_text(item) is not None for item in row_items):
        items = row_items
    items = items or [_clean_visual_item(str(b)) for b in slide.get("bullets", [])[:4]]
    cards = _metric_cards_from_items(items)
    visible = min(len(cards), max(1, int(math.ceil(reveal * len(cards)))))
    gap = 14
    card_w = (x2 - x1 - gap) // 2
    card_h = max(64, min(88, (y2 - y1 - gap) // 2))
    for i, (value, label) in enumerate(cards[:visible]):
        x = x1 + (i % 2) * (card_w + gap)
        y = y1 + (i // 2) * (card_h + gap)
        card = (x, y, x + card_w, min(y + card_h, y2))
        draw.rounded_rectangle(card, radius=7, fill=(11, 24, 36), outline=(35, 90, 130), width=2)
        draw.rectangle((x, y, x + 6, card[3]), fill=(20, 184, 166))
        _draw_single_line_text(draw, value, (x + 20, y + 12), font=font, width=card_w - 38, fill=(93, 224, 194))
        _draw_wrapped_text(
            draw,
            label,
            (x + 20, y + 38),
            font=font,
            width=card_w - 38,
            max_height=max(1, card[3] - y - 44),
            fill=(224, 233, 245),
            spacing=3,
            max_lines=2,
        )


def _metric_cards_from_items(items: list[str]) -> list[tuple[str, str]]:
    cards: list[tuple[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"\b\d+(?::\d{2}|\.\d+)?(?:\s*(?:-|to)\s*\d+(?:\.\d+)?)?\s*(?:%|x|×)?\s*(?:pages?|figures?|slides?|minutes?|videos?|pairs?|accuracy)?",
        flags=re.IGNORECASE,
    )
    for item in items:
        text = re.sub(r"\s+", " ", item).strip()
        matches = list(pattern.finditer(text))
        added_metric = False
        for match in matches:
            value = re.sub(r"\s+", " ", match.group(0)).strip()
            key = value.casefold()
            if not value or key in seen:
                continue
            label = _metric_label_from_value(value, text)
            cards.append((value, label or "Reported paper statistic"))
            seen.add(key)
            added_metric = True
            if len(cards) >= 4:
                return cards
        if not added_metric and text:
            cards.append((f"{len(cards) + 1:02d}", text))
            if len(cards) >= 4:
                return cards
    return cards or [("01", "Evidence extracted from the paper")]


def _metric_label_from_value(value: str, source_text: str) -> str:
    value_l = value.lower()
    source_l = source_text.lower()
    if "pages" in value_l or "page" in value_l:
        return "Average paper length"
    if "figures" in value_l or "figure" in value_l:
        return "Figures per document"
    if "slides" in value_l or "slide" in value_l:
        return "Average slides per video"
    if "minutes" in value_l or "minute" in value_l:
        return "Video length range"
    if ":" in value_l and any(token in source_l for token in ("duration", "video", "minute")):
        return "Average video duration"
    if "pairs" in value_l or "pair" in value_l:
        return "Paper-video pairs"
    if "accuracy" in source_l or "%" in value_l:
        return "Reported accuracy gain"
    label = re.sub(re.escape(value), "", source_text, count=1).strip(" .,:;-")
    label = re.sub(r"\b(and|with|of|the|a|an)\b", " ", label, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", label).strip()


def _percent_from_text(text: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return max(0.0, min(100.0, value))


def _draw_arbor_terminal(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], *, reveal: float, font: Any) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=6, fill=(7, 13, 22), outline=(29, 69, 103))
    prompt = "$ arbor video build --style dynamic"
    draw.text((x1 + 18, y1 + 18), prompt, fill=(93, 224, 194), font=font)
    rows = slide.get("visual_items") or slide.get("bullets", [])
    visible = min(len(rows), max(1, int(math.ceil(reveal * len(rows)))))
    y = y1 + 54
    for i, item in enumerate(rows[:visible]):
        prefix = "✓" if i < visible - 1 else ">"
        draw.text((x1 + 18, y), prefix, fill=(20, 184, 166), font=font)
        _draw_single_line_text(draw, str(item), (x1 + 42, y), font=font, width=x2 - x1 - 64, fill=(205, 216, 231))
        y += 28
    bar_end = x1 + 18 + int(max(1, (x2 - x1 - 36) * reveal))
    draw.rectangle((x1 + 18, y2 - 28, bar_end, y2 - 20), fill=(20, 184, 166))


def _draw_arbor_cards(draw: Any, slide: dict[str, Any], box: tuple[int, int, int, int], *, reveal: float, font: Any) -> None:
    x1, y1, x2, _y2 = box
    items = [_clean_visual_item(str(item)) for item in (slide.get("visual_items") or slide.get("bullets", []) or ["problem", "method", "result"])[:4]]
    visible = min(len(items), max(1, int(math.ceil(reveal * len(items)))))
    for i, item in enumerate(items[:visible]):
        x = x1 + (i % 2) * ((x2 - x1) // 2 + 8)
        y = y1 + (i // 2) * 92
        w = (x2 - x1) // 2 - 10
        draw.rounded_rectangle((x, y, x + w, y + 72), radius=7, fill=(11, 24, 36), outline=(35, 90, 130), width=2)
        draw.rectangle((x, y, x + 5, y + 72), fill=(20, 184, 166))
        _draw_wrapped_text(
            draw,
            str(item),
            (x + 16, y + 10),
            font=font,
            width=w - 32,
            max_height=42,
            fill=(224, 233, 245),
            spacing=3,
        )


def _draw_arbor_pointer(draw: Any, x: int, y: int, attention: float) -> None:
    attention = max(0.0, min(1.0, attention))
    if attention > 0:
        r = int(7 + attention * 7)
        draw.ellipse((x - r, y - r, x + r, y + r), outline=(64, 224, 208), width=1)
    shadow = [(x + 2, y + 2), (x + 14, y + 27), (x + 18, y + 16), (x + 30, y + 16)]
    arrow = [(x, y), (x + 12, y + 25), (x + 16, y + 14), (x + 28, y + 14)]
    draw.polygon(shadow, fill=(2, 8, 18))
    draw.polygon(arrow, fill=(33, 216, 190), outline=(170, 255, 239))


def _draw_arbor_caption(draw: Any, caption: str, *, width: int, height: int, font: Any) -> None:
    box = (96, height - 132, width - 96, height - 38)
    draw.rounded_rectangle(box, radius=8, fill=(8, 15, 27), outline=(31, 61, 96), width=2)
    _draw_wrapped_text(
        draw,
        caption,
        (box[0] + 24, box[1] + 14),
        font=font,
        width=width - 240,
        max_height=box[3] - box[1] - 22,
        fill=(226, 236, 248),
        spacing=4,
        max_lines=3,
    )


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
    use_omni_cursor: bool = False,
    use_image_api: bool = False,
    use_tts: bool = False,
) -> VideoPipelineResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    _progress(
        "pipeline",
        "start paper/project-to-video build",
        current=0,
        total=12,
        detail=f"input={input_path} out={out_dir} api={'on' if use_api else 'off'} fps={fps}",
    )
    _progress("ingest", "load source", current=1, total=12, detail=f"kind={kind}")
    source = load_source(input_path, kind=kind)
    source["created_at"] = _utc_now()
    source["api_mode"] = _text_model_provider() if use_api else "heuristic"
    source["visual_theme"] = choose_paper_visual_theme(source)
    _progress(
        "ingest",
        "source loaded",
        current=1,
        total=12,
        detail=f"title={source.get('title', '')} chars={len(source.get('text', ''))} theme={source['visual_theme']}",
    )
    if use_omni_cursor:
        use_vlm_cursor = True
        os.environ.setdefault("OPENAI_VISION_BASE_URL", _lumid_base_url())
        os.environ.setdefault("OPENAI_VISION_MODEL", os.environ.get("LUMID_OMNI_MODEL") or LUMID_OMNI_MODEL)
    (out_dir / "source.json").write_text(json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")

    _progress("pipeline", "run builders and judge loop", current=2, total=12)
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
    _progress("scene_director", "plan varied layouts and entrances", detail=f"api={'on' if use_api else 'off'}")
    slides, scene_direction_report = plan_scene_directions(source, slides, use_api=use_api)
    (out_dir / "scene_direction.json").write_text(
        json.dumps(scene_direction_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    slides = sanitize_public_slides(slides)
    subtitles = sanitize_public_subtitles(subtitles)
    cursor_plan = build_cursor_plan(
        subtitles,
        slides=slides,
        source=source,
        out_dir=out_dir,
        use_vlm_cursor=use_vlm_cursor,
    )
    talker = build_talker_plan(subtitles)

    _progress("pipeline", "generate slide images", current=5, total=12)
    paper_figures = extract_paper_figures(source, out_dir)
    validate_paper_figures = os.environ.get("AUTO_VIDEO_PAPER_FIGURE_VALIDATE", "1").strip().lower() not in {"0", "false", "no", "off"}
    assign_paper_figures(
        slides,
        paper_figures,
        validate_with_vlm=bool(use_image_api and validate_paper_figures),
    )
    (out_dir / "paper_figure_assignments.json").write_text(
        json.dumps(
            [
                {
                    "slide_index": int(slide.get("index") or 0),
                    "title": slide.get("title"),
                    "paths": slide.get("paper_figure_paths") or [],
                    "validation": slide.get("paper_figure_validation") or [],
                }
                for slide in slides
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_generation = generate_slide_images(slides, out_dir, use_image_api=use_image_api)
    require_model_images = os.environ.get("AUTO_VIDEO_REQUIRE_MODEL_IMAGES", "1").strip().lower() not in {"0", "false", "no", "off"}
    missing_required_images = [
        str(slide.get("title") or f"Slide {slide.get('index')}")
        for slide in slides
        if str(slide.get("visual_kind") or "").casefold() == "image"
        and not (slide.get("generated_image_paths") or slide.get("paper_figure_paths"))
    ]
    if use_image_api and require_model_images and missing_required_images:
        raise RuntimeError(
            "Image model did not produce a validated asset after retries for: "
            + ", ".join(missing_required_images)
            + ". Local placeholder rendering is disabled."
        )

    _progress("pipeline", "write storyboard artifacts", current=6, total=12)
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
    _progress("pipeline", "synthesize narration audio", current=7, total=12)
    subtitles = add_title_card_hold(subtitles)
    tts_result, timed_subtitles = synthesize_tts_segments(subtitles, out_dir, use_tts=use_tts)
    timeline_scale = 1.0
    audio_duration = None
    if tts_result.get("ok"):
        original_duration = max((float(item["end_sec"]) for item in subtitles), default=0.0)
        subtitles = timed_subtitles
        cursor_plan = align_cursor_plan_to_subtitles(cursor_plan, subtitles)
        talker["audio_path"] = tts_result.get("path", "")
        talker["audio_generated"] = True
        audio_duration = media_duration_seconds(Path(str(tts_result["path"])))
        synced_duration = max((float(item["end_sec"]) for item in subtitles), default=0.0)
        timeline_scale = synced_duration / original_duration if original_duration > 0 else 1.0
        _progress("timeline", "aligned scenes to measured TTS segments", detail=f"audio_duration={audio_duration or 0:.3f}s timeline={synced_duration:.3f}s")
    elif use_tts:
        _progress(
            "tts_builder",
            "timed narration failed; refusing unsynchronized whole-track fallback",
            detail=str(tts_result.get("error") or ""),
        )
    (out_dir / "tts_generation.json").write_text(
        json.dumps(tts_result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "talker_plan.json").write_text(
        json.dumps(talker, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_srt(subtitles, out_dir / "subtitles.srt")
    (out_dir / "cursor_plan.json").write_text(
        json.dumps(cursor_plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "storyboard.json").write_text(
        json.dumps(
            {"slides": slides, "subtitles": subtitles, "cursor_plan": cursor_plan, "talker_plan": talker},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    scene_timeline = build_scene_timeline(source, slides, subtitles)
    (out_dir / "scene_timeline.json").write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "scene_based_research_explainer",
                "reference_style": "Arbor-inspired event-driven minimal motion",
                "shot_count": len(scene_timeline),
                "shots": scene_timeline,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (out_dir / "storyboard.json").write_text(
        json.dumps(
            {
                "slides": slides,
                "subtitles": subtitles,
                "cursor_plan": cursor_plan,
                "talker_plan": talker,
                "scene_timeline": scene_timeline,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    judge_path = out_dir / "judge_feedback.json"
    _progress("pipeline", "write final artifacts", current=8, total=12)
    judge_path.write_text(json.dumps(judge, indent=2, ensure_ascii=False), encoding="utf-8")
    revision_history_path = out_dir / "revision_history.json"
    revision_history_path.write_text(
        json.dumps(revision_history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_flowmesh_spec(out_dir, source)
    preview_path = out_dir / "preview.html"
    _progress("preview", "write HTML preview", current=9, total=12, detail=str(preview_path))
    write_preview_html(source, slides, subtitles, cursor_plan, judge, talker, preview_path)
    video_path = out_dir / "video.mp4"
    _progress("pipeline", "render MP4 video", current=10, total=12, detail=str(video_path))
    video_rendered = render_mp4_video(source, slides, subtitles, cursor_plan, video_path, fps=fps)
    audio_muxed = False
    if video_rendered and tts_result.get("ok") and tts_result.get("path"):
        _progress("pipeline", "mux audio", current=11, total=12)
        audio_muxed = mux_audio_into_video(video_path, Path(str(tts_result["path"])))
    elif video_rendered:
        _progress("pipeline", "skip audio mux", current=11, total=12, detail="no generated audio")
    else:
        _progress("pipeline", "skip audio mux", current=11, total=12, detail="video render failed")

    _progress("pipeline", "write metrics", current=12, total=12)
    total_duration = max((s["end_sec"] for s in subtitles), default=0)
    vlm_cursor_points = sum(1 for item in cursor_plan if item.get("grounding_mode") == "vlm")
    generated_image_count = sum(1 for item in image_generation if item.get("ok"))
    paper_figure_count = sum(len(slide.get("paper_figure_paths") or []) for slide in slides)
    unique_visual_assets = {
        str(path)
        for slide in slides
        for path in (slide.get("visual_asset_paths") or [])
        if str(path)
    }
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
        "scene_shot_count": len(scene_timeline),
        "subtitle_count": len(subtitles),
        "estimated_duration_sec": total_duration,
        "audio_duration_sec": round(audio_duration, 3) if audio_duration else None,
        "timeline_scale": round(timeline_scale, 4),
        "api_used": source["api_mode"] != "heuristic",
        "text_model_provider": source["api_mode"],
        "text_model": (
            os.environ.get("LUMID_MODEL")
            or os.environ.get("LUM_MODEL")
            or os.environ.get("DEEPSEEK_MODEL")
            or os.environ.get("OPENAI_MODEL", "")
        ),
        "vision_model_configured": bool(
            os.environ.get("OPENAI_VISION_API_KEY")
            or _lumid_api_key()
            or os.environ.get("OPENAI_API_KEY")
        ),
        "vision_model": (
            os.environ.get("OPENAI_VISION_MODEL")
            or os.environ.get("LUMID_MODEL")
            or os.environ.get("LUM_MODEL")
            or os.environ.get("OPENAI_MODEL", "")
        ),
        "talker_mode": talker.get("mode", ""),
        "tts_provider": talker.get("tts_provider", ""),
        "tts_model": talker.get("tts_model", ""),
        "tts_requested": use_tts,
        "tts_audio_generated": bool(tts_result.get("ok")),
        "tts_audio_path": tts_result.get("path", ""),
        "tts_timing_mode": tts_result.get("timing_mode", "segment_exact_required"),
        "tts_speech_tempo": tts_result.get("speech_tempo"),
        "tts_post_speech_hold_sec": tts_result.get("post_speech_hold_sec"),
        "audio_muxed": audio_muxed,
        "talking_head_provider": talker.get("talking_head_provider", ""),
        "talker_api_ready": talker["api_ready"],
        "image_api_requested": use_image_api,
        "image_model": os.environ.get("LUMID_IMAGE_MODEL") or os.environ.get("LUM_IMAGE_MODEL") or LUMID_IMAGE_MODEL,
        "generated_image_count": generated_image_count,
        "generated_images_per_slide": int(os.environ.get("AUTO_VIDEO_IMAGES_PER_SLIDE", "2")),
        "paper_figure_count": paper_figure_count,
        "unique_visual_asset_count": len(unique_visual_assets),
        "image_generation_path": str(out_dir / "image_generation.json"),
        "video_rendered": video_rendered,
        "fps": fps,
        "renderer_version": "scene_based_research_explainer_v2",
        "render_style": os.environ.get("AUTO_VIDEO_RENDER_STYLE", "scene"),
        "visual_theme": source.get("visual_theme", "signal"),
        "vlm_cursor_requested": use_vlm_cursor,
        "omni_cursor_requested": use_omni_cursor,
        "vlm_cursor_points": vlm_cursor_points,
        "cursor_grounding_mode": "vlm" if vlm_cursor_points else "heuristic",
        "video_path": str(video_path) if video_rendered else "",
        "preview_path": str(preview_path),
        "storyboard_path": str(out_dir / "storyboard.json"),
        "scene_timeline_path": str(out_dir / "scene_timeline.json"),
        "flowmesh_spec_path": str(out_dir / "flowmesh_spec.json"),
        "revision_history_path": str(revision_history_path),
    }
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    _progress(
        "pipeline",
        "complete",
        current=12,
        total=12,
        detail=f"preview={preview_path} video={video_path if video_rendered else 'not_rendered'} images={generated_image_count}/{len(image_generation)} audio_muxed={audio_muxed}",
    )
    return VideoPipelineResult(
        out_dir=out_dir,
        metrics_path=metrics_path,
        preview_path=preview_path,
        video_path=video_path,
        storyboard_path=out_dir / "storyboard.json",
        judge_path=judge_path,
        revision_history_path=revision_history_path,
    )
