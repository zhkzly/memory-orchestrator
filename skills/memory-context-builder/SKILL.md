---
name: memory-context-builder
description: Use when starting or resuming work that needs a scoped memory context pack.
---

# Memory Context Builder

Purpose:
- assemble the minimum context pack for the next run

Flow:
1. read task scope
2. pull relevant user preferences
3. pull relevant project context
4. pull relevant evidence notes
5. call `build_context_pack`

Do not:
- flood the prompt with unrelated memory
