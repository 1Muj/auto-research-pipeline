from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from auto_research.video_pipeline import (
    _call_openai_compatible,
    _json_from_model,
    _normalize_slide,
    build_slides,
    build_cursor_plan,
    build_subtitles,
    build_talker_plan,
    has_audio_stream,
    decide_target_slide_count,
    media_duration_seconds,
    mux_audio_into_video,
    render_mp4_video,
    align_cursor_plan_to_subtitles,
    scale_timeline_to_duration,
    synthesize_tts_audio,
    synthesize_tts_segments,
    write_preview_html,
    write_srt,
)

INTERNAL_MARKERS = [
    "Judge note",
    "Revision pass",
    "Revision focus",
    "judge feedback",
    "slide_builder",
    "subtitle_builder",
    "cursor_builder",
    "talker_builder",
]

INTERNAL_PATTERNS = [
    re.compile(r"\bJudge note:.*?(?=(?:[.!?]\s+[A-Z])|$)", re.IGNORECASE),
    re.compile(r"\bRevision pass(?:\s+\d+)?:.*?(?=(?:[.!?]\s+[A-Z])|$)", re.IGNORECASE),
    re.compile(r"\bRevision focus:.*?(?=(?:[.!?]\s+[A-Z])|$)", re.IGNORECASE),
    re.compile(r"\b(?:slide_builder|subtitle_builder|cursor_builder|talker_builder)\b", re.IGNORECASE),
]


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _clean_text(text: Any) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    for pattern in INTERNAL_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s+([.!?,;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;")
    return cleaned


def _contains_internal_text(value: Any) -> bool:
    text = str(value or "")
    return any(marker.lower() in text.lower() for marker in INTERNAL_MARKERS)


def _clean_list(items: Any, *, fallback: list[str] | None = None) -> list[str]:
    if not isinstance(items, list):
        return fallback or []
    cleaned = [_clean_text(item) for item in items]
    cleaned = [item for item in cleaned if item and not _contains_internal_text(item)]
    return cleaned or (fallback or [])


def _clean_slide(slide: dict[str, Any]) -> dict[str, Any]:
    item = dict(slide)
    item["title"] = _clean_text(item.get("title")) or str(slide.get("title") or "Slide")
    item["purpose"] = _clean_text(item.get("purpose"))
    item["bullets"] = _clean_list(item.get("bullets"), fallback=["Explain the core idea clearly."])[:4]
    note = _clean_text(item.get("speaker_note"))
    if not note or _contains_internal_text(note):
        note = " ".join(item["bullets"][:3])
    item["speaker_note"] = note[:900]
    item["visual_prompt"] = _clean_text(item.get("visual_prompt"))
    item["visual_caption"] = _clean_text(item.get("visual_caption"))
    item["visual_items"] = _clean_list(item.get("visual_items"), fallback=item["bullets"])[:6]
    if isinstance(item.get("visual_table"), list):
        table: list[list[str]] = []
        for row in item["visual_table"][:5]:
            if isinstance(row, list):
                clean_row = [_clean_text(cell)[:100] for cell in row[:4]]
                if clean_row and not any(_contains_internal_text(cell) for cell in clean_row):
                    table.append(clean_row)
        item["visual_table"] = table
    return item


def _summarize_eval(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_score": evaluation.get("overall_score"),
        "classification": evaluation.get("classification"),
        "major_bottlenecks": evaluation.get("major_bottlenecks", []),
        "highest_priority_fixes": evaluation.get("highest_priority_fixes", []),
    }


def _extract_slide_payload(data: Any) -> list[Any]:
    if not isinstance(data, dict):
        return []
    candidates = [
        data.get("slides"),
        data.get("repaired_slides"),
        data.get("revised_slides"),
        data.get("storyboard", {}).get("slides") if isinstance(data.get("storyboard"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            return candidate
    return []


def _model_repair_slides(
    source: dict[str, Any],
    slides: list[dict[str, Any]],
    evaluation: dict[str, Any],
    *,
    target_slides: int,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
    source_chars = 16000
    source_text = str(source.get("text") or "")[:source_chars]
    eval_summary = _summarize_eval(evaluation)
    dimension_scores = evaluation.get("dimension_scores") if isinstance(evaluation.get("dimension_scores"), dict) else {}
    info: dict[str, Any] = {"attempted": True, "accepted": False, "reason": ""}
    prompt = f"""
You are repairing a PPT explanation video storyboard after evaluator feedback.
Return JSON only, with exactly this shape:
{{"slides":[{{"title":"...","purpose":"...","bullets":["..."],"speaker_note":"...","visual_kind":"image|flow|table|metrics","visual_caption":"...","visual_items":["..."],"visual_table":[["Metric","Value","Meaning"]]}}]}}

Repair goals:
- Create exactly {target_slides} slides.
- Give every slide a unique job in the story. No repeated bullets across slides.
- Use specific, audience-friendly titles, not only "Motivation", "Core Idea", "Workflow", "Evidence", or "Limitations".
- Each slide should have 2 or 3 short bullets, each under 18 words.
- Speaker notes should be natural narration, 55 to 90 words per slide.
- Remove garbled OCR, raw bibliography entries, raw table dumps, repeated citations, checkmark/cross symbol lists, and half sentences.
- Preserve only source-grounded facts that are clear enough to explain.
- Make narration refer to the slide's actual visual focus.
- Do not mention evaluator feedback, repair, revision, JSON, modules, or pipeline internals in user-visible content.

Evaluator summary:
{json.dumps(eval_summary, ensure_ascii=False)}

Dimension feedback:
{json.dumps(dimension_scores, ensure_ascii=False)[:9000]}

Current storyboard:
{json.dumps(slides, ensure_ascii=False)[:12000]}

Source title: {source.get("title", "")}
Source excerpt:
{source_text}
""".strip()
    raw = _call_openai_compatible(prompt)
    data = _json_from_model(raw)
    revised = _extract_slide_payload(data)
    info["raw_response_excerpt"] = str(raw or "")[:800]
    if not revised:
        info["reason"] = "model_response_missing_slides"
        return None, info
    if len(revised) < target_slides:
        info["reason"] = f"model_returned_{len(revised)}_slides_expected_{target_slides}_padded_with_source"
        fallback = build_slides(source, max_slides=target_slides, use_api=False)
        revised = [*revised, *fallback[len(revised) :]]
    normalized = [_normalize_slide(i, item) for i, item in enumerate(revised[:target_slides], start=1)]
    cleaned = [_clean_slide(slide) for slide in normalized]
    info["accepted"] = True
    info["returned_slide_count"] = len(revised)
    return cleaned, info


def repair_video_artifacts(
    artifact_dir: Path,
    evaluation: dict[str, Any],
    *,
    fps: int = 24,
    seconds_per_slide: int = 22,
    use_api: bool = False,
    use_tts: bool = False,
    target_slides: int | None = None,
) -> dict[str, Any]:
    """Repair final artifacts using evaluator advice, then re-render the MP4.

    The API path rewrites the storyboard from evaluator advice. The fallback remains
    deterministic: remove internal leakage, rebuild timed plans, and render again.
    """
    source = _read_json(artifact_dir / "source.json", {})
    storyboard = _read_json(artifact_dir / "storyboard.json", {})
    judge = _read_json(artifact_dir / "judge_feedback.json", {})
    slides = storyboard.get("slides") if isinstance(storyboard.get("slides"), list) else []
    cleaned_slides = [_clean_slide(slide) for slide in slides if isinstance(slide, dict)]
    if target_slides and target_slides > 0:
        desired_slide_count = max(1, int(target_slides))
    else:
        repair_cap = int(os.environ.get("AUTO_VIDEO_REPAIR_MAX_SLIDES", os.environ.get("MAX_SLIDES", "10")))
        desired_slide_count = decide_target_slide_count(
            source,
            max_slides=repair_cap,
            use_api=use_api,
        )
    repair_mode = "deterministic_eval_repair"
    model_repair_info: dict[str, Any] = {"attempted": False, "accepted": False}
    if use_api and cleaned_slides:
        model_slides, model_repair_info = _model_repair_slides(
            source,
            cleaned_slides,
            evaluation,
            target_slides=desired_slide_count,
        )
        if model_slides:
            cleaned_slides = model_slides
            repair_mode = "model_guided_eval_repair"
    if len(cleaned_slides) < desired_slide_count:
        fallback = build_slides(source, max_slides=desired_slide_count, use_api=False)
        cleaned_slides = [*cleaned_slides, *fallback[len(cleaned_slides) : desired_slide_count]]
    subtitles = build_subtitles(cleaned_slides, seconds_per_slide=seconds_per_slide)
    cursor_plan = build_cursor_plan(subtitles, slides=cleaned_slides, source=source, out_dir=artifact_dir)
    talker = build_talker_plan(subtitles)
    tts_result, timed_subtitles = synthesize_tts_segments(subtitles, artifact_dir, use_tts=use_tts)
    audio_duration = None
    timeline_scale = 1.0
    if tts_result.get("ok"):
        original_duration = max((float(item["end_sec"]) for item in subtitles), default=0.0)
        subtitles = timed_subtitles
        cursor_plan = align_cursor_plan_to_subtitles(cursor_plan, subtitles)
        talker["audio_path"] = tts_result.get("path", "")
        talker["audio_generated"] = True
        audio_duration = media_duration_seconds(Path(str(tts_result["path"])))
        synced_duration = max((float(item["end_sec"]) for item in subtitles), default=0.0)
        timeline_scale = synced_duration / original_duration if original_duration > 0 else 1.0
    elif use_tts:
        tts_result = synthesize_tts_audio(talker, artifact_dir, use_tts=True)
        if tts_result.get("ok"):
            talker["audio_path"] = tts_result.get("path", "")
            talker["audio_generated"] = True
            audio_duration = media_duration_seconds(Path(str(tts_result["path"])))
            if audio_duration:
                subtitles, cursor_plan, timeline_scale = scale_timeline_to_duration(subtitles, cursor_plan, audio_duration)

    repaired_storyboard = {
        "slides": cleaned_slides,
        "subtitles": subtitles,
        "cursor_plan": cursor_plan,
        "talker_plan": talker,
        "repair_source": {"mode": repair_mode},
    }
    cleaned_judge = {
        "overall_score_before_repair": judge.get("overall_score"),
        "repair_mode": repair_mode,
        "repair_note": "Final slide and subtitle artifacts were cleaned and rebuilt after evaluator feedback.",
    }
    _write_json(artifact_dir / "storyboard.json", repaired_storyboard)
    _write_json(artifact_dir / "cursor_plan.json", cursor_plan)
    _write_json(artifact_dir / "talker_plan.json", talker)
    _write_json(artifact_dir / "tts_generation.json", tts_result)
    _write_json(artifact_dir / "judge_feedback.json", cleaned_judge)
    write_srt(subtitles, artifact_dir / "subtitles.srt")
    write_preview_html(source, cleaned_slides, subtitles, cursor_plan, cleaned_judge, talker, artifact_dir / "preview.html")
    video_path = artifact_dir / "video.mp4"
    rendered = render_mp4_video(source, cleaned_slides, subtitles, cursor_plan, video_path, fps=fps)
    audio_muxed = False
    if rendered and tts_result.get("ok") and tts_result.get("path"):
        audio_muxed = mux_audio_into_video(video_path, Path(str(tts_result["path"])))
    audio_stream_present = has_audio_stream(video_path)
    repair_report = {
        "mode": repair_mode,
        "video_rendered": rendered,
        "video_path": str(video_path) if rendered else "",
        "tts_requested": use_tts,
        "tts_audio_generated": bool(tts_result.get("ok")),
        "tts_timing_mode": tts_result.get("timing_mode", "whole_track_scaled"),
        "tts_speech_tempo": tts_result.get("speech_tempo"),
        "tts_post_speech_hold_sec": tts_result.get("post_speech_hold_sec"),
        "audio_duration_sec": round(audio_duration, 3) if audio_duration else None,
        "timeline_scale": round(timeline_scale, 4),
        "audio_muxed": audio_muxed,
        "audio_stream_present": audio_stream_present,
        "slide_count": len(cleaned_slides),
        "subtitle_count": len(subtitles),
        "removed_internal_markers": INTERNAL_MARKERS,
        "model_repair": model_repair_info,
        "evaluation_summary": _summarize_eval(evaluation),
    }
    _write_json(artifact_dir / "eval_repair_report.json", repair_report)
    metrics = _read_json(artifact_dir / "metrics.json", {})
    if isinstance(metrics, dict):
        metrics.update(
            {
                "slide_count": len(cleaned_slides),
                "subtitle_count": len(subtitles),
                "estimated_duration_sec": max((float(s["end_sec"]) for s in subtitles), default=0.0),
                "tts_requested": use_tts,
                "tts_audio_generated": bool(tts_result.get("ok")),
                "tts_audio_path": tts_result.get("path", ""),
                "audio_muxed": audio_muxed,
                "audio_stream_present": audio_stream_present,
                "video_rendered": rendered,
                "video_path": str(video_path) if rendered else "",
                "eval_repair_mode": repair_mode,
            }
        )
        _write_json(artifact_dir / "metrics.json", metrics)
    return repair_report
