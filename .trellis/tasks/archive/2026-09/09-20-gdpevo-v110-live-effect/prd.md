# v1.10 GDPevo 真实效果实验

## Goal

固定v1.10代码、归档train001学习证据和GDPevo task_group_007，运行一次真实Teacher与条件触发的base-candidate对照，记录质量、回归与完整调用成本。

## Requirements

- 使用当前 v1.10.0 产品代码和固定 GDPevo task_group_007 commit。
- 复用已归档 train001 学习 Episode；本轮 usage 只统计新的 Teacher、Actor 与 evaluator 调用。
- 真实 Teacher 若补读、弃权、NOOP 或生成候选，均按原样保存。
- 候选存在时沿普通 `evolve` 路径比较 train001 target 与 train004 regression，不绕过验证/选择/发布。
- 输出一份自包含实验报告及简历可写结论。

## Acceptance Criteria

- [x] 新实验目录不可覆盖，plan 在第一次模型调用前写入。
- [x] ledger、Store、Teacher 输入和最终 result 均可复核。
- [x] 报告明确新旧成本边界、provider失败与单次实验限制。
- [x] Git 产品 commit 固定为 1ad555f，实验未修改产品代码。

## Notes

- 本任务只执行实验并写报告；发现产品问题时停止并另开实现任务。
