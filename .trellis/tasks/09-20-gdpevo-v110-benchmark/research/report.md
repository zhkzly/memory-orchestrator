# GDPevo v1.10 Benchmark 报告

日期：2026-09-20

## 结论

本轮 benchmark 的 provider 和 Teacher 链路已经完整跑通，但没有产生可评分 Candidate，因此没有新的任务提分数字。结果不是 provider 失败：readiness 与 development 共 **7/7** 次模型请求正常返回，合计 **81,656 Token**。系统从归档 train001 失败 Episode 中生成 1 条 `instance` pitfall，Diagnosis 认为修改必要性仍为 `needs_evidence`，最终 `abstained`，保持 **0 Candidate / 0 Actor 对照 / 0 Release / generation 0**。

这轮定位出了更具体的下一瓶颈：原轨迹有 138 个事件，系统扫描了全部元数据，但当前有界选择只让 Teacher 实际分析 7 个事件。进入摘要的内容主要是模板、备忘录开头和最终输出片段；用于解释失败的 product/inventory/shipping 查询链没有进入可见证据。因此此次弃权是合理的证据门行为，同时说明当前轨迹分段选择不足以支持该类长工具轨迹的归因。

## 冻结设置

| 项目 | 值 |
|---|---|
| 产品 | commit `1ad555f583e1d14a7b58372ae43850d94b70cf67`；当前 `src/` 与 GDPevo runner 与其一致 |
| Contract | v1.10.0，`d39a35d4…f2ce8` |
| GDPevo | commit `56d60ae4…22954`，task_group_007 |
| 模型 | `gpt-5.6-terra`，localhost:8317，timeout 120 秒 |
| 学习材料 | 归档 train001 Episode；旧 Actor 执行不计入本轮调用 |
| Development | train001 target；train004 regression 仅在 Candidate 存在时执行 |
| Frozen test | test001；本轮未打开其 prompt/payload/notes/output/evaluator，也未执行 probe |

设置阶段查看过 group manifest 与文件名，因此这里不使用含糊的“完全没有接触任何 test 元数据”表述。真正冻结的是 test001 的任务正文、payload、参考输出、评分器和执行结果。

## Readiness

readiness 原样复用了上一轮失败的 `diagnose_v1` payload：51,692 个序列化字符，payload SHA-256 为 `59aed5fa…f1f`。

| 指标 | 结果 |
|---|---:|
| 请求 | 1/1 返回 |
| 耗时 | 23.46 秒 |
| JSON object | 是 |
| Prompt / Completion / Total Token | 16,640 / 1,081 / 17,721 |
| Unknown usage | 0 |

因此上一轮即时 500/超时不是当前必现故障，development 得以启动。readiness 只证明 transport 能承载代表性长请求，不计作记忆效果。

## Development 结果

| 阶段 | 物理调用 | 状态 | Token |
|---|---:|---|---:|
| 局部摘要 | 4 | 3 个摘要完成，1 次调用用于修复 | 30,956 |
| Experience extract | 1 | 完成 | 15,290 |
| Diagnosis | 1 | 完成，`needs_evidence` | 17,689 |
| 合计 | 6/6 返回 | `abstained` | 63,935 |

本轮没有重新执行旧 Actor。作为学习来源的归档 train001 Episode 得分为 **5/17（0.2941）**，仅用于说明输入失败轨迹；它不是本轮新跑的 base 分数。

提取出的 Experience：

> Do not treat correct order coverage as sufficient for ERP fulfillment classification

它被限制为 `reuse_level=instance`。模型只陈述评分器中可见的共现：订单集合与客户异常匹配，但库存状态、短缺 SKU、最终决策等不匹配；同时明确承认完整 ERP 查询、完整提交和评分细节不可见。

Diagnosis 选择 `route=skill_patch`，认为空 Skill 库存在潜在能力缺口，但 `necessity.verdict=needs_evidence`。它没有把假设强行转成 ADD，因此候选槽为 `noop`。这正是 v1.10 证据门的预期语义。

## 为什么没有 Candidate

本轮的实际轨迹处理数据为：

| 指标 | 数量 |
|---|---:|
| 原始事件 | 138 |
| 元数据扫描 | 138 |
| 投影事件 | 11 |
| Teacher 实际分析事件 | 7 |
| 省略事件 | 126 |
| 计划片段 | 4 |
| 完成片段 | 3 |
| 因摘要调用预算未分析 | 1 |

第四个片段原本包含最早的两个 `/orders/...` action/result，但 4 次 summary 物理调用中有 1 次被输出修复消耗，所以该片段没有执行。更关键的是，即使第四片段执行，当前排序仍按普通工具调用的原始先后截断。

对同一 Episode 做无模型、只读的覆盖审计后，完整轨迹需要 36 个片段：

- inventory 查询第一次出现在第 **22** 段；
- shipping quote 第一次出现在第 **32** 段；
- submit 位于第 **36** 段。

当前 `max_segments=4` 只会覆盖模板/备忘录、最终 artifact 和最早订单查询。失败反馈恰好指向 inventory/decision 字段，但这些相关调用没有被反馈引导到前四段，且未选片段不会进入可补读目录，Teacher 无法主动请求它们。

所以根因首先是 **framework 的上下文选择策略**，其次才是预算；不是简单再改 Teacher prompt。把 Token 上限稍微调大也不够，至少要改变片段优先级或让反馈相关的 action/result 进入可补读目录，并为修复调用预留摘要额度。

## 三道门的最终状态

| 门 | 状态 | 原因 |
|---|---|---|
| Provider readiness | 通过 | 1/1 长请求返回合法 JSON |
| Development candidate | 未通过 | Experience 为 instance；Diagnosis=`needs_evidence`；0 Candidate |
| 重复评价 | 未启动 | 没有已发布 development Candidate |
| Frozen test | 未启动 | 上一道门未通过 |

这不是把缺失分数填成 0。train001/train004 的新 base-candidate 请求数量就是 0，任务性能差值为 **未测量**。

## 可以与不可以写进简历

主简历仍应优先使用已有的强结果：历史候选 train001 **5/17→5/17**、train004 **12/17→10/17**，被冻结回归门拒绝。

本轮适合在项目面试中补充：

> 在固定 GDPevo 138 事件失败轨迹上完成 7/7 次真实模型调用与 81,656 Token 全链路审计；系统将缺证经验限制为 instance 并保持 0 Candidate/0 发布，同时通过分段覆盖审计定位 inventory 证据排在第 22 段的长轨迹选择瓶颈。

不能写“benchmark 提升”“未见任务提分”或“Skill 已生成并有效”。

## 下一步

下一步应单独修复轨迹选择，而非在本实验上调结果：让失败 criterion/实体与 action/result 片段建立通用相关性排序或可补读入口，并在 summary stage 为一次合法修复预留容量。修复后用相同 train001/train004、同一评分器和发布门重新开新实验；只有 Candidate 通过 development 与重复运行，才解封 test001。

## 核对

- 机器一致性断言通过：readiness 1 次 + development 6 次 = 7 次，合计 81,656 Token；0 Candidate、comparison/release 为 null、generation 0。
- `tests.test_gdpevo_context` 与 `tests.test_memory_trajectory_learning` 共 21/21 通过。
- Trellis context validate、blueprint verify、JSON 解析与 `git diff --check` 通过。
- `src/`、`tests/`、`examples/gdpevo_pilot/` 相对冻结产品 commit 无差异。
