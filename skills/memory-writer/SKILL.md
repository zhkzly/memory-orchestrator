---
name: memory-writer
description: Use when a verified memory item should be promoted into the correct durable Markdown layer.
---

# Memory Writer

Purpose:
- write verified items to the correct markdown target

Flow:
1. accept verified item
2. call `promote_item`
3. write only to the intended layer

Do not:
- rewrite history silently
- move unverified items into durable layers
