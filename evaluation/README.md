# Memory Evaluation Artifacts

Use these files to keep rubric decomposition, evidence collection, and scoring separate.

## Files

- `rubric.md`: produced by the rubric decomposer
- `evidence.json`: produced by the evidence collector
- `score-report.json`: produced by the scorer

## Process

1. Write the rubric first.
2. Collect evidence into `evidence.json`.
3. Score only from the rubric plus evidence.

## Rule

Never edit rubric, evidence, and score in the same pass.
Keep the steps separate so the review trail stays auditable.
