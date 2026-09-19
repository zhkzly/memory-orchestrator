# 定位候选Skill无增益与回归根因

## Goal

只读对比真实base/candidate执行轨迹、工具查询、产物与官方评分点，定位train001无提升和train004丢2分的首个因果差异，并给出简历安全结论。

## Requirements

- 对比两个任务的base/candidate工具查询、可见Skill上下文、最终artifact、调用成本和逐评分项。
- 找到train004丢失SP7的精确字段差异，并核对是否源于缺数据、错误规则或随机变化。
- 解释train001为什么Skill增加成本却没有救回任何评分组。
- 输出可用于简历和面试的真实结论，不把观察差异冒充因果证明。

## Acceptance Criteria

- [x] 直接失分字段、对应订单和评分组均可回查。
- [x] 候选是否收到Skill、是否缺ERP数据有实际消息/工具证据。
- [x] 明确支持的根因、替代解释和最小改进方向。
- [x] 给出一到两条不夸大的简历表述。

## Notes

- 只读诊断，PRD-only；报告保存到research。
