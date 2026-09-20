# v1.10 GDPevo Benchmark

## Goal

在不修改 v1.10 产品、prompt、评分器和准入规则的前提下，先确认本地 provider 能完成真实等长结构化请求，再运行固定 GDPevo development 学习与候选对照；只有 development 候选通过原发布门，才进入重复运行和冻结 test 评测。

## Requirements

- 固定产品 commit `1ad555f583e1d14a7b58372ae43850d94b70cf67`、contract v1.10.0、GDPevo commit `56d60ae4ae5e067d1ec0ee1f850622e69f422179`、task_group_007 和模型 `gpt-5.6-terra`。
- readiness 复用上一轮失败的真实 `diagnose_v1` 完整 payload；要求 transport 正常返回且正文为 JSON object。失败则停止，不把 provider 故障计作算法分数。
- development 复用归档 train001 Episode 与空基线 Store；Teacher 允许提取、弃权、NOOP 或生成候选，均原样留档。
- 仅在候选存在时，由 GDPevo 官方 scorer 比较 train001 target 和 train004 regression；不人工补分、不读取 test 输入。
- development 候选只有通过冻结的 Validation/Selection/Release 路径后，才规划相同配置的重复运行；只有重复证据完成后才运行冻结 test001 base/memory 对照。
- 记录全部请求、失败、unknown usage、Token、版本状态与没有发生的阶段；不从 Token 推断货币成本。
- 本任务只产生实验材料和报告；发现产品缺陷时另开任务，不在本轮边跑边修。

## Acceptance Criteria

- [x] readiness 的输入 hash、响应状态、耗时、usage 与 JSON 解析结果可复核。
- [x] readiness 的停止分支已在冻结 plan 中声明；本轮实际通过，未触发 provider-blocked。
- [x] readiness 通过后，development plan 在调用前冻结，且 ledger、Teacher 输入、Store 与结果均落盘。
- [x] `needs_evidence`、NOOP 与 0 Candidate 按真实分支报告，未执行的 Actor/test 阶段没有伪造成 0 分。
- [x] 未通过 development 前，runner 未打开或执行 `test_001` 的任务文件；报告不把 development 当未见泛化。
- [x] 已生成简历 v3，但只陈述历史任务分数与本轮真实调用量、弃权和限制。

## Notes

- 用户已在本轮明确要求开始 benchmark；任务进入执行不再等待二次确认。
