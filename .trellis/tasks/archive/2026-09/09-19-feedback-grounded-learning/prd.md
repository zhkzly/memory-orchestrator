# 反馈闭环与 Skill 适用性优化

## Goal

保留现有分层轨迹处理，修复失败反馈与执行证据脱节、泛化经验证据不足及 Skill 排除条件不生效的问题。

## Requirements

- 保留现有三层轨迹输入、action/result 调用组、局部摘要、原文引用、依赖回找和累计模型预算；本任务只补足上层证据闭环。
- 将被拒 target 转为下一轮 Episode 时，若原 EvaluationResult 绑定了可验证 TaskAssessment，则将其 criterion feedback 原样作为适配反馈的来源材料，并保留缺失情形。
- 对任务族或跨任务族经验，要求证据同时覆盖任务要求、至少一个完整 action/result 调用、被评价的最终产物和绑定反馈；实例经验保持可用。
- 当上述证据不足时，模型必须在剩余预算内请求目录中的原文，或输出实例级经验/弃权；不得仅凭失败组名生成通用 checklist。
- 新增 Skill 使用简短、机器可执行的 `require_any` / `exclude_any` 任务文本短语；检索时排除条件优先于正向匹配。
- 所有规则保持 benchmark 无关；GDPevo 只作为真实失败金标和回归夹具。

## Acceptance Criteria

- [x] 真实拒绝样本回流后，适配 Feedback 含原 criterion 的身份、结果、原始 reason 与来源引用；篡改绑定会被拒绝。
- [x] 最终 artifact 事件与 Feedback 通过相同 artifact digest 的资源关系关联，且不改变原始事件正文。
- [x] 真实坏提取中“task + group score”形式的 task-family 经验被语义检查拒绝，并返回缺少的证据角色。
- [x] 完整任务/action/result/artifact/feedback 链可通过；instance 级局部事实不受新增门影响。
- [x] ADD 缺少机器 scope selector 时在模型修复预算内被拒；合法 selector 可持久化。
- [x] 从真实候选 Skill 派生的 selector 在 train_001 被选中，在 train_004 被 `scope_exclusion` 排除。
- [x] 相关定向测试、完整 Python 回归、mutation、contract check/render/verify 均通过。

## Notes

- 当前总纲版本为 1.9.0；涉及 N02/N04/N06/N07/N08 与 Q10/Q12/Q14/Q19/Q28。
- “证据闭环”证明信息被提供并绑定，不自动证明自然语言归因正确或 Skill 会提升效果。
