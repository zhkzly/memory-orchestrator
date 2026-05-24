---
name: memory-cleaner
description: Use when reviewing memory records for stale claims, contradictions, duplicate records, or reference problems.
---

# Memory Cleaner

Purpose:
- remove duplicates, mark contradictions, and downgrade stale claims

Flow:
1. inspect target scope
2. call `clean_memory`
3. preserve history when context matters

Do not:
- delete historical evidence without marking it outdated
