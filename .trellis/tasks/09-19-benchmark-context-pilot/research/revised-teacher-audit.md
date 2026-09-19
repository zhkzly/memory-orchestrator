# Revised Teacher 实际输入与输出审查

审查日期：2026-09-19。范围：同一条 train_001 学习经历的 continued / revised 三个 Teacher 节点；只读工件与当前消费者代码。未调用模型，未修改产品、提示词或评分器，未读取 probe 的答案、轨迹或评价。

结论：修复后真实工具结果更可用，引用也确实落在已提供正文；但输出仍主要是通用的逐记录核对流程，没有证明学到了正确业务公式。新出现的 `check_ref:null` 是过程依从检查缺材料，属于尚未厘清的“研究过程检查与发布验收混用”风险。它不是本轮未发布的唯一原因，也不应通过删检查来追求发布。

## 1. 审查工件与对照边界

- 原输入/输出：[continued/teacher-inputs](pilot/continued/teacher-inputs)，`01-extract_v1.json`、`02-diagnose_v1.json`、`03-propose_v1.json`。
- 修复后输入/输出：[revised/teacher-inputs](pilot/revised/teacher-inputs)，同名三个文件。
- 修复后实际 SDK 消息和返回：[call_0025.start.json](pilot/calls-continued/call_0025.start.json) 至 `call_0027.return.json`。
- 选择修复的同 fixture / 同预算离线对照另见 [evidence-selection-plan.md](evidence-selection-plan.md)；这里审查的是实际 Teacher 消费与产出，不能用离线可达性代替模型实际使用。

两个 extract 的 prompt digest 相同：`a6b5c38e95602384941327e8f04c74796de32751a36ca1e7908f0b0a768a9056`。但 diagnose / propose 已分别加入评价范围和检查义务语义，digest 不同。因此 extract 是相同提示词下的输入变化样本；后两节点不是只改变证据选择的单变量实验。全部只是各一次返回，亦存在模型采样波动。

## 2. 实际上下文没有缩短，但内容构成改善

字符数采用模型账本的实际 messages 序列化口径；tokens 是服务方实报，不由字符估算。三节点前后各一次调用，均无格式/语义修复。

| 节点 | continued 输入字符 | revised 输入字符 | continued 输入 / 输出 tokens | revised 输入 / 输出 tokens | continued / revised 秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| extract | 61,004 | 62,078 | 20,092 / 1,230 | 20,307 / 1,108 | 24.66 / 21.89 |
| diagnose | 62,307 | 60,340 | 19,621 / 1,189 | 19,682 / 1,222 | 23.74 / 36.18 |
| propose | 19,855 | 20,818 | 5,386 / 1,228 | 5,640 / 1,499 | 23.53 / 29.17 |

原 extract 包有 17 个事件，业务 GET 结果正文只有 1 个 order；revised 包有 20 个事件，包含 order×1、product×2、inventory×2、customer×1，以及提交成功回执。动作与结果的对应关系可读，模板从开头提供并有后续补读入口。

修复后的目录并非全部已读：目录从 11 个 action 改为 7 个 result、4 个 feedback 续段和 2 个 action 续段。两个 extract 都返回 `read_requests=[]`，所以不能把目录里的内容算作 Teacher 已利用的证据。

冗余仍存在：revised `readable_ref_catalog` 在 packet 内和单独输入中重复，`blocks` 普通 JSON 口径为 8,459 字符，原为 7,359。packet 本体略小，实际 extract messages 却增加 1,074 字符、215 输入 tokens。这个修复改善了可见内容和可回读性，未证明节省 tokens 或加速；本次时延差异也不能归因于上下文质量。

## 3. 类别覆盖不等于完整的业务证据链

以下内容确实出现在 revised packet 的工具结果正文中，而不是仅出现在请求参数或目录：

