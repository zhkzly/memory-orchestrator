# Benchmark 检查

- [x] 产品、contract、数据、模型、prompt digest、评分器、预算和任务身份均在首次调用前固定。
- [x] readiness 使用上一轮真实完整 payload；返回、耗时和 usage 全部保存。
- [x] readiness 通过；未把上一轮基础设施故障或本轮结果归因混写。
- [x] development 使用独立 Store/ledger，未覆盖上一轮实验或旧 Actor 证据。
- [x] Teacher 的 instance、`needs_evidence`、NOOP 和 abstain 均保留，未挑选好结果。
- [x] Candidate 为 0，因此 train001/train004 新评分请求为 0；未补分或伪造对照。
- [x] development 未发布，重复评价与 frozen test 均未启动。
- [x] 报告逐层区分 provider readiness、学习行为、development 效果与 frozen-test 泛化。
- [x] 7/7 调用 usage 已知；provider 无报价，货币成本保持 unknown。
- [x] 本任务未修改 `src/`、`tests/`、prompt、schema、evaluator 或 benchmark 数据。
