# GDPevo v1.10 效果证据说明

日期：2026-09-20

代码分支：`codex/vault-controller-maintenance`

核心版本：Memory Orchestrator contract v1.10.0

## 一句话结论

当前证据证明了**演化闭环能够发现并阻止有害 Skill 发布**，但尚未证明记忆系统能稳定提升后续任务分数。简历应写“构建演化与回归防护机制，并在真实小批实验中拦截退化候选”，不能写“显著提升 Agent 性能”。

## 2026-09-20 v1.10 真实 Teacher 重放

在本机模型服务恢复后，使用相同归档 train_001 Episode、固定 v1.10 prompt/schema 和 `gpt-5.6-terra` 执行了两次独立 study；没有重跑旧 Actor，也未读取 test split。

首轮 extract 成功生成 1 条 `instance` Experience。模型明确指出，当前只看到模板/备忘录读取、部分评分与不完整覆盖，缺少完整 ERP action/result、最终输出和完整反馈，不能识别具体失败原因，也不能升级为 task-family procedure。这与旧版在相同证据上生成通用 task-family checklist 形成直接对照。

首轮随后在 diagnosis 遇到 `InternalServerError`；独立重试在摘要和 extract 分别遇到 APIStatusError 与 120 秒超时。两轮合计：

| 指标 | 结果 |
|---|---:|
| 物理模型请求 | 11 |
| 有 usage 返回 | 8 |
| usage 未知的失败调用 | 3 |
| 已知 Token | 71,076 |
| Experience | 1 条 instance（首轮） |
| Candidate / Actor 对照 / Release | 0 / 0 / 0 |

因此 v1.10 新增了真实的安全性证据：证据不足时，Teacher 会把经验限制在实例级，而非继续生成跨任务 Skill。provider 中断使本轮无法测得新的 target/regression 分数，不能据此声称性能提升。完整原始 ledger、Store 与输出保存在对应 Trellis 实验任务中。

## 实验问题

从一次失败任务及其长轨迹、工具调用和外部评分中提炼经验，生成 Skill 后，是否能：

1. 改善目标任务；
2. 不损害相关回归任务；
3. 以可接受的模型调用成本完成更新。

## 已执行设置

| 项目 | 设置 |
|---|---|
| 数据 | GDPevo task group 007 的 `train_001` 与 `train_004` |
| 目标任务 | `train_001`，Northwind expedite/dispatch-control |
| 回归任务 | `train_004`，allocation/transfer workflow |
| 比较 | base snapshot 与 candidate snapshot，各任务各执行一次 |
| 评分 | GDPevo 官方可执行 evaluator；8 个字段组，总权重 17 |
| 模型 | `gpt-5.6-terra`，OpenAI-compatible SDK |
| 发布规则 | 目标有正增益，且逐题回归不下降；不满足则保留旧版本 |

这是一轮开发期小批实验，不是正式 benchmark 总榜，也没有固定随机 seed 或多次重复执行。

## 实际结果

| 任务 | Base | Candidate | 差值 | 结论 |
|---|---:|---:|---:|---|
| train_001 target | 5/17 | 5/17 | 0 | 没有目标增益 |
| train_004 regression | 12/17 | 10/17 | -2 | 出现回归 |

- Selection：`keep_current`
- Candidate：拒绝发布
- Active library：保持原版本
- 新增真实 SDK 调用：27 次
- 新增 Token：213,599；价格未知

候选在 train_001 的总 Token 从 29,405 增至 44,613（+15,208，约 +51.7%），但分数未提高。train_004 的候选 Token 从 33,084 增至 36,339（+3,255，约 +9.8%），同时分数下降 2/17。

## 回归的直接表现

train_004 的候选获得了完整三仓库存数据，问题不是少查数据。新增失分来自订单级 rollup：

- `SO-70036`：base=`has_backorder`，candidate=`mixed_actions`；
- `SO-70050`：base=`needs_transfer`，candidate=`mixed_actions`。

这两处变化使 SP7 整组由通过变为失败，直接损失 2 分。公开 memo/template 没有定义多 action 的 rollup 优先级，因此不能把 benchmark gold 反推出通用规则。

## 根因与 v1.10 修复

原 Teacher 输出的 task-family 经验只引用了任务要求和失败评分组，同时明确承认完整 ERP 请求/响应及最终 artifact 不可见，却仍生成“逐字段检查”的通用 checklist。该 Skill 的自然语言 exclusions 已写明不适用于 allocation/transfer，但旧选择器只使用宽泛 `task_family=northwind_erp`，所以仍将其注入 train_004。

v1.10 增加四项确定性约束：

1. rejected target 回流时保留原 criterion feedback，不只保留总分；
2. 用 artifact digest 绑定被评分输出和 Feedback；
3. task-family/cross-family 经验必须引用任务、完整 action/result、同版本输出和外部反馈，否则补读、降级或弃权；
4. 新 Skill 必须声明机器 `require_any/exclude_any`，排除条件先于排名执行。

对**原始坏提取结果**做确定性重放时，v1.10 会以 `reusable_evidence_incomplete` 拒绝；对其诊断结果会以 `necessity_invalid` 拒绝。为真实候选补充机器边界后，train_001 能命中，train_004 会因 `allocation desk`/`transfer` 被排除。

## 当前可以宣称的效果

### 已有证据

- 演化链路实际运行到经验提取、Skill 候选、base/candidate 对照、Selection 和拒绝发布。
- 冻结评分与回归门成功阻止无增益且回归的 candidate 进入 active library。
- v1.10 对真实旧坏草稿执行确定性拒绝，并使声明的任务排除边界成为实际选择逻辑。
- v1.10 真实 Teacher 重放将相同不完整证据降为 instance 经验；两次运行在 provider 失败下保持 0 Candidate、0 发布并保留未知 usage。
- 当前 Python 核心 383/383 回归通过；v1.10 关键保护完成 22 次 mutation 检查。

### 尚无证据

- 没有测得目标任务或未见任务的正向分数提升；
- 没有多 seed／多次重复，不能证明 Skill 是回归的唯一原因；
- 没有完成 Codex/Claude Code 原生轨迹适配；
- 没有证明维护 Token 成本低于长期收益。

## 简历安全表述

> 构建 Agent 执行轨迹→证据提取→经验/Skill 候选→冻结对照→版本发布/回退的记忆演化框架；在 GDPevo 2 任务、4 次版本对照中识别目标 0 增益与回归 12/17→10/17，并通过外部评分门拒绝有害候选。进一步基于真实失败链增加 artifact-feedback 绑定和 Skill 机器适用边界，完成 383 项回归与 22 次故障注入检查。

## 得到正向收益数字还需什么

下一轮应在稳定 provider 窗口中固定 v1.10 代码和预算，在同一开发任务流上重新执行：

1. 用真实 Teacher 处理 exact rejected-target Episode，记录补读/弃权/候选内容和全部成本；
2. 若生成候选，至少对 target 与 regression 各重复 3 次，保留全部失败运行；
3. candidate 选择只使用开发/验证任务；冻结后再测未参与更新的同族任务；
4. 报告逐题均值、波动、回归数、成功率与 Teacher+Actor+Evaluator 总 Token；
5. 只有 target/held-out 有正增益且无超阈值回归时，才在简历中写“提升”。

如果重放选择 abstain 或没有候选，这仍是有效结果：说明证据门阻止了一次缺少可执行行为差异的更新，但不能换算为任务性能提升。