| 结果事件 | 已提供的源记录 | 对应正文引用 |
| --- | --- | --- |
| observation_17 | 订单 SO-70049，WH_WEST；SKU 为 NW-1053、NW-1029、NW-1009、NW-1034 | `ev:6bdff11dcb30baf772284eca:0:490` |
| observation_33 | 客户 CUST-2027，active、risk_flag=none | `ev:3efd0c83d79e22795acc2832:0:157` |
| observation_49 | 产品 NW-1011，active=true、safety_stock=14 | `ev:9f25ae8c176f0bebb8f207f0:0:204` |
| observation_67 | 产品 NW-1047，active=true、safety_stock=36 | `ev:7626a13a8d88110431e88794:0:204` |
| observation_83 | 库存 NW-1047 / WH_CENTRAL，on_hand=88、reserved=15、quarantined=28 | `ev:3385106477d553b8801efe08:0:145` |
| observation_99 | 库存 NW-1004 / WH_CENTRAL，on_hand=192、reserved=33、quarantined=0 | `ev:f42bf32e9ba676a02caad579:0:145` |
| observation_133 | `{"status":"ok","submitted":true}` | `ev:7773843ca829827cb2c543e8:0:32` |

客户能与该订单连接；NW-1047 产品与库存也能连接。但已提供的订单行不包含两个已提供产品中的任何一个，订单仓库也不是两个库存结果的仓库。因此，**当前 GET 正文中没有一条完整的“订单行需求 → 同 SKU 产品 → 同仓库库存”的连接**，不能据此独立重算某条订单的 shortage / low-stock 判断。

这也不能反过来证明 Actor 查错了仓库：这些是选择器从不同阶段取出的片段，属于不同实体很正常。若要具体归因，下一步应考虑在既定预算内围绕一条实体链补齐证据，或实际请求已有可读依赖；不是把所有日志加入上下文。本轮不继续修改选择器。

## 4. 引用可见性与语义支撑分别判断

对六份真实输出逐一调用当前 `validate_citations(value, corresponding_extract_packet)`，均通过。按递归去重的 `ev:` 引用计：

| 输出 | continued | revised | 判断 |
| --- | ---: | ---: | --- |
| extract | 13 | 4 | 全部引用已提供正文 |
| diagnose | 14 | 7 | 全部引用已提供正文 |
| propose | 4 | 4 | 全部引用已提供正文 |

这只证明引用未伪造、未偷用未读目录，不证明每个因果判断成立。revised 的实际引用消费如下：

- extract 的事实、经验依据和最终 Skill 都主要引用任务、模板、官方分项反馈、提交回执四类材料。
- diagnose 顶层 `evidence_refs` 加入一个 order 和两个 inventory 结果，但其具体 `hypotheses[*].supporting_refs` 仍主要是任务/模板/反馈，或回执/反馈。没有给出由订单数量和库存数值推出某条业务判断的论证。
- “submitted=true 与官方判失败同时存在”有直接证据，支持区分提交接受和结果正确。它不能证明 Actor 因误信回执而提前结束，也不能证明 Actor 没做过未被记录的检查。
- 模型保留了这些未知：不能定位具体错误记录、完整业务规则或计算错误；部分轨迹不能证明全部数据是否取齐、是否存在未观察到的复核。这些保留是合理的。
- `necessity.behavior_delta` 中 “Instead of proceeding from collected records directly to a submitted payload” 容易把未观察到的复核写成确定缺失。其余 `unknowns` 又承认可能有未记录复核。后续应使行为差异也保持条件性，避免由“没有看到”推出“没有执行”。

## 5. 产出更明确，但仍是待验证的流程假设

continued 给出逐字段证据表、先算异常集合再映射决策、最后重算汇总的流程。revised 仍沿此方向，增加实际仓库、`active` / `safety_stock` 等字段提示，以及回执不等于正确性的明确边界；最终 ADD 一个 8 步 Skill，`asset_edits=[]`。

这是比完全泛泛的“检查答案”更可执行的建议，但没有确定具体库存公式、优先级或决策映射，也未指出哪一条订单原本算错。single failed episode + coarse field-group feedback 不足以确认独一根因。`necessity.repeatable=true` 是 Teacher 对流程可复用性的判断，不是多任务重复证据；空库只能证明没有已有 Skill，不能单独证明新增该流程会有收益。

