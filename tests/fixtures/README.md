# Benchmark-derived fixtures

`gdpevo_context_train001.json` and `gdpevo_actor_first_request.json` derive from the actual local SDK execution of GDPevo task_group_007/train_001. Their origin metadata records the captured source and hashes. They include public benchmark inputs/data alongside this project's observed execution and model outputs; no final-test answers are embedded.

Upstream: [Prism-Shadow/GDPevo](https://github.com/Prism-Shadow/GDPevo), commit `56d60ae4ae5e067d1ec0ee1f850622e69f422179`. The upstream Apache-2.0 license is retained in [GDPEVO_LICENSE.txt](GDPEVO_LICENSE.txt). This attribution also applies to benchmark excerpts in the pilot evidence archive; it does not change this project's own distribution license.

`gdpevo_summary_repair_train001.json` copies the actual first summary input, returned draft, quote diagnostics and bound Feedback from the 2026-09-19 post-rewrite pilot at product commit `46bf5f0`. It reproduces the nested-JSON quote mismatch and the repair request that exceeded the original 8000-token input limit. Tests may construct a second response by copying literal source text; that response is explicitly scripted, not a new real model result or evidence of learned improvement. The same upstream attribution applies; no held-out task or gold answer is included.
