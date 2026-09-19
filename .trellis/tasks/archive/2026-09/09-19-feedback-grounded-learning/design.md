# 设计

## 根因

现有底层已按角色、目标版本和调用组分层，并对长轨迹做有预算的局部整理。真实 pilot 的失败发生在其上层：`extract_v1` 生成的 task-family pitfall 只引用任务要求和评分组，没有引用最终 artifact 或任何完整 action/result；`diagnose_v1` 明知完整执行缺失，仍把通用核对清单判为可复用行为差异。随后 Skill 的自然语言 `scope.exclusions` 仅作为说明，选择器按宽泛 `task_family=northwind_erp` 将其注入明确属于 allocation/transfer 的 train_004。

## 数据流

```text
既有分层轨迹与局部摘要（保持）
  -> 回流 Feedback 保留原 criterion 细项
  -> artifact 与 Feedback 用 digest 资源边绑定
  -> extract/diagnose 检查闭合证据角色
       缺失 -> read_requests / instance / abstain
       完整 -> 允许进入候选生成
  -> ADD Skill 必须声明机器 scope selector
  -> selector exclude 优先，随后才做现有排名/依赖/预算
```

## 契约选择

- 不新增证据链 schema：复用 `supporting_refs`、packet `relations.calls`、`resource_relations` 和现有状态分支，由宿主计算角色覆盖，减少模型机械输出。
- `SkillContent.scope` 新增可选 `retrieval`：`require_any` 至少一个短语，`exclude_any` 可为空；旧快照无该字段时保持 legacy 选择，新 ADD 必须提供。
- 短语只做大小写无关的任务文本子串匹配；它是显式检索条件，不宣称完整自然语言蕴含。exclude 命中优先并记录匹配短语。
- task-family/cross-family 的可复用经验及 `necessity.verdict=proceed` 需覆盖 task、完整 call pair、environment artifact result、feedback；instance 经验不受此门限制。

## 反馈投影

`capture_rejected_target_episodes` 继续只回流 rejected candidate 的 target 轨迹。若 EvaluationResult 有 TaskAssessment，则先用现有 assessment 校验路径重验，再将 criterion feedback 的公开字段和原始 `reason` 放入新的 adaptation Feedback reason；缺记录时明确 `original_criterion_feedback=[]`，不伪造。最终 artifact 事件和反馈索引各带同一 digest 的 artifact resource。

## 风险边界

- 评分器若只给组级布尔值，系统仍不能定位具体订单或隐藏规则；新增门的目标是阻止无证据泛化，并不制造字段归因。
- 旧 Skill 没有机器 selector 时继续 legacy 行为；只有新 ADD 强制，避免破坏历史快照读取。
- 本任务不重排原轨迹片段，也不新增 Teacher 调用。
