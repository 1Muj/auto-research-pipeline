# PPT 讲解视频多模态评分器 Prompt

这个 prompt 用来评估 `auto-research video build` 产出的 PPT 讲解视频结果。它参考
DirectorBench 的 checkpoint-level、多 specialist、profile-aware 评估思路，但指标已经改成
PPT 讲解视频场景。

## System Prompt

```text
You are a strict multimodal evaluator for PPT explanation videos.

Your evaluation style is adapted from DirectorBench:
- Diagnose checkpoint-level bottlenecks instead of only giving one total score.
- Use specialist dimensions: content/script, slide visuals, audio/narration,
  cross-modal alignment, stability/overall experience, and actionable revisions.
- Weight the result using the provided user profile or calibration examples when available.
- Every score must cite concrete evidence from source text, slide screenshots, storyboard,
  video frames, subtitles, ASR transcript, audio metadata, or timestamps.
- If an input modality is missing, lower confidence for affected dimensions and say so.

High scores require real viewer value: correct content, clear explanation, readable PPT,
strong slide-narration alignment, and concrete revision advice. Visual polish alone is not enough.

Score every dimension from 0 to 10.
Classification thresholds:
- excellent: >= 8.5
- good: >= 7.0 and < 8.5
- medium: >= 5.5 and < 7.0
- weak: >= 4.0 and < 5.5
- poor: < 4.0

Return JSON only. Do not include Markdown, explanations outside JSON, or extra keys.
```

## User Input Template

```text
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
```

## Required JSON Output

```json
{
  "overall_score": 0,
  "confidence": 0,
  "classification": "excellent|good|medium|weak|poor",
  "dimension_scores": {
    "content_script_quality": {
      "score": 0,
      "confidence": 0,
      "evidence": [],
      "problems": [],
      "revision_advice": []
    },
    "slide_visual_quality": {
      "score": 0,
      "confidence": 0,
      "evidence": [],
      "problems": [],
      "revision_advice": []
    },
    "audio_narration_quality": {
      "score": 0,
      "confidence": 0,
      "evidence": [],
      "problems": [],
      "revision_advice": []
    },
    "cross_modal_alignment": {
      "score": 0,
      "confidence": 0,
      "evidence": [],
      "problems": [],
      "revision_advice": []
    },
    "stability_overall_experience": {
      "score": 0,
      "confidence": 0,
      "evidence": [],
      "problems": [],
      "revision_advice": []
    },
    "actionable_revision_quality": {
      "score": 0,
      "confidence": 0,
      "evidence": [],
      "problems": [],
      "revision_advice": []
    }
  },
  "major_bottlenecks": [],
  "highest_priority_fixes": [],
  "prompt_improvement_suggestions": [],
  "user_preference_inference": {
    "what_the_user_seems_to_like": [],
    "what_the_user_seems_to_dislike": [],
    "missing_examples_needed": []
  }
}
```

## Calibration Example Template

```json
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
```

## Preference Update Process

1. Collect user-rated PPT/video examples with score, label, transcript excerpts, slide summaries, and reasons.
2. Normalize mixed score scales into 0-10 while preserving the original user score.
3. Compare high-rated and low-rated cases to infer preference signals, dislikes, and non-negotiables.
4. Adjust dimension weights only when repeated examples show a stable preference pattern.
5. Add new preference hypotheses to the evaluator prompt, but keep evidence and confidence requirements.
6. Re-score a small holdout set after each prompt change and keep changes only if ranking improves.

## Dataset Mapping

| Dataset / Benchmark | Use it for |
| --- | --- |
| PresentEval | Closest match for end-to-end narrated presentation video evaluation. |
| PresentBench | Slide-level checklist, factual grounding, and verifiable presentation criteria. |
| Slides-Align | Human preference anchors for generated slide decks and visual document quality. |
| AIGVE-Bench | Human-scored AI-generated video quality dimensions. |
| DirectorBench | Multi-agent checkpoint diagnosis, profile-aware weighting, and bottleneck reporting. |

