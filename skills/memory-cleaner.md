# memory-cleaner

Purpose:
- remove duplicates, mark contradictions, and downgrade stale claims

Flow:
1. inspect target scope
2. call `clean_memory`
3. preserve history when context matters

Do not:
- delete historical evidence without marking it outdated
