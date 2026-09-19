# 反馈、归因与准入：SkillSmith / GEPA 一手核查

状态：一手论文与固定版本源码核查完成；本轮只讨论，未修改产品、提示词、HTML或运行参数，未调用模型。范围是两篇论文与一条官方工程文档；源码事实与论文实验分别标注，不能由源码存在推出论文分数已复现。

结论：**目前优先缺的是能支持具体判断的学习证据，而非更复杂的演化搜索。** 两篇工作都将反馈组织与候选评分分开；SkillSmith公开实现和GEPA默认示例还会给Teacher训练答案。我们的反馈条件不能直接套用它们的效果。这个判断对“输入条件不同”有高置信度，对“补齐哪些材料后能改善GDPevo”仍是待实验的假设。

## 要回答的问题与当前证据边界

1. Teacher真正收到的是分数、gold、实际产物，还是已有环境诊断？
2. 失败如何产生具体候选；归因解释与采用候选所需证据如何分开？
3. 我们只有8组判定和不完整实体链时，哪些问题能确定，哪些只能保留假设？

【本地已知】当前讨论入口README确认：Teacher只读到有限片段，没有完整订单→同SKU→同仓库链；两个extract未主动补读。官方8组判定不能唯一确定每一条错误记录及其原因。将它们与generic Skill联系起来目前属于待区分的机制假设，不能把相关性写成已经证实的单一根因。

证据标签：**论文声明**＝论文原文的方法/实验；**源码静态核对**＝下面固定commit的实际字段/分支，未执行该仓库；**本地已知**＝本项目现有工件结论；**我们的推断**＝用于讨论的解释/选择，不冒充论文结论。

## 固定来源

