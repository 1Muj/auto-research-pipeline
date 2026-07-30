# Background Comparison: Automated Research Agents

| System | Focus | Mechanism | Mapping in auto-research | Lite implementation |
|---|---|---|---|---|
| AI Scientist-v2 | End-to-end automated ML discovery | Hypothesis, experiment execution, analysis, figures, paper writing, reviewer loop | YAML experiment spec, Vast execution, threshold feedback, reviewer brief | review + visualize commands over real run artifacts |
| Google AI Co-Scientist | Scientist-in-the-loop hypothesis generation | Multi-agent generation, reflection, ranking, evolution of hypotheses | Governance fields plus critic recommendations from metrics | review command checks hypothesis/metrics alignment and next experiments |
| OpenAI PaperBench | Evaluate research-paper replication by agents | Hierarchical rubrics and objective grading of replication subtasks | success_threshold and threshold_detail as a compact rubric | feedback JSON and visualization expose pass/fail evidence |
| Hugging Face ML Intern | Open-source ML engineer agent for HF ecosystem | Agent loop, tool router, docs/papers/datasets access, local or sandbox tools, traces | Local CLI, experiment commands, Vast push, artifacts, review output | ml-intern-lite demo tracks planning, tool trace, artifact and shipping metrics |

## References

- AI Scientist-v2: https://arxiv.org/abs/2504.08066
- Google AI Co-Scientist: https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/
- PaperBench: https://arxiv.org/abs/2504.01848
- Hugging Face ML Intern: https://github.com/huggingface/ml-intern
