# 设计依据

## 已有能力

当前 `build_trajectory_plan` 已按目标/修订分段、保持调用组、按角色和重要性选择，并由 `_learning_packet` 做直提或有预算的局部整理；摘要引用必须是原文子串，片段仍可按目录补读。因此本任务不再增加“先分层”实现。

## 真实失败链

- `ffb60696...json` 的 `extract_v1` 输出把经验标为 `reuse_level=task_family`，但 supporting refs 只覆盖任务要求和 evaluator scoring-point 文本；其 unknowns 明确说完整 memo/template、ERP 请求响应和 artifact 都未提供。
- 随后的 `diagnose_v1` 仍把“逐字段 evidence worksheet + consistency pass”判为 `necessity.verdict=proceed`，形成通用 checklist。
- 真实候选 Skill 的 scope 已写“不要用于 allocation/transfer”，但 `context.py` 当前只按 task_family/triggers 正向词项打分，并明确把 prose conditions 当 advisory；因此 train_004 仍收到 3877 字符 Skill。
- train_004 的直接回归为 order rollup 两处变化，公开材料没有给出优先级；这类材料不足应保持 unknown，而不是倒推规则。

## 采用的最小机制

保留现有分层器；补足三条已经存在但未闭合的边：原 criterion feedback -> adaptation feedback，artifact digest -> feedback，supporting refs -> 可复用经验角色门。自然语言 scope 不再承担机器判定，新增短语 selector 仅用于 ADD Skill 的执行边界。