两个版本都 `completed`、`missing_evidence=[]`、不补读，同时在经验 `unknowns` 中承认数据不全。这在当前契约下允许形成有限的流程经验，不能报告为“已经完成业务错误归因”。

## 6. 新 null 检查：过程研究与发布验收的混合

continued diagnose/propose 只有绑定 `case:train_001` 的 target 和 `case:train_004` 的 regression。revised 两节点保留它们，又新增同一必需项：

```json
{
  "purpose": "distinguish",
  "check_ref": null,
  "behavior": "Verify that the proposed procedure is actually followed: template and local memo are read; live order, product, customer, inventory, warehouse, and quote data needed by the task are collected; per-record derivations precede summary recomputation; and submission status is not treated as correctness validation."
}
```

其 `required_evidence` 要求执行轨迹或结构化工作产物；当前可信目录没有这种过程检查。Teacher 在 `necessity.unknowns` 和提案理由中明确承认 null 阻止发布，所以此次不是没有理解 null 后果，也不是伪造了一个可通过的引用。

剩余语义风险在于检查义务的来源：

1. target/regression 的官方评分检验最终任务产物；“流程是否真的照做”可以支持机制研究、消费证据或归因辨别，但未必是任务正确性的必要条件。
2. 读取模板/调用 GET 可以从可见工具事件核对；“先做逐记录推导再重算 summary”和“没有把回执当正确性”未必有独立可观察事件。当前任务没有要求公开内部推理，不能把读取隐藏思维链作为解决办法。
3. 若项目确实承诺流程依从或过程级因果解释，就应事先提供适当的可观察产物与可信检查。若只承诺最终质量改善，则要在下一轮冻结协议前区分发布验收与研究性过程问题，不能由 Teacher 随意把全部研究问题转成发布必需项。

当前候选已经声明该义务，不能在看到结果后删除它、改绑不等价 case 或降低门槛。N09/N10 保留义务并集的机制应保持。本轮 diagnose/propose 也同时改了 scope/义务提示词，不能断言是证据选择修复导致新增 null。

## 7. 答案记忆与适用范围

完整检查两份 Skill，扫描 `SO-数字`、`NW-数字`、`CUST-数字`、`WH_*`、`TRAIN_EXPEDITE_*` 实例标识均无匹配；未发现把库存数值、运费值或固定答案记录写进 Skill，亦无附属资产。引用原证据本身不等于复制答案。

两者仍写入 `train_001` / `train_004` 的范围或检查绑定。这是本轮 benchmark 特定的验收边界，不是答案泄漏，但限制了便携性，不能据此声称跨任务泛化。

revised 的自然语言 `scope.exclusions` 排除 allocation-desk / train_004 风格规则，而 `task_family` 仍为 `northwind_erp`。当前 `context.py:166–175` 按 family / trigger 匹配，没有用自然语言 exclusions 实施确定性的过滤。因此“Skill 写了排除条款”不等于“宿主不会把它提供给回归任务”；若被提供，实际执行器仍需遵守其中边界。这是一条现有选择/使用责任，不在本次审查中扩实现。

## 8. 开发对照结果与本审查的证据上限

以下由根代理在本审查期间提供，未由本 worker 另读评价文件：修复后 target 为 base 5/17、candidate 5/17；regression 为 base 5/17、candidate 2/17；validation rejected，0 发布。null distinguish 不是唯一阻断，质量与回归条件也未通过。根共记录 51 次 SDK 调用、9 次任务执行、2 个独立任务；两侧 active 均为空库，故不再运行无新增比较意义的 probe，probe 保持未读。

本次可以确认“实际证据供给改善，模型仍产出有限流程假设，当前候选没有达到已冻结准入”。不能将前后 Actor 预算信息变化、提示词变化与采样波动下的分数差，称为记忆修复的因果提升或下降。也不能将引用合法、三个节点返回成功或可读类别增加写为已学会业务规则。

后续若另行授权，只需围绕两个具体问题设计新的冻结开发对照：提供能连成实体链的有限证据是否使提炼更具体；过程研究义务是否被不恰当地升级为发布必需项。本轮停止追加模型、修改和阈值调整，保留这次未发布结果。
