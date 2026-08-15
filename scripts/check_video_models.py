from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from auto_research.video_pipeline import (
    _call_lumid_image,
    _call_openai_compatible,
    _call_openai_vision,
    _lumid_api_key,
    synthesize_tts_audio,
)


def main() -> None:
    out_dir = Path("/tmp/auto_model_smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {"key_loaded": bool(_lumid_api_key())}

    try:
        text = _call_openai_compatible('{"task":"Return JSON only","answer":"ok"}')
        results["text_model"] = {"ok": bool(text and text.strip()), "excerpt": (text or "")[:240]}
    except Exception as exc:
        results["text_model"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        image_path = out_dir / "gpt_image_smoke.png"
        ok, err = _call_lumid_image(
            "Clean abstract academic diagram, no text, no UI, no screenshot, complete shapes inside frame.",
            image_path,
        )
        results["image_model"] = {
            "ok": bool(ok and image_path.is_file() and image_path.stat().st_size > 0),
            "path": str(image_path) if image_path.exists() else "",
            "bytes": image_path.stat().st_size if image_path.exists() else 0,
            "error": err,
        }
    except Exception as exc:
        results["image_model"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        tts = synthesize_tts_audio(
            {"narration_text": "This is a short audio test for the PPT video pipeline."},
            out_dir,
            use_tts=True,
        )
        audio_path_value = str(tts.get("path") or "")
        audio_path = Path(audio_path_value) if audio_path_value else None
        results["tts_model"] = {
            "ok": bool(tts.get("ok") and audio_path and audio_path.is_file() and audio_path.stat().st_size > 0),
            "path": str(audio_path) if audio_path and audio_path.exists() else "",
            "bytes": audio_path.stat().st_size if audio_path and audio_path.exists() else 0,
            "error": tts.get("error", ""),
        }
    except Exception as exc:
        results["tts_model"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        vision_path = out_dir / "vision_test.png"
        img = Image.new("RGB", (320, 180), (245, 248, 252))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 50, 140, 130), fill=(40, 160, 220))
        draw.ellipse((185, 55, 275, 145), fill=(250, 180, 60))
        img.save(vision_path)
        vision = _call_openai_vision(
            'Return JSON only: {"ok":true,"description":"..."}. Describe the simple shapes.',
            vision_path,
        )
        results["vision_model"] = {"ok": bool(vision and vision.strip()), "excerpt": (vision or "")[:300]}
    except Exception as exc:
        results["vision_model"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
