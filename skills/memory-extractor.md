# memory-extractor

Purpose:
- identify candidate memory items from current work

Flow:
1. read current session context
2. extract candidate facts, preferences, project rules, and scratchpad notes
3. call `capture_candidate`
4. propose a classification

Do not:
- promote tentative material
- invent durability
