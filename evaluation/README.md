# Memory Evaluation Artifacts

Use these files to keep rubric decomposition, evidence collection, and scoring separate.

## Files

- `rubric.md`: produced by the rubric decomposer
- `evidence.json`: produced by the evidence collector
- `score-report.json`: produced by the scorer
- `usability-rubric.json`: runnable proxy rubric for daily usability and memory-harness readiness
- `usability-evidence.json`: evidence set for the usability rubric
- `structure-rubric.json`: runnable proxy rubric for memory-architecture and layering quality
- `structure-evidence.json`: evidence set for the structure rubric

## Process

1. Write the rubric first.
2. Collect evidence into `evidence.json`.
3. Score only from the rubric plus evidence.

## Rule

Never edit rubric, evidence, and score in the same pass.
Keep the steps separate so the review trail stays auditable.

## Usability Score

Run the usability rubric directly:

```bash
node dist/cli.js score --rubric evaluation/usability-rubric.json --evidence evaluation/usability-evidence.json --out usability-score-report.json
```

The full harness also runs this score and requires an overall score of at least 4.5.

Run the structure rubric directly:

```bash
node dist/cli.js score --rubric evaluation/structure-rubric.json --evidence evaluation/structure-evidence.json --out structure-score-report.json
```
