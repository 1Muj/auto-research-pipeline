# AutoResearch-Video: Judge-Guided Paper and Project Presentation Generation

## Abstract

Researchers often need to turn a paper or a project repository into a short presentation video. The task is time consuming because it combines reading, slide writing, narration, visual focus planning, and quality review. We present AutoResearch-Video, a lightweight workflow that decomposes the problem into builders and connects them with an explicit judge agent.

## Introduction

Existing paper-to-video systems show that long-horizon generation is more useful when the system can reason over the paper structure instead of only generating a single video prompt. A practical research demo should produce intermediate artifacts that a human can inspect: slides, subtitles, cursor plans, and judge feedback. These artifacts also make the system easier to deploy on workflow engines such as FlowMesh.

## Method

The pipeline has five stages. First, the ingest stage extracts text from a paper or a local project directory. Second, the slide builder summarizes the source into a small number of presentation slides. Third, the subtitle builder turns slide notes into timed narration and visual-focus prompts. Fourth, the cursor builder grounds those prompts into screen coordinates. Finally, the judge agent scores coverage, length, and visual synchronization, then recommends which builder should be revised.

## Experiments

The first MVP focuses on inspectable artifacts rather than photorealistic video. It generates Markdown slides, SRT subtitles, cursor plans, a FlowMesh-style DAG specification, a judge feedback JSON file, and an HTML preview. This allows a user to run the complete loop locally or on a Vast GPU server without relying on private code hosting. When API keys are available, the heuristic slide and judge builders can be replaced by an OpenAI-compatible model call.

## Discussion

The main limitation is that the MVP does not call a real text-to-speech or talking-head model by default. This is intentional for early research iteration: the judge loop and workflow structure should be validated before spending GPU or paid API budget on rendering. The next step is to add optional TTS and talking-head providers, then compare human-made and system-generated videos using a stronger rubric.