- SkillSmith论文：[arXiv 2606.01314v1](https://arxiv.org/html/2606.01314v1)，2026-05-31。
- SkillSmith作者仓库：[yangforever17/SkillSmith](https://github.com/yangforever17/SkillSmith)，本次读取固定commit [2cbbd37c5293c3c06f1f5efc5709382639763cfa](https://github.com/yangforever17/SkillSmith/commit/2cbbd37c5293c3c06f1f5efc5709382639763cfa)，2026-06-05。当前发布实现不自动等同于论文实验版本。
- GEPA论文：[arXiv 2507.19457v2 PDF](https://arxiv.org/pdf/2507.19457v2)，2026-02-14；HTML版本本次返回过大错误，按PDF正文核查。
- GEPA官方仓库：[gepa-ai/gepa](https://github.com/gepa-ai/gepa)，本次固定commit [15ee314f9c7d34ec153b809d401f42f55c4dcd76](https://github.com/gepa-ai/gepa/commit/15ee314f9c7d34ec153b809d401f42f55c4dcd76)，2026-09-11；官方另列[论文实验artifact](https://github.com/gepa-ai/gepa-artifact)，不能把当前通用SDK默认值当成论文实验配置。

## 已确认的共同区别

**论文声明**：SkillSmith §3.1使用任务分数定位失败，并允许额外反馈函数μ_f提供编译错误、缺失文档、约束违反等诊断；没有此函数时才退回轨迹诊断。§3.3把候选的工具测试、集成测试和回归检查与反思步骤分开。[SkillSmith §3.1–3.3](https://arxiv.org/html/2606.01314v1#S3)

**论文声明**：GEPA §3/算法1输入明确包括评分μ和文字反馈μ_f；反思模型看当前prompt、轨迹、分数和反馈。候选先与父代在同一minibatch比较，再用D_pareto作选择；该选择集不是未触及的最终测试集。[GEPA §3，PDF第4–6页](https://arxiv.org/pdf/2507.19457v2#page=4)

**我们的推断**：可信验收只给8组对错时，语言模型可以提出诊断，但不能把其自由解释升级为隐藏业务规则的真值。最少需要把“观察到了什么”“哪一类判定失败”“可能原因”“用什么新证据区分原因”分开；即使新的候选改善了分数，也未必证明最初的原因解释唯一正确。

## 1. SkillSmith：Teacher实际得到的材料

以下为**源码静态核对**，不是根据论文名称推测。

| 位置 | 实际材料或行为 | 对我们的意义 |
| --- | --- | --- |
| `AgentResult` | task/question、标准answer、prediction、score、activated_skills/tools、trace、category同时存在 | 原始结果结构本身就比8组判定丰富 |
| `build_reflection_prompt` | 明示`ground_truth`、`prediction`、`score`、激活组件、`diagnostics`和压缩trace；另给已有组件、历史反例、capability假设/记忆、可选源文档 | gold、实际输出、上下文和解释不是同一类反馈 |
| `REFLECTION_SYSTEM` | 要求比较预测与答案、定位缺失信息/计算/格式，再输出root_cause、目标组件、approach、与被拒方案的差别、预期迁移 | 这是模型生成的修复计划，不能由字段名root_cause推断其已被证明 |

来源：[schemas.py L82–99](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/schemas.py#L82-L99)，[prompts.py L83–108、L137–190](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/prompts.py#L83-L190)。这些字段是训练反思载荷，不能据此批准把最终测试答案交给Actor或Teacher。

**源码静态核对**：它的`diagnose_failure`也不全是独立环境真值。代码依据timeout字符串、有无retrieved_evidence和低分生成`likely_gap`，并可能建议从抽取/表格解析修复。它是诊断启发式；“检索到非空文本”不等于文本充分支持答案。[prompts.py L387–428](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/prompts.py#L387-L428)

**源码静态核对**：不能把该仓库描述为“反思器完整读取所有长轨迹”。`compact_trace`保留reasoning/raw_response各末700字符，检索正文前900字符；非JSON轨迹只留末900字符。Actor记录的激活列表来自模型返回，缺失时用suggested列表，并非独立的实际消费证明。[prompts.py L365–384](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/prompts.py#L365-L384)，[agent.py L45–101](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/agent.py#L45-L101)

## 2. SkillSmith：从失败到候选，再到采用

**源码静态核对**：`run`先按阈值选失败，再按capability组织候选材料；反思器产出计划，独立的bundle proposer写Skill/Tool修改与工具测试。反思调用失败时可返回None，让后续提案器直接分析；不是“没有可靠归因就一定停止”。[loop.py L98–134、L374–482](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L98-L134)，[反思失败分支](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L426-L482)

**源码静态核对**：候选依次经过启用的生命周期/Skill格式/工具测试、原失败题集成比较、可用的capability holdout和validation均分门。holdout没有相应题目时直接跳过；各门可配置，默认开启。validation门比较平均分，不是逐题零退化保证。提案写出的工具测试也由同一生成流程提供，因此仍需独立任务评价。[loop.py L156–257](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L156-L257)，[holdout L520–560](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L520-L560)，[config.py L43–80](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/config.py#L43-L80)，[工具代码/测试由bundle提供](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/prompts.py#L24-L78)

**我们的推断**：可借鉴“症状与修复计划一起保存，失败也进入下一次检索”，但不能照搬“单一共享根因”的措辞来覆盖异质失败。先确保送入同一次归因的事件属于同一种决策和证据条件，才讨论可复用机制。候选有效与归因唯一正确是两个命题。

## 3. GEPA：反馈构造是适配器的职责

**源码静态核对**：`EvaluationBatch`分开保存outputs、scores、trajectories。`make_reflective_dataset`由适配器实现，要求把轨迹整理成组件级、高信号的JSON记录；引擎不会自动从任意日志恢复业务依赖。[adapter.py L145–216](https://github.com/gepa-ai/gepa/blob/15ee314f9c7d34ec153b809d401f42f55c4dcd76/src/gepa/core/adapter.py#L145-L216)

**源码静态核对**：默认单轮实现向求解模型发送system prompt与`data.input`；Evaluator另拿`data.answer`和生成输出。默认`ContainsAnswerEvaluator`通过答案子串判断得分，并把正确答案写入反馈（失败时也写入）。Teacher随后得到`Inputs / Generated Outputs / Feedback`；数值score单独交给引擎，默认反思记录没有独立score字段。[default_adapter.py L63–84、L117–173、L176–201](https://github.com/gepa-ai/gepa/blob/15ee314f9c7d34ec153b809d401f42f55c4dcd76/src/gepa/adapters/default_adapter/default_adapter.py#L63-L201)

这说明“使用GEPA”并不确定反馈条件。默认答案子串评分只是例子，不能替代我们的GDPevo官方结构评分；直接套默认Evaluator会同时改变评价和训练信息披露。

**论文声明**：论文实验的μ_f是任务定制的：HotpotQA/HoVer提供已找回与仍缺的相关文档；IFBench提供满足/失败的约束描述；PUPA提供质量与隐私泄漏的分数拆解。因此不能把GEPA概括成“总要给gold”，也不能概括成“任意一个总分已足够”。[GEPA Appendix E.1，PDF第23–25页](https://arxiv.org/pdf/2507.19457v2#page=23)

## 4. GEPA：反思提出更新，评价选择更新

**源码静态核对**：当前proposer先收集带轨迹的父代执行，交由adapter生成reflective dataset，再更新指定组件文本、在同一minibatch执行子代。没有轨迹、或没有新文本时跳过，不会把一段空泛反思当成已完成的候选。所有已评估提案交回engine选择。[reflective_mutation.py L425–506、L530–618](https://github.com/gepa-ai/gepa/blob/15ee314f9c7d34ec153b809d401f42f55c4dcd76/src/gepa/proposer/reflective_mutation/reflective_mutation.py#L425-L618)

**源码静态核对**：engine将acceptance/selection和全验证集评估分开；当前SDK还允许自定义selection策略选择探索性候选。这里的“accepted”主要指进入搜索池，不能直接翻译成我们系统的生产发布许可，也不是每个验证题都不下降。[engine.py L527–642](https://github.com/gepa-ai/gepa/blob/15ee314f9c7d34ec153b809d401f42f55c4dcd76/src/gepa/core/engine.py#L527-L642)

**我们的推断**：这里真正可迁移的是两个接口：一边保留供模型解释的细节，另一边保留不可由模型重写的比较目标。改得更具体的prompt不等于找到了真正原因；只有固定范围的新执行结果，才能支持采用该版本。

## 5. 负结果、证据疑点与不能外推的前提

| 来源与等级 | 明确边界 | 本项目不能据此声称什么 |
| --- | --- | --- |
| SkillSmith论文§5，论文声明 | 依赖骨干模型反思质量；共现少时生态估计噪声大 | 模型写出root_cause不等于得到可验证因果归因 |
| SkillSmith §3.2，论文声明＋我们的推断 | 相互作用估计来自既有日志中的共激活残差，论文说不增加消融成本；这是观察性估计 | 不能当成独立控制实验已证明某Skill导致收益 |
| SkillSmith Table 2，论文实验报告 | 无约束工具修改变体回归率8.9%，完整方法仍有2.1%回归 | 演化/测试门不提供无条件零退化保证 |
| GEPA Table 1，论文实验报告 | Qwen3-8B的IFBench：GEPA 38.61，GEPA+Merge 28.23；AIME上GEPA 32，GRPO 38 | 加merge不保证更好；不能把总体平均优势当所有任务优势 |
| GEPA §5.1，论文声明 | 部分代码搜索实验让train与Pareto集都等于待解决任务集合 | 测试时搜索的解题改善不等于未见任务泛化 |

来源：[SkillSmith §3.2](https://arxiv.org/html/2606.01314v1#S3.SS2)，[SkillSmith Table 2及§5](https://arxiv.org/html/2606.01314v1#S4.SS2)，[GEPA Table 1，PDF第8页](https://arxiv.org/pdf/2507.19457v2#page=8)，[GEPA §5.1，PDF第12页](https://arxiv.org/pdf/2507.19457v2#page=12)。论文中的实验数值未由本轮复现；这里只用于约束论断，不用于给本项目背书。

另有一项**文献内部待澄清**：SkillSmith Appendix D.1称OfficeQA最终测试205题、SealQA最终测试92题；Table 1却标246/111题，且197对应80.1%、55对应49.5%的比例按后者分母计算。不能同时把两处描述当成一套已核准的held-out结果。这里不猜测原因，只保留复现/引用时需要澄清的口径。[SkillSmith v1，Table 1与Appendix D.1](https://arxiv.org/html/2606.01314v1)

## 6. 对GDPevo问题的解释：两条信息缺口不能混成一条

**本地已知**：8组判定中，一组失败通常表示该组覆盖的多行至少有一处不匹配。它没有告诉Teacher具体哪一行、哪个字段、参考值是多少，也没有确定是读错实体、计算错、优先级错还是最终序列化错。反过来，如果某组通过且官方比较覆盖所有相应记录，其实际输出中的相应字段就是可用的成功证据；不能只盯失败。

**我们的推断**：目前应分开检验两条缺口：

1. **执行证据不连贯**：订单行、SKU、目标仓库、对应库存/商品/客户返回、最后输出字段没有连成同一个判断。即使业务数据已在原日志里，Teacher也未必在当次上下文中看见。
2. **验收诊断过粗**：即使上述链齐全，一组false仍可能对应多种规则/字段错误；没有额外可信信号，不能要求Teacher唯一推出隐藏规则。

将第一条补好不等于解决第二条；给第二条增加一段LLM解释也不能恢复第一条丢失的原始事实。generic Skill可能是这种双重欠定性的结果，也可能与提炼提示词过度强调“通用”有关；当前证据不足以只归因其中一个。

## 7. 讨论中的最小方向，不是新增实现计划

**我们的建议，尚未实验验证**：先围绕一项实际决策组织可读材料，再决定是否值得提出Skill。一个解释单元至少能指回：当前目标和规则来源、订单/行/SKU/仓库身份、实际查询与返回、最终输出字段、适用的官方判定、明确缺失的链接。没有必要先建复杂搜索树或让多个Teacher投票。

如果问题是已有正确GET返回未进入Teacher上下文，SkillSmith的工具演化也不能作为修改GDPevo业务环境或评分器的理由；应先定位证据传递层。其“工具能力不足”的动机只有在相应证据成立时才适用。

反馈分四层保存，避免混淆：

| 层 | 谁提供 | 可以支持的结论 |
| --- | --- | --- |
| 观察事实：实际调用、返回、产物值 | 运行环境/记录器 | 发生了什么；只能引用确实看见的内容 |
| 验收事实：判定、约束、必要时参考值 | 冻结的可信评分器/明确人工标签 | 哪个声明条件满足或不满足 |
| 解释假设：可能的机制与替代解释 | Teacher | 下一步应该调查或尝试什么 |
| 采用证据：固定条件下的目标/回归/成本结果 | 实际再执行与独立评价 | 在已测范围内是否采用该候选 |

若维持当前gold盲反馈，先允许保存有依据的操作经验与未决假设，不要逼出隐藏业务规则。若讨论增加训练期细粒度反馈，应由原评分器/参考数据产生实体与字段差异，而不是由LLM把总分改写成“权威原因”；这会改变训练反馈协议，必须单独标明，且与原反馈条件做可比讨论。最终probe的gold或失败不能回流改当前Skill。

还需区分三种结果：经验值得记下；候选值得试；版本值得采用。一次小样本成功可支持继续调查，不能同时认证归因、跨题有效和未来不退化。已有记忆的错误假设和反例也应保留其证据与适用范围，不让反思文本仅因存进库就升级为事实。

## 8. 一条工程比较

Anthropic的官方上下文工程文档建议压缩先保证重要信息召回，再减少冗余，并明确指出最少必要上下文不一定很短。这是工程建议，不是“实体链取证已被论文证明”的实验结论。对我们更有用的解释是：先确认当前分析单元具备作判断所需的信息，再缩短它；不能把短、分时覆盖或固定字符截断直接当作信息充分的替代。[Effective context engineering for AI agents，Compaction部分](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

## 本轮未声称完成的验证

- 未运行SkillSmith或GEPA，没有复现其收益或比较随机性。
- 未证明补全实体链一定提高GDPevo分数，也未证明只提高反馈粒度就足够。
- 未核实到能直接量化“本项目八组反馈＋不完整链”损失的论文对照实验；这个数量不能从其他任务的平均提升换算。
- 未改任何运行代码、提示词或HTML；上述建议是讨论选项，尚未变成新的实现约束。
