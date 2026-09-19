# 候选拒绝后未补读：因果诊断

## 结论

这里有两个不同的缺口：

1. **候选生成前的补读没有发生。** LLM在extract阶段合法选择了“现有证据足以形成一条有限pitfall”，而不是`needs_more_evidence`。当时预算未耗尽，但目录没有提供它真正需要的完整业务轨迹，输出契约还要求“经验”和“补读”二选一。
2. **候选验证拒绝后没有新一轮学习。** 当前`evolve()`是一次显式循环：learn → compare → select/publish。`keep_current`后直接返回。四次对照的原始事件保存在`evaluation_returns`，没有成为Episode/Run，评价反馈绑定request_id而不是episode_id，因此不能直接交给下一次`learn()`。

所以：**一次演化事务已经完整结束；“从被拒候选的执行与反馈继续演化”的多轮闭环尚未实现。**

## 实际时序

### 1. 局部整理丢失了最接近业务因果的片段

计划处理4个局部段，summary阶段也只允许4次调用。前三段成功；第四段含两个真实`business_get`调用及订单返回：

- `/orders/SO-70000`及492字符结果；
- `/orders/SO-70007`及299字符结果。

模型第四段引用了完整299字符结果，超过`max_quote_chars=240`。已有4次summary调用全部消耗，修复将成为第5次，因此被stage call limit拒绝。前三段继续进入extract，但第四段业务材料没有形成摘要。

这不是总预算耗尽，也不是旧JSON转义问题。这里的配置关系是`max_segments=4`、summary `max_calls=4`、`max_format_repairs=1`：所有段都首次调用时，最后一段没有任何纠错余量。

### 2. extract可见的补读目录不能满足它声明的缺证

真实05-extract显示：

- `max_read_requests=3`；
- `remaining_evidence_expansions=1`；
- extract阶段还允许第二次调用。

所以它没有因为补读预算耗尽而停止。

但9个`readable_ref_catalog`只包括：

- answer template的`0:600`范围（原记录4540字节）；
- memo的`0:600`范围（原记录1785字节）；
- prompt的action/result；
- 最终artifact的`0:600`范围（原记录3103字节）；
- 若干feedback范围。

目录中**没有任何ERP business_get结果**。对template/memo/artifact的请求也只能读取目录声明的固定范围，不能获得模型所说的“complete”内容。目录条目只给raw_ref/range/structure/call_id，不直接给关联tool/path；部分可通过当前fragments和relations反查，但第四段的业务调用不在这个目录里。

模型输出因此是自洽的：

```text
missing_evidence = 完整template、memo、ERP查询和提交JSON
read_requests = []
reason = 当前要求和可见评分足以提炼一条有界的task-family pitfall，不能作更具体归因
```

它仍可请求600字节范围以补一点template/memo/artifact内容，但这些范围不能提供它声明需要的完整业务因果链。没有证据证明一次补读足以改变结论。

### 3. ExtractionDraft契约使“先保留经验，再继续读”不合法

执行schema探针得到：

| 组合 | schema结果 |
| --- | --- |
| `completed` + experience + read_request | REJECTED |
| `needs_more_evidence` + experience + read_request | REJECTED |
| `needs_more_evidence` + 空experience + read_request | ACCEPTED |

因此模型只能二选一：

- 放弃本轮经验，返回`needs_more_evidence`，宿主才会执行`expand_packet`；
- 返回`completed`经验，`learning.py`立即跳出补读循环。

提示词写的是“需要补读则requests；无法形成有用经验则abstained”。它没有规定“只能形成通用核对清单时必须优先补读”。模型明确认为有限pitfall已算有用经验，所以选择completed。`missing_evidence`只是说明字段；框架没有把“completed且missing_evidence非空”视为冲突。

这是模型选择和契约偏置共同产生的结果，不是引用校验器替模型做了决定。

## 为什么验证拒绝后没有继续学习

验证在经验、归因、候选生成之后发生。`engine.evolve()`读取SelectionRecord；decision不是selected时，设置`status=not_selected`并直接返回。没有从ValidationRecord返回N06的边，也不会在同一轮自动创建另一个模型预算。

这种停止有合理目的：target/regression是冻结的候选选择材料。用同一验证结果立即修改候选再重试，会把验证集逐步变成训练集，破坏预先固定的准入证据。

但当前实现也没有为**显式的下一轮适配**准备完整材料：

- Store只有原始学习经历：1 Episode、1 Run；
- 四次对照分别保存为`evaluation_returns`，每次含124–212个事件；
- 对应feedback的`subject_ref`是evaluation request_id；
- `learn()`输入要求Episode ID，`feedback_for()`只返回绑定episode_id的反馈。

因此调用方即使开启第二个learning cycle，也不能直接把这些拒绝轨迹交给现有`learn()`。还缺一个明确的、受split权限约束的“评价执行 → 新学习Episode”转换过程。

## 第一因果偏差及所有者

按时间顺序，最早的可行动偏差在候选生成之前：

1. summary计划没有给最后一段留纠错调用；
2. 失败/未接受段中的business_get材料没有作为可辨认、可读取的catalog候选交给extract；
3. extract契约允许单失败样本上的task-family通用清单提前completed，并强制经验与补读互斥。

这些属于N06的framework输入/调用契约；LLM负责在实际可见选项中决定是否读取和写什么经验。

验证后的停止属于另一层：N09结果没有进入一个新的、明确授权的N06周期。这是多轮生命周期未闭合，不该用增加同轮重试次数偷偷补上。

## 最小下一步及可证伪标准

建议分两项实施，先做A，后做B，不能混成一个无限自动循环。

### A. 在生成候选前完成证据充分性测试

- summary规划必须为修复留出可声明的调用余量；未成功整理的段仍把真实action/result locator优先交给extract。
- catalog为result提供确定性的关联action信息（至少tool/path/总字节范围），让模型能判断哪个ref补什么；不能只给不可辨认的call_id。
- extract提示/契约明确：如果只能形成通用核对清单，而目录中有可能使结论更具体的原始材料，先返回`needs_more_evidence`。下一次调用再生成经验；不要求宿主自动写经验。

判定探针：使用相同train001输入，第一次extract必须请求至少一个与具体业务结果对应的ref；expanded输入后要么形成含具体行为差异且有原文支撑的经验，要么abstain。只改提示却目录仍无business证据，不算完成。

### B. 将拒绝结果放入显式的新学习周期

- 不在原validation中原地重试。
- 仅把预先授权为adaptation/target的评价执行转换成新的Episode/Run，保留task revision、snapshot、events、artifact和feedback；regression/final保持只读评价材料。
- 新cycle有新的ID、预算和版本；可以同时输入base/candidate target轨迹做比较归因。上一轮validation仍不可改写。

判定探针：candidate被拒后，authorized target执行可产生可学习Episode及绑定反馈；regression请求不能进入learning source。第二轮`learn()`的source_episode_ids包含新target Episode且不包含regression/final。没有这个物理数据流，就不能宣称“系统会从被拒候选中继续演化”。

## 状态修正

- 已完成：单次学习、候选生成、冻结对照、拒绝与不发布。
- 未完成：从候选拒绝轨迹开始的下一轮自进化闭环。
- 本次诊断没有修改产品或提示词，没有调用模型或benchmark，也没有读取test001/gold。
