# SkillSmith：实现深读与可核对样例

日期：2026-09-18。论文由一个独立 subagent 精读，本文聚焦主 agent 的源码与作者示例核查。固定源码提交：`2cbbd37c5293c3c06f1f5efc5709382639763cfa`。

## 本轮需要纠正的认识

- 之前只看主循环和门控不足以评价整篇工作；还必须追踪联合修改对象、实际运行方式、轨迹粒度、生态分数和具体样例。
- 公开 `agent.py` 有 direct 与 OpenCode CLI 两条路径。不能仅凭存在自有 Agent 类就说它无法使用现成 Agent；本次尚未验证 Codex/Claude 原生接入。
- 作者的 `tally` 示例同时产生 Skill、Python helper 和测试；`officeqa` 示例则明确记录了工具过拟合与改用 skill-first 的结果。因此不能把论文理解为每次失败都应生成工具。

## 已执行的有限检查

从固定提交复制作者 `tally_transform` 的 tool.py、test_tool.py 和入口模块到临时分析目录，检查代码后执行原有 unittest。6 个测试通过；额外调用 ant/key 得到 ant:35、key:41，与仓库提供的两个验证样例一致。

这只验证发布工具的确定性行为。本次没有执行 LLM、自我演化过程或论文主基准，不能据此声称复现了 0→1 的 Agent 改善。

命令均退出 0；执行环境 stderr 出现 `Failed to create stream fd: Operation not permitted`，使用 `python3 -S -B` 后仍出现，但 unittest 的 6 项断言及两个直接输出检查通过。该告警原样保留，不把它解释为论文或模型执行问题。

## 1. 输入是一份有反馈的执行记录

