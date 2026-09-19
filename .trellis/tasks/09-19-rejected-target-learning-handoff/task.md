# 初始契约（冻结）
目标：把被拒target候选的真实评价执行转成下一轮可学习Episode，并由evolve返回其ID。
不变量1：仅candidate+target+rejected+keep_current且执行/评价完整可转换；base/regression/transfer/final/unknown不进入学习。
不变量2：原Validation/Selection/EvaluationReturn不可改；新Episode保留确切task/snapshot/events/score/失败门与来源。
不变量3：当前轮不自动再次调用模型或发布；调用方用新预算显式启动下一轮，回归/最终集合继续隔离。
不做：无限循环、提示词/补读改造、评分门修改、原生Agent接入、读取test001/gold、公开推送。
金标：510e84d真实train001 candidate EvaluationReturn、rejected Validation、keep_current Selection及132事件。

## 追加

- 用户确认整体流程应为“拒绝→保存新经历→下一轮重新提炼”；强调不要过度设计。
- 选择显式next_episode_ids交接，不在engine内部循环，避免新增model factory/调度器和验证集内原地重试。
