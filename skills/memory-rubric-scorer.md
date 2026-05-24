# memory-rubric-scorer

Purpose:
- score a candidate memory system using evidence-backed proxy items

Flow:
1. read rubric definition
2. gather proxy-level evidence
3. call `evaluate_rubric`
4. refuse to score without evidence

Do not:
- give rubric scores from intuition alone
