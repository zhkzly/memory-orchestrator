# v1.4 数据交接索引（非已实现 API）

产品代码仍暂停。本页只连接源契约，字段、模型模板和 Schema 均在 docs/blueprint/project-contract.json；不维护另一套 Python 默认签名。

| 环节 | 当前交接 | 缺失/责任规则 |
| --- | --- | --- |
| 明确事实记忆 | UserProjectMemory | N01 明确保存/纠正，N02 按范围读取；学习器不能写 |
| 已有经历 | EpisodeRecord | 允许未知 task/source snapshot/context/feedback；保留已知角色/父子/目标身份 |
| 召回后使用 | ContextManifest → EpisodeRecord.context_ref | 只在确实有上下文时回传，校验项目；提供不等于采用 |
| 请求采样 | TaskSpec + ContextManifest + 显式策略 → N03 execute 函数 | 系统保存 RunGroupPlan 和全部结果；函数报告环境观测缺口 |
| 反馈 | Feedback / TaskAssessment | 有则接收或调用 evaluate 获取；迟到反馈追加到原对象，无则 unknown |
| 提取 | EpisodeIndex + 可用反馈 → EvidencePacket → ExtractionResult | 目录与已读正文分开；有限补读；不要求 RunBundle/GroupReceipt 才能导入 |
| 归因 | 经验/反例/可用来源信息 + 当前库 → ChangeIntent | 原因是假设；非 Skill 问题可 NOOP；源版本未知不伪造 |
| 修改 | ChangeIntent + 同一 base → PatchCandidate[] | ADD/PATCH/RETIRE/NOOP，依赖/冲突/项目/附属资产一起处理 |
| 比较 | EvaluationPlan.requests → 执行/评价函数 → EvaluationResult[] | 次数/案例/门槛预先固定；全请求有记录，实际语义由函数提供 |
| 判定与选择 | 实际结果 → ValidationRecord + SelectionRecord | 必需门完整且唯一；所选项必须通过、符合冻结规则 |
| 发布/回退 | 精确候选 + 验证 + 选择 → ReleaseRecord | 同项目，匹配 base/generation/资产/协议，回退关联已发布历史 |

## 原草稿变更说明

撤销将 validate_candidate(..., repeats=1, max_parallel=1) 当作已确认默认 API 的表述。保留可重复/可并行的比较能力，具体次数由协议给出。

不把 transfer 可选/不下降或旧版严格提升规定为万能默认；按承诺范围和本次协议选择，并保留回归与未知处理。

评价函数可分别执行和评分，也可组合实现；均须返回与请求版本/案例匹配的证据。只返回一个任意分数不足以宣称真实改进。

无需通用回调注册器或事件框架；公开方法命名在产品实施时按这条已闭合数据流确定。已有 tests 是草稿，不是当前规范。