[`schemas.py:90`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/schemas.py#L90) 的 AgentResult 保存 task_id、question、answer、prediction、score、activated_skills、activated_tools、trace、category。

[`agent.py:45`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/agent.py#L45) 先检索 Skill/工具、构造输入，执行 direct 或 OpenCode，解析结果，再由 scorer 比较预期与实际。这里 answer 是外部评价依据，不是模型内部推理。

实现边界：trace 保存模型给出的 reasoning、截短的 raw_response、检索建议及文档证据；activated 列表可能来自模型输出，也可能回退到检索建议。因此这些字段不自动证明工具实际被执行，也不是完整、无损的原生逐步轨迹。

## 2. 反思与实施分两次模型调用

[`loop.py:374`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L374) 收集失败，检索旧失败模式，更新生态统计，生成当轮允许的工具操作，先调用反思，再把计划交给 bundle proposer。

[`prompts.py:83`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/prompts.py#L83) 的反思输出包含 root_cause、action、target_component、approach、differs_from_discarded、expected_transfer。它要先说清缺什么、修哪个现有组件、为什么能迁移，而不是马上写代码。

后续 proposer 同时看到已有组件、失败记录及评分、来源材料、反模式、生态信号和允许操作，产出一个 BundlePlan。固定实现会向训练失败分析提供 ground_truth；迁移到自然 coding 会话时，必须用可信验收/review 代替，不能假定永远有标准答案。

## 3. 学到的是一套配合的外部资产

[`schemas.py:34`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/schemas.py#L34) 的 BundlePlan 同时包含 skill_ops 与 tool_ops，并记录理由、预计效果、目标与留出任务 ID。

- Skill 操作有 create/edit/retire，内容说明何时及如何工作。
- Tool 操作有 create/wrap/edit/compose/split/retire，包含代码、测试和来源工具。
- 一个候选把操作说明与被调用代码一起更新，避免新工具上线却无人会调用，或 Skill 指向旧接口。

这是论文主张的逻辑原子 bundle；公开文件操作并不因此自动具有跨进程/跨文件的事务保证。部署系统还需独立确认切换与回退语义。

## 4. 一个具体作者样例：tally

作者的 [`tally` 结果页](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/examples/tally/RESULTS.md) 说明其任务是一个人为定义的字符串变换。初始 Agent 按任务约束返回 UNKNOWN；之后候选同时增加 `named-transform` Skill 与 `tally_transform` Python 工具。

Skill 指明触发条件、参数提取、调用哪个工具和回答形式；工具实现字母位置求和；测试覆盖大小写、非字母、空串等。发布的训练样例为六个词，验证样例为两个不同词。作者报告验证由 0/2 到 2/2；本轮仅核对发布函数与测试，没有重跑模型产生这些资产的过程。

它清楚展示“说明怎样调用”与“提供可调用能力”的分工，但人为隐藏规则、极小验证集和初始 UNKNOWN 约束意味着不能把这组 toy 结果当成真实业务的一般增益。

## 5. 验证与状态选择是实际执行路径

[`validator.py`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/validator.py#L31) 实际启动 unittest 并检查工具操作约束。其后 [`loop.py:164`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L164) 在配置启用时检查目标失败上的改善、能力留出集，以及验证分数回归；通过后才更新候选集合。

[`store.py:58`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/store.py#L58) 为候选复制父状态，保存 bundle 与 manifest。Pareto 比较使用各任务得分，不只保留平均分最高者；最终排序还考虑能力信息。当前主循环选 `best_state()`，不应将它直接描述成论文的概率父代采样。

回归门比较平均分，不保证每道旧题绝不回归。作者 OfficeQA 示例里验证均值提高，但一题从 0.25 降至 0.10，正好说明要同时报告逐题变化。

## 6. 生态信号怎样计算

[`ecology.py:46`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/ecology.py#L46) 先减去任务类别历史均分，形成残差；再比较某 Skill 被标记激活/未激活时的残差均值，使用 EMA 平滑。两个 Skill 的协同量，是共同激活均值相对两种单独激活均值中较好者的差。

Lotka–Volterra 更新结合这些量、现有 utility 和容量参数，得到有上下界的动态值。正协同可提高相容组件的排序，负协同提示冲突。它复用已有日志，便宜，但不是随机干预，类别均值也不能完全消除任务选择、版本和能力混淆。

配置事实：[`config.py:101`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/config.py#L101) 的 retrieval_weight 与 synergy_weight 默认都是 0；[`agent.py:411`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/agent.py#L411) 此时只按文本相关性排 Skill。复现实验必须固定真实配置，不能因存在生态代码就说默认运行使用了论文所有机制。

## 7. 作者公开的负例：不应强迫每次生成工具

[`examples/officeqa/RESULTS.md`](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/examples/officeqa/RESULTS.md) 承认一个早期工具硬编码了不存在的表题，真实数据上返回 None；表面得分来自 LLM 的补救，不能归功于工具。作者随后禁用新工具生成，改为行为 Skill；两题验证均值由 0.125 到 0.275。

这不是论文主基准，也不是本轮模型重现。价值在于它提供了真实的作者反例：规则清晰、适合确定性计算时生成工具有意义；文档理解与不稳定抽取可能更适合改指导。源码 `allow_tool_creation=false` 会约束生成路线，并禁止把不存在的工具用 edit/wrap 伪装创建。

## 8. 对现成 Coding Agent 接入的含义

公开代码已支持 OpenCode CLI，证明方法设计不要求只能自建一个 ReAct Agent。将同样的外部资产思想用于 Codex/Claude，可以让原生 Agent 读取 Skill，并通过既有 shell/工具入口调用项目脚本；这属于拟议适配，本轮没有验证兼容性或效果。

需要保留的是：真实调用记录、外部验收、失败归因、Skill与脚本的成套候选、分级验证及版本证据。需要按场景决定的是：是否确实需要生成工具、生态统计是否有足够数据、是否需要多分支选择。不能先把所有模块搬进当前记忆项目。

## 9. 本轮判断

SkillSmith 应成为完整系统设计的重要参考；此前仅凭主循环较重、使用自有 Agent 类就把它放次位，依据不足。其核心价值是区分操作知识与工具能力缺口，并将二者作为可验证的联合更新。

论文效果的可信范围、消融支持和文内口径问题，见 [独立论文精读](skillsmith-paper-independent-20260918.md)。源码、仓库小例子和论文主表是三类证据，不混作一组结果。

## 10. 论文与公开实现的对账边界

| 对象 | 论文描述 | 此次公开快照 |
| --- | --- | --- |
| 父代选择 | 从逐实例优势的候选集合按权重采样 | `run()` 直接调用 `best_state()` |
| 工具动作 | Wrap/Edit/Compose/Split/Retire 五类 | schemas 另有显式 create，共六类 |
| 生态影响检索 | 相关性、utility、synergy、cost 四项 | 文本相关性加可选 utility/synergy；默认两个生态权重为0，所查排序未含成本项 |
| 激活记录 | 任务执行中的激活集合 | 列表可能由模型报告或回退到检索建议，需要额外消费证据 |
| 使用现成执行器 | 方法不约束为特定模型API | 已有 direct/OpenCode 分支，尚无本轮确认的 Codex/Claude 专用接入 |

这些差异说明照默认仓库运行不能自动等同论文设置，不直接否定论文方法或效果。若要复现，需要从论文的超参数、数据和配置反向核对真实执行路径。

独立读者指出的主要数字口径问题也经本文算术核对：主表 OfficeQA 的197对应246分母为80.1%，不是附录205测试题；SealQA的55对应111分母为49.5%，不是附录92测试题。必须在作者澄清前保留分母歧义，不能据此直接指控泄漏，也不能把主表数字当已确认的严格留出集效果。
