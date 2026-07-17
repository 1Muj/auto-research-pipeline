# FlowMesh AutoResearch Video Demo

This demo project shows how an AutoResearch workflow can turn a local repository into a presentation video plan. The project is intentionally small so that it can run on a laptop, a Vast instance, or a FlowMesh worker.

## Goal

The goal is to make project-to-video generation inspectable. Instead of asking a model to create a final video directly, the system produces intermediate artifacts: a project summary, slides, narration subtitles, cursor coordinates, a talker plan, judge feedback, and an HTML preview.

## Architecture

The project uses a builder pipeline inspired by recent paper-to-video systems:

- Ingest builder reads repository files and identifies the project goal.
- Slide builder creates a compact explanation for a professor or lab meeting.
- Subtitle builder turns slide notes into timed narration.
- Cursor builder maps visual focus prompts to screen coordinates.
- Talker builder prepares API inputs for TTS and talking-head services.
- Judge agent scores the result and gives revision instructions.

## Why it matters

For research workflows, the value is not only the final video. The intermediate artifacts make it easier to debug the system, compare builders, and deploy individual nodes on FlowMesh. This also matches the auto-research idea: run a workflow, collect metrics, let a judge critique it, and iterate.
