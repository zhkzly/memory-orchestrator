# 拒绝候选进入下一轮学习

## Goal

为被拒绝的target候选评价建立受控Episode回边，保持regression/final隔离，并由evolve返回下一轮episode IDs而不自动无限重试。

## Requirements

- 被拒绝的候选只把`target`臂的candidate执行交给下一轮；regression/transfer/final及base保持评价专用。
- 转换必须由ValidationRecord+SelectionRecord+EvaluationPlan/Result/Return共同授权，不能仅凭request ID或调用方声明。
- 新Episode及Feedback是原评价的不可变投影，包含来源、candidate snapshot、任务修订、实际事件/artifact、score/outcome和失败门；不接触私有criteria/gold。
- `evolve()`不自动消费新预算，只在`not_selected`结果中返回`next_episode_ids`。调用方显式传入新的StructuredModel再次调用。
- 重复恢复得到相同记录，不重新执行评价或模型。

- [x] checklist 1–10全部可执行验证。
- [x] 使用真实GDPevo拒绝记录派生fixture证明正路径；边界变体由该fixture修改单一条件。
- [x] 新Episode可通过现有lineage/evidence/learn入口，旧selection-only直接导入仍拒绝。
- [x] 完整Python回归、总纲自检与官方mutation通过；不将scripted teacher当真实收益。

## Notes

- 这是公共来源/生命周期契约变更，需design与总纲版本更新。
