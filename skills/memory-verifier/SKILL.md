---
name: memory-verifier
description: Use when a memory candidate needs evidence review before it can become durable memory.
---

# Memory Verifier

Purpose:
- check whether a candidate should be stored durably

Flow:
1. inspect candidate item
2. gather or request evidence
3. call `verify_candidate`
4. reject weak or speculative items

Do not:
- auto-promote weak claims
- collapse fact and inference
