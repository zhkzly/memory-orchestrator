# 验证记录

## 身份与冻结

- 产品 commit：`1ad555f583e1d14a7b58372ae43850d94b70cf67`
- contract：v1.10.0 / `d39a35d4...f2ce8`
- GDPevo：`56d60ae4...22954`
- 两个 plan 的 task、prompt digest、模型、预算一致；ledger 分开且均从0开始。
- `git diff -- src tests examples/memory_evolution examples/gdpevo_pilot` 为空；实验未改产品、prompt、schema、Actor或evaluator。

## 物理结果

- study：6 requests；5有usage，已知47,590 Token；1条instance Experience；diagnose InternalServerError；0 Candidate。
- study-retry：5 requests；3有usage，已知23,486 Token；summary APIStatusError；extract 120.1s timeout；0 Candidate。
- 合计：11 requests；8有usage；3 usage未知；已知71,076 Token；0 Actor comparison；0 Release；active generation 0。

## 完整性检查

- 242份JSON均可解析。
- 所有物理stage仅为 summarize/extract/diagnose；calls ledger中不存在`test_001`。
- 两个Store均无candidate ID、无committed release，active snapshot保持空基线。
- 原始 start/return、Teacher inputs/results、Store、plan和最终result均保留。
- `git diff --check`与Trellis task validate均exit 0。

## 解释边界

首轮真实extract将旧式泛化经验降为instance，属于v1.10安全行为证据。provider失败阻止Diagnosis/Proposal完成，因此不存在新的任务分数或性能收益。失败调用Token未知，不填0；不因一次成功extract推断稳定遵从率。
