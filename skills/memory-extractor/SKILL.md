---
name: memory-extractor
description: Use when a session may contain durable memory candidates that should be captured before verification or promotion.
---

# Memory Extractor

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
