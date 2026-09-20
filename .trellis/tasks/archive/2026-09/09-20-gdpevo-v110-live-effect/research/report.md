# v1.10 GDPevo 真实 Teacher 实验

## 结论

本轮得到了一项真实的**安全性行为证据**，没有得到新的任务分数提升：首轮 `gpt-5.6-terra` 将旧实验中会升级为 task-family Skill 的通用 checklist 降为 `instance` 经验，并明确表示缺少完整 ERP action/result、最终输出与完整反馈时不能归因或泛化。随后模型服务在 diagnosis 阶段返回错误；独立重试又在摘要与提取阶段出现 APIStatusError/120 秒超时。因此没有产生 Candidate，也没有触发 Actor base-candidate 对照。

## 冻结设置

- 产品 commit：`1ad555f583e1d14a7b58372ae43850d94b70cf67`
- contract：v1.10.0，SHA-256 `d39a35d4...f2ce8`
- GDPevo：`56d60ae4...22954`，task_group_007
- 学习证据：归档 train_001 Episode；旧 Actor 执行不计作本轮调用
- 开发回归：train_004；仅在 Candidate 存在时执行
- 模型：`gpt-5.6-terra`，timeout 120 秒，SDK 不自动重试
- test split：未读取、未运行

两个 study 使用相同代码、数据、prompt digest、预算和门槛，分别保留独立 Store 与调用 ledger。第二次运行只用于确认首轮即时 500 是否偶发；出现新的 provider 错误后按计划停止。

## 首轮结果

### 成功阶段

- 4 次 summary 物理调用；两份合法局部摘要进入提取。
- 1 次 extract 调用成功。
- 生成 1 条 Experience，`reuse_level=instance`。

经验标题为：

> Reading the template and memo alone does not establish a complete dispatch-control solution

模型明确记录：

- 可见证据只覆盖模板/备忘录读取与部分评分；
- 没有完整 ERP 查询、最终 JSON 与 submission；
- 不能断言哪个未观察动作缺失或造成失败；
- 没有完整 action/result 与 evaluated output 时，不升级为 task-family procedure。

这与旧回放形成直接对照：旧版在相同证据上生成了 task-family checklist；v1.10 真实 Teacher 选择 instance 级记忆。

### 终止原因

`diagnose_v1` 的第一次请求在 0.76 秒返回 `InternalServerError`。Framework 保存了 Experience、错误、预算预留和未知 usage；没有生成 Diagnosis/Candidate。

## 独立重试

- 3 次摘要调用成功；第 4 次摘要返回 APIStatusError。
- Framework 保留已完成摘要并继续尝试 extract。
- extract 请求在 120.1 秒超时，usage 未知。
- 未产生 Experience、Diagnosis 或 Candidate。

同一 provider 在两个独立 study 的不同阶段失败，因此停止继续重试；没有修改 prompt、输入上限、模型、任务或发布门来追求候选。

## 调用与成本

| 运行 | 请求数 | 有 usage 返回 | usage 未知 | 已知 Token |
|---|---:|---:|---:|---:|
| study | 6 | 5 | 1 | 47,590 |
| study-retry | 5 | 3 | 2 | 23,486 |
| 合计 | 11 | 8 | 3 | 71,076 |

已知合计包含 prompt 64,745、completion 6,331。3 次失败调用的实际 Token 未知，不能填 0；provider 未返回价格，货币成本未知。

## 版本结果

- Candidate：0
- Actor comparison：0
- Release：0
- Active generation：0
- Active snapshot：保持空基线 `bea91769...82fa`

未运行 Actor 对照不是节省后补出的选择：协议规定只有 Candidate 存在才计划比较。无候选时不能制造 base/candidate 分数。

## 这轮证明了什么

1. 新 prompt 与 host gate 在真实 Teacher 调用中改变了经验粒度：同类不完整证据产生 instance pitfall，而非 task-family Skill。
2. 失败调用、未知 usage、部分摘要和已保存 Experience 都被保留，没有被包装成成功或零成本。
3. 系统没有因为简历需要数字而放宽证据门或发布一个无法验证的 Skill。

## 没有证明什么

1. 没有 Candidate，因此没有新的 target/regression 分数和正向性能增益。
2. 两次 provider 失败说明当前服务稳定性不足以完成本轮端到端效果测量；不能归因于 Memory Orchestrator 的学习逻辑。
3. 单次成功 extraction 不能证明所有模型调用都会稳定降级为 instance。

## 简历可用结论

可以写：

> 在真实长轨迹 Teacher 重放中，将缺少完整 action/result 与 evaluated output 的经验限制为实例级记忆，阻止其升级为跨任务 Skill；两次冻结运行共记录 11 次模型请求和 71,076 个已知 Token，provider 中断时保持 0 Candidate/0 发布并保留未知成本。

不建议把这条替换掉此前更强的回归门结果。主简历仍优先写“识别并拒绝 12/17→10/17 的回归候选”；本轮适合作为面试追问时证明 v1.10 修复真实改变了 Teacher 行为。

## 下一步

在得到稳定 provider 窗口后重新开新 study；只有完成 Diagnosis/Proposal 并生成 Candidate，才执行 train001/train004 对照。若仍为 instance/NOOP/abstain，应将其报告为安全更新率，而不是任务提升。任何 prompt/预算/模型调整必须另立实验版本，不能覆盖本轮失败。
