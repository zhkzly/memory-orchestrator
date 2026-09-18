# SkillEvo / SkillTriage：真实执行轨迹怎样变成可用反馈

核查日期：2026-09-18。范围：反馈原料、错误定位、责任归属、修改约束及日常 coding agent 的迁移条件。仅阅读公开材料并写本文；未运行论文模型、未修改产品、未上传本地分析。

**结论（高置信）：两篇工作都说明“日志本身不够”。SkillEvo 用人工已处理工单提供正确知识，再通过模拟对话暴露差异；SkillTriage 用同任务的成功或更便宜运行提供参照，再分析 Skill 引起的轨迹差异。前者的优势是把反馈收窄成可编辑事实，后者的优势是要求归因解释具体执行差异。两者均未证明：给一条没有参考答案、没有对照运行的任意日常日志，就能可靠区分模型、Skill、工具、环境和评测器问题并自动修好。** [SkillEvo §3](https://arxiv.org/html/2608.13120v1#S3)，[SkillTriage §III、§VI](https://arxiv.org/html/2608.11888v1#S3)

本文标记：**论文事实**指原文明确描述；**实验级**指作者报告的实验，未经本次复跑；**推断级**指从公开证据得出的边界判断；**工程建议**指本文提出的日常应用方式，不能冒充作者实现。

## 1. 材料核查与可见边界

| 项目 | SkillEvo | SkillTriage |
| --- | --- | --- |
| 原文身份 | Qianxi Yan 等，*SkillEvo: Self-Renewing Evolution Gradients from Multi-Turn Interaction Feedback*，arXiv:2608.13120v1，2026-08-13 | Gen Dong 等，*Agent Skills Can Be Harmful: An Empirical Study of Skill-Induced Failures in LLM Agents*，arXiv:2608.11888v1，2026-08-12；SkillTriage 是其中的归因工具 |
| 本次读到 | 正文、附录 A–G；含核心 prompt、伪代码、具体工单全过程、模型及工具权限 | 正文 §I–IX、Figure 4、表格和案例；没有公开在文中的完整归因 prompt 或 JSON schema |
| 数据边界 | 2,000 个人工升级工单，9 个 Skill、98 个 reference 文件；工单按时间分成 3/4 开发、1/4 留出评估；作者明确不能公开生产工单 | 从 SkillsBench / SWE-Skills-Bench 收集受控运行，315 个功能失败候选和 350 个效率候选，经人工筛选形成 125 + 182 = 307 个已确认案例 |
| 官方代码边界 | 论文和 arXiv abstract 未提供作者实现链接；双引擎检索未找到可确认属于本篇的公开仓库 | 同样未找到可确认属于作者的官方实现仓库；同名 `skill-triage` 仓库不能据名称视作论文实现 |
| 因而不能声称 | 已逐行核验生产 FSM、归因代码、全部提示词或真实工单 | 已核验 DS1–DS5 的具体计算代码、证据 gate 的准确逻辑、完整输入输出 schema |

来源：[SkillEvo 附录 A](https://arxiv.org/html/2608.13120v1#A1)、[附录 B 开头](https://arxiv.org/html/2608.13120v1#A2)、[复现声明](https://arxiv.org/html/2608.13120v1#Sx2)；[SkillTriage §III-D](https://arxiv.org/html/2608.11888v1#S3.SS4)、[§VI-A](https://arxiv.org/html/2608.11888v1#S6.SS1)。两篇 arXiv 页面均标注 CC BY 4.0；下文中文为本次分析与改写，短引文、字段和案例归属于上述作者。SkillEvo 明说附录 prompt 是生产提示词核心约束的 **condensation**，省略了重复示例和格式校验指令，不能把附录当成完整可运行代码。

## 2. 原始输入到底是什么

### SkillEvo：人工解法是反馈的知识来源，模拟器负责把问题再次问出来

**论文事实。** 输入起点是人工升级工单的完整对话，包括真实用户陈述、先前机器人表现（若有）、人工处理过程和最终回答。约 40% 工单开头即转人工、约 60% 是机器人多轮未解决后转人工。系统先去标识，再筛选是否真正解决、是否有可以由 AI 复用的知识；不是将全部失败日志直接总结成 Skill。[§4.1.1](https://arxiv.org/html/2608.13120v1#S4.SS1.SSS1)、[B.1.3](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS3)

`judge_outcome` 的输出字段为：

```text
resolved: bool
reusable_by_ai: bool
human_action_type:
  resolved / handoff / waiting_for_user / internal_operation /
  document_guidance / configuration_guidance / unknown
```

仅“升级、再问细节、提工单”不算可复用解决；依赖内部诊断或后台操作且未给用户可执行办法的重故障也被过滤。下一步 `extract_signal` 才提取 `skill_topic`、`user_problem`、`knowledge_facts`、`suggested_change`、`generalizable`、`knowledge_type`、`quality_score`。`generalizable` 和样本质量是两个判定，不应混成“高分就可写入”。[B.1.3、B.2.2](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS3)

同一原始工单还被转换为两种不同可见面的材料：

| 材料 | 接收方与用途 |
| --- | --- |
| `opening_message` | 给模拟用户；只陈述初始症状和请求 |
| `behavior_facts` | 给模拟用户；限定用户先前做过什么、看到了什么及环境事实 |
| `emotion_trajectory` | 给模拟用户；限制透露信息的节奏及情绪变化 |
| `target_keywords: [{topic, priority}]` | 给模拟用户及意图状态机；`key` / `minor` 意图议程 |
| `expected_solution` | 单独给 Verifier 的人工参考解法；最多 200 词，过滤后台代操作；禁止注入模拟用户 |

关键原文约束是 `expected_solution` “is never injected into the simulated-user prompt”。模拟器并不重新执行用户操作，也不能通过读日志、抓包、SSH 自己调查；其输出是 `<reason>`、`<agenda_check>`、`<action>`、`<say>`。状态机依据 `<agenda_check>` 中逐字报告的议题更新意图状态，正常结束要求议程得到覆盖，反复无进展则可以放弃；最大对话轮数为 10。[B.1.1–B.1.2](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS1)、[附录 F](https://arxiv.org/html/2608.13120v1#A6)

**推断级。** 这是一种有边界的咨询场景重建，不是对生产环境的完整执行重放。服务 agent 只有 Skill 加载和只读检索工具，写工具被注销。因此其主要结果是“建议的知识是否正确、完整”，不能等同于修改代码后真实测试通过、云操作真实生效、产物真实落盘。[附录 E](https://arxiv.org/html/2608.13120v1#A5)

### SkillTriage：任务契约、两条运行和验证结果共同构成输入

**论文事实。** 其输入需要共享任务视图，以及 target / reference 两个运行视图。初始任务指令、输入数据、仓库或容器状态、验证器、模型和 agent 框架保持相同，只改变 Skill 设置。target 是被审计的 Skill 运行，reference 是无 Skill 或另一个语义相关 Skill 的运行。候选 Skill 通过正常加载界面提供，agent 可以不加载；必须读取实际加载记录，不能把“Skill 可用”当成“Skill 已影响执行”。[§III-A–C](https://arxiv.org/html/2608.11888v1#S3.SS1)

核心证据包括：任务要求、Skill 文件内容、两个运行的有序轨迹、确定性 verifier / tests 结果、生成产物、token 和耗时。轨迹涵盖模型消息、工具调用、文件操作、搜索、编辑、命令执行等；效率分支进一步依赖逐步骤的 token / time / tool 记录。原文没有公开完整字段序列化格式，也没有承诺每个事件具备可恢复的环境快照。[§II](https://arxiv.org/html/2608.11888v1#S2)、[§VI-A](https://arxiv.org/html/2608.11888v1#S6.SS1)

两种进入分析的前提：

- 功能问题：target **FAIL**，reference **PASS**。
- 效率问题：二者都 **PASS**，target 的 token 比值与耗时比值都大于 1，且至少一个大于主阈值 2.0。不能仅因一方 token 多、另一方更快就算该论文的效率退化。

reference 是 **pseudo-oracle**：证明相同任务和 verifier 条件下存在更好运行，不是完整语义正确性的人工 gold。论文先移除证据不足、疑似 verifier 过窄误判及重复案例，再由人工逐案确定根因并形成小组共识。**SkillTriage 的自动分类从这些已确认问题开始；它不是从未经审查的日常日志自动发现 Skill 有害的检测器。** [§III-D](https://arxiv.org/html/2608.11888v1#S3.SS4)、[§VI](https://arxiv.org/html/2608.11888v1#S6)

## 3. 谁评价谁，怎样定位错误位置

### SkillEvo 的诊断链

1. **先审模拟器是否问够。** `c_U` 是关键意图中实际被问出的比例；`c_U < 1` 时将样本归为 Evaluation Noise，并移出 agent 侧分母。未被问到的要求不能直接算 agent 知识失败。
2. **再审 agent 对已暴露意图的回答。** Skill 命中是 gating factor：未命中则 `h=0`，`s_C=0`。已提出意图按人工“意图—解法”对判正确与否，关键/次要权重为 0.7/0.3。`s_C` 是意图准确度，不能等同于整个任务成功率。
3. **Verifier 对知识内容给分和解释。** 主要检查规则、路径、约束、产品事实。文风、简洁性、对话策略不是主要扣分项；相反规则/相反结论最高只能 59 分。最终解决还要求分数至少 60 且不漏关键条件。
4. **Attributor 对照原始人工处理、模拟对话和 verifier 证据。** 其定位单位是“人工讲对的事实”与“机器人说错/漏说的话”，输出 Skill 能否修复，而非仅复述低分。
5. **Collective attribution 合并共性。** 只对 `knowledge_gap` 聚合；相同知识缺口多次出现时合并，避免把每条工单特殊细节逐条写进 Skill。

来源：[§3.2.2–3.2.3](https://arxiv.org/html/2608.13120v1#S3.SS2.SSS2)、[B.1.4–B.1.5](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS4)、[B.2.1](https://arxiv.org/html/2608.13120v1#A2.SS2.SSS1)。这些是基于可见语句和事实的证据定位；公开材料没有展示从工具调用依赖图定位“最早致因操作”的一般算法。

公开的两个输出形状如下；这里的占位内容不是实际运行结果：

```json
{
  "score": 80,
  "ai_solution_summary": "...",
  "human_solution_summary": "...",
  "reasoning": "..."
}
```

```json
{
  "root_cause": "knowledge_gap | capability_limit | eval_noise",
  "knowledge_facts": ["..."],
  "suggested_change": "...",
  "target_file": "...",
  "evidence": ["human utterance", "bot utterance"],
  "needs_human_review": false
}
```

其中 `knowledge_facts` 必须来自人工对话中的具体事实；不允许把个案 ID、金额或临时链接混入。`needs_human_review` 出现在 schema 和案例，但公开核心 prompt 没有提供充分的自动置位规则，不能据一个 `false` 推断可靠的人审升级机制。[B.1.5](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS5)

角色上，Editor 使用 `deepseek-v4-pro`；User Agent、Verifier、Attributor、Governor 使用 `minimax-m3`。这是编辑者与评价者分模型家族，不是所有评价角色彼此独立。原文没有在模型表中明确服务 agent 的模型身份，不宜自行补全。[附录 E–F](https://arxiv.org/html/2608.13120v1#A5)

### SkillTriage 的诊断链

1. **规范化成共享任务与双运行视图**，用确定性 evidence gates 检查最低限度的轨迹、Skill 和 verifier 材料。
2. **预先提取差分证据**，不让最终分类模型只凭两段长日志自由猜测。
3. **将分类定义作为候选解释的证据要求**，选能同时解释 target 结果与两条轨迹差异的标签。
4. **输出 category、subcategory、自然语言原因、引用的 Skill 片段或轨迹证据、repair suggestion**。这些是公开的报告语义字段，不能冒充已核验的 JSON key 名称。

功能分支的五个信号明确到以下检查对象：

| 信号 | 原文定义所检查的差异 | 可以帮助排除什么 |
| --- | --- | --- |
| DS1 | target 独有的环境/运行状态变更能否解释 verifier 失败 | 不能仅看最终代码就断言算法写错 |
| DS2 | 这些变更是 Skill 明确要求，还是 Skill 间接诱导 | 要把 Skill 指令和 agent 实际操作连起来 |
| DS3 | 任务要求的路径 vs target 实际写入路径 | 区分产物位置错与内容错 |
| DS4 | 已产出、产出前停滞，或拒绝产出 | 区分有错误实现与流程耗尽/适用范围误判 |
| DS5 | 对任务必需元素做聚焦的构造差异检查 | 区分错误填入与完全遗漏 |

效率分支按探索、实现/产出、产出后验证/调试分阶段；另标记依赖安装/环境修复、读取 Skill 引用文件等动作。对比总量、阶段量、标签量的成本增量。成本“最大来源”的初步估计只是提示，最终还须读高成本与低成本步骤，区别“每次调用更贵”和“多做了一批工作”。[§VI-A、Figure 4](https://arxiv.org/html/2608.11888v1#S6.SS1)

**重要实现边界：** 论文没有披露完整 DS 代码，不能把“computes”自动解释为五个全部由确定性规则完成的 oracle；文中明确称确定性的部分是最低证据 gates。也没有给出固定的逐步对齐算法、可验证的 causal graph、最早错误步骤的数学定义或完整归因 prompt。

执行任务使用 OpenCode 1.15.1 + Claude Opus 4.6；自动归因使用 GPT-5.5 对同一对证据判三次、2/3 投票。作者明确 **不重新运行 benchmark tasks**，这三次不是三次独立任务复现。[§III-C](https://arxiv.org/html/2608.11888v1#S3.SS3)、[§VI-B](https://arxiv.org/html/2608.11888v1#S6.SS2)

## 4. 是否真正区分 agent、工具、模拟器、评测器

| 责任面 | SkillEvo 的处理 | SkillTriage 的处理 | 仍未解决的边界 |
| --- | --- | --- | --- |
| Skill 知识 | 缺失、过时、错误路由归 `knowledge_gap`，可补人工已给出的事实 | 看相关 Skill 的范围、默认值、模板、流程如何改变目标轨迹 | 单次错误不直接证明 Skill 文本缺失；已有知识未读到、读到未应用也可能表现相同 |
| agent 能力/表达 | 知识正确但交付笨拙、绕远也进入 `capability_limit` | 从受控参照与人工过滤中减少普通能力不足/波动的混入 | 不是通用的 model-vs-skill 定责器；SkillEvo 的“不可由 Skill 修复”是其事实知识库范围定义 |
| 工具/环境 | 权限、缺诊断工具、后台限制、基础设施故障进 `capability_limit`，不写入知识反馈 | DS1/DS2 分析显式依赖故障、间接环境状态漂移；工具调用和环境状态进入证据 | 未提供完整的 agent 参数错误 / 工具实现 bug / 服务瞬断 / 环境配置四分判定和各自反事实验证 |
| 模拟器 | 意图没问到或场景失真进入 `eval_noise`，覆盖不足样本移出分母 | 没有用户模拟器；直接执行 benchmark 任务 | 意图覆盖只排除一种模拟失真，不能验证全部隐藏环境状态或真实操作后果 |
| 评测器 | 正确解法被按措辞/路线差异误判可进入 `eval_noise`；以人工参考为锚 | 先人工去掉 verifier 过窄的案例；ref PASS 只是该 verifier 下成功 | 两者都需要额外权威判断来识别判分器错；不能靠更多次同类模型投票创造真值 |

来源：[SkillEvo B.1.5](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS5)；[SkillTriage §IV-B](https://arxiv.org/html/2608.11888v1#S4.SS2)、[§VI-A](https://arxiv.org/html/2608.11888v1#S6.SS1)、[§VII-B](https://arxiv.org/html/2608.11888v1#S7.SS2)。最后一列为推断级边界。

SkillEvo 的 `capability_limit` / `eval_noise` 被排出 Skill **知识修改**闭环，并不表示系统已自动修复工具或评测器。SkillTriage 返回修复建议，也未展示自动改变 Skill/Tool 后再评估、发布的实现闭环。

## 5. 成对、反事实、重放：证据能支持多强的因果说法

| 问题 | SkillEvo | SkillTriage |
| --- | --- | --- |
| 有成对材料吗 | 有：人工处理与模拟处理；以及修订前后再次模拟 | 有：同任务的 target/reference 受控运行 |
| 是只改变 Skill 的实验吗 | 框架固定模型角色、反复改 Skill；总体有单轮反馈/治理消融，但人工处理和模拟处理本身不是同 agent、同环境的 Skill 单变量对照 | 研究设计固定任务、环境初态、输入、模型、框架、verifier，只改 Skill 设置，是更接近干预的比较 |
| 是精确重放吗 | 不是。新的模拟对话会自适应分叉；没有执行真实云操作 | 不是在相同轨迹前缀注入动作后精确回放；是不同 Skill 条件下的完整运行 |
| 排除了随机性吗 | 未见个案归因的受控重复任务实验或单条新增事实消融 | 原文未报告用于排除采样方差的多次任务重复方案；三次投票重复的是归因而非任务 |
| 能定位到某条 Skill 文本必然致因吗 | 指向可补事实与目标文件，但不保证区分未提供、未检索、未应用 | 轨迹差分和 Skill 引文可形成机制证据；换整个 Skill 同时改变多条指令，仍不能自动锁定唯一致因句 |

**推断级判断。** SkillTriage 的受控对照加执行证据，比“失败后写反思”强；可支持在固定设置下某种 Skill 条件关联并诱导了特定偏差。它仍不等于对每个案例做了重复干预、单句删除实验、工具回放来证明充分或必要原因。SkillEvo 的前后改善说明候选修订有用，也不等于诊断标签已经被因果验证。两者可以给可核对的原因候选；因果强度应随证据升级，不能随反思文本的自信升级。

**实验级与误读边界：**

- SkillEvo 在留出集报告 TSR 从 30.0% 到 81.8%；单轮 QA 为 66.4%。多轮反馈消融固定归因、编辑、治理模块，是作者对反馈来源的总体证据。每轮报告使用开发集选出的截至该轮最好版本，曲线单调不代表每次新修订都不退化。[§4.2–4.3](https://arxiv.org/html/2608.13120v1#S4.SS2)
- SkillEvo 的 Verifier 与人工共识一致率“超过 90%”，该段没有给出这项核验的具体样本数、混淆矩阵或根因分类准确率。另一个实验的 **200 条对话、两名专家、95.3%** 是模拟器在意图表达/透露节奏/情绪方面的相似度，不能移作 verifier 或 attributor 准确率。[§4.1.3](https://arxiv.org/html/2608.13120v1#S4.SS1.SSS3)、[§4.4.1](https://arxiv.org/html/2608.13120v1#S4.SS4.SSS1)
- SkillTriage 精确子类匹配为功能 111/125（88.8%）、效率 132/182（72.5%）；高层类别为 117/125、145/182。它测的是**已经确认有问题的集合里的人工标签匹配**，不含对所有正常任务的误报率，不能称为“日常日志自动识别 Skill 错误的 88.8% 准确率”。[§VI-C](https://arxiv.org/html/2608.11888v1#S6.SS3)
- 功能标签仍有 14/125 错误，集中在错误实现/遗漏、环境/路径边界；效率标签有 50/182 错误，常见多种成本原因混在一条轨迹。论文建议暴露确切 Skill 段落、步骤、产物差异和高成本事件，不能只输出标签。[§VI-C](https://arxiv.org/html/2608.11888v1#S6.SS3)

## 6. 一个完整的 SkillEvo 案例：原始工单到有界修改

以下是作者附录 D 的 COS 工单 17413068，仅叙述论文中的历史规则，不能当成现行云产品政策。步骤与关键数值来自原文，JSON 值为中文缩写。[附录 D](https://arxiv.org/html/2608.13120v1#A4)

1. **原始材料。** 用户有 200 GB/月流量包，7 月 27 日 23:59 到期，已用 182 GB、剩 18 GB。人工处理给出：续费延长有效期；新周期配额到重置日才可用；旧包提前耗尽转按量计费。
2. **构造任务。** 关键意图是续费何时生效，次要意图为旧包耗尽会否停服及是否扣余额。模拟用户只能看场景，不看人工解法。
3. **运行与最早偏差。** agent 第一回合就说续费立即生效并把额度立刻加到当前包。后续对“耗尽后转按量”答对，却未纠正第一句。用户最终仍表示理解和感谢。意图覆盖达到 1.0，因而不能把错误推给“模拟器没问”。
4. **Verifier。** 对照人工规则打 10 分，记录双方 solution summary，指出立即加额度与到重置日才可用的矛盾。用户的感谢没有覆盖这个独立判定。
5. **Attributor。** 输出 `root_cause=knowledge_gap`；`knowledge_facts` 为续期、重置日和按量计费三条事实；`target_file=references/resource-pack-deduction.md`；`evidence` 引人工正确说法与机器人错误说法。另一工单相同问题被合并成一个信号。
6. **Editor。** 只补目标文件的有效期部分，说明新周期在到期次日 00:00 重置、此前不能使用新配额、提前耗尽扣余额；余下十三节不动。编辑受原始基线约束。
7. **修订后再模拟。** 同一场景中首答正确，追问也正确，Verifier 给 92 分。此处证明的是论文展示的这个修订后对话改善，没有公开复跑原始生产用户操作。

这里有两条必须保留的证据限制：

- **错误在第一回合已可见。** 本例本身不能证明必须多轮才发现这个反向规则；多轮的总体价值应看其对照实验，不能由本例独自承担。
- **原 Skill 并非完全没有续费规则。** 附录 D.5 的修改前文本已写着 “Renewal extends validity only and does not add traffic quota”。因此公开 diff 更直接证明补充了重置日期、使用顺序等细节；它没有独立排除已有规则未被检索/正确应用的原因。正文的 `knowledge_gap` 也包含 mis-routed knowledge，不能将这个总类误写为“原文必然缺一条知识”。[D.2](https://arxiv.org/html/2608.13120v1#A4.SS2)、[D.5](https://arxiv.org/html/2608.13120v1#A4.SS5)

这也解释了日常反馈为什么不能只读用户最后一句或 agent 自述“已完成”：可信反馈来自可观察的任务要求、实际行为及另一条可核验事实之间的冲突。

## 7. 一个 SkillTriage 案例：测试绿过，却验证了另一个环境

作者 §IV-B 的 `openpyxl` 例子更接近日常 coding agent。[原例](https://arxiv.org/html/2608.11888v1#S4.SS2)

| 步骤 | 原文可核对的证据 | 诊断含义 |
| --- | --- | --- |
| 1. 任务契约 | 创建仓库中的 `openpyxl/utils/report_engine.py` | 要交付的是该仓库中的可导入模块 |
| 2. target 操作 | 判断旧版本不兼容，执行 `pip install openpyxl`，切到 `/tmp`，从 `sys.path` 去掉 `/workspace/openpyxl` | 运行时已改为外部安装，验证环境发生漂移 |
| 3. target 后果 | verifier 的 import / xlsx 测试失败；verifier 从仓库包导入 | target 自检不再验证 verifier 所加载的对象 |
| 4. reference 操作 | 在仓库 `openpyxl/formatting/rules.py` 将 `from collections import Mapping` 改为 `from collections.abc import Mapping` | 保留仓库执行上下文并处理兼容问题 |
| 5. 差分归因 | target 独有的环境变更解释了失败；归 Environment-State Mismatch | 不能只将报错归到 `report_engine.py` 代码内容 |

按 §VI-A 的框架，DS1 会看上述环境差异，DS2 还应检查具体 Skill 是否要求或诱发这些操作。**原文案例未刊出那个 Skill 的完整相关段落，也未提供该例的完整机器报告，所以本文不能进一步声称已经核验“是哪一句 Skill 直接导致 pip install”。** 这是环境漂移有强证据、精确 Skill 文本归因仍受公开材料限制的案例。

可提出的修复约束（**本文工程建议，不是作者工具的原样输出**）：下次修改应保持任务指定仓库的导入来源，修改前后记录 `cwd` 和实际模块路径；不能通过换成系统安装包来证明仓库修改成功。如果原 Skill 明确要求这种替换，改那条条件；如果是 agent 临时选择，先修执行/验证约束，不能凭相同症状向无关 Skill 追加冗长警告。验收应从任务指定环境重新导入并检查产物，而非只接受此前那条绿测试记录。

另一个清晰的定位例子是 §IV-D：任务要求写 `libs/langchain/langchain/`，target 按“真实包是 langchain_classic”写到了 `libs/langchain/langchain_classic/`，reference 按任务路径写入。DS3 在此定位 Wrong Artifact Location，优先修路径契约，不应先重写 RAG 内容。[§IV-D](https://arxiv.org/html/2608.11888v1#S4.SS4)

## 8. 反馈如何具体约束下一次修改

**SkillEvo 已给出可借鉴的编辑约束。** [B.1.6–B.1.8](https://arxiv.org/html/2608.13120v1#A2.SS1.SSS6)

- 先输出 `signal id | verdict | target file and section | rationale` 筛选表，规划阶段不编辑；逐文件编辑前先读目标节，已覆盖的内容不机械追加。
- 新知识默认进 references；`SKILL.md` 是路由入口，仅新主题路由或新的全局规则才改。检查是否在 description 声明范围内、是否稳定、是否为新增知识。
- 聚合多个失败到 2–4 类共性再精改，超出 Skill 范围就标 out of scope，不把能力边界越写越大。
- Checker 同时看原始基线 `S0 → current` 和上一轮 `S(t-1) → current`：前者找累计事实丢失，后者找本轮错误和无关内容。修复必须恢复丢失的稳定事实，同时不能一键回滚所有合法新知识。
- 严重事实丢失、新错误、格式破坏会使 `passed=false`；结构冗余一般作为建议带入后续轮次。核心 prompt 还豁免少量非核心知识点丢失，不能把正文“事实保持硬约束”解释为每个字节都必须保留。
- Governor 可建议 `merge_sections`、`consolidate_tail`、`split_file`，有优先级且每文件最多三条；拆分阈值是 700 行，description 的冗余阈值是 400 词。它不是输出一条泛泛“写简洁些”的反馈。

事实锚是“稳定知识”，不意味着现实产品规则永久有效。日常使用时若历史规则已经过时，需要用当前权威事实判定是否应废弃，不能把恢复历史文本当成天然正确；这是迁移时额外需要的判断，论文的旧工单参考不自动提供它。

**SkillTriage 的约束止于诊断和建议。** 它要求报告引用 Skill/轨迹证据，区分应改适用范围、环境前提、必需元素、产物位置、常驻上下文、额外步骤或依赖修复。正文提出应分离任务要求与示例/默认值，依据任务风险与预算约束验证量，但这些是论文发现与未来方向，不是已展示的自动修复、回归验证和上线系统。[§IV–VII](https://arxiv.org/html/2608.11888v1#S4)

## 9. 日常 Codex / Claude Code 可以迁移什么，缺什么时要降级

以下仅是**工程建议**，不涉及对具体 Codex/Claude Code 版本接口的配置说明，也不假设可拿到隐藏推理、完整上下文或环境快照。

可从真实执行记录逐步形成反馈，而无需预先准备完整人工答案：

1. **保存当时可见的契约。** 用户目标、明确路径/交付物/约束、发生变更后的最新要求。只凭任务名或事后总结很容易把“后来改了需求”错判为失败。
2. **保存实际事件和来源。** Skill 内容及实际加载位置/版本；原始工具调用参数、返回结果、错误、退出状态；必要的 cwd、仓库版本、修改 diff、产物位置。记录工具证据，不把 agent 叙述替代为工具执行事实。没有逐步 token/time 就不能做论文那种精确成本归因。
3. **先找可观察的违约，再找责任。** 文件没写到指定路径、命令失败却宣称成功、测试导入来源不对，这些可以由任务和工具/产物证据判断，不需要标准解法。审美满意度、隐含用户目标或未执行的外部效果则不具备同样的客观标签。
4. **定位第一处有证据的偏差。** 从失败观察回溯到具体工具操作或决定，再查看该处是否有 Skill 原句支撑。记录另一个解释：agent 自行偏航、工具行为异常、环境漂移、要求变动或 checker 过窄。只能定位“第一次观察到”时，不写成“唯一最初原因”。
5. **只对证据允许的对象提修改。** 明确错误规则可形成 Skill 小修订；一次远端超时不能自动变成永久 Skill 禁令；合法参数下工具稳定违反自己的契约才形成工具实现问题候选；测试检查了错误要求则应修 verifier。证据不足时保留问题，不能用自动写 Skill 来掩盖不确定性。
6. **能隔离时才加对照。** 对可本地复现的任务，在保存的初态分别跑旧/新 Skill，保持任务与验证条件一致；必要时只去掉可疑指令。日常任务涉及外部写操作、变化中的网页、用户临时输入时，不能承诺完整重放。离线回放固定工具返回只检验“这些返回下的 agent 行为”，不证明真实服务的效果。
7. **修复后的验证与归因分开记。** 修改后通过当前检查可以说明该候选在此例可用；单次通过不证明原根因唯一，也不证明泛化。再看未参与修订的其他实际任务是否出现同类问题或新退化。

一条实用反馈至少应把这些内容说清：**违反哪条要求；对应哪个事件/产物；最早可定位偏差；相关 Skill 原句是否确实加载；还有哪些替代解释；允许改哪个文件/规则；用什么实际观察验收。** 这是本文建议的内容清单，不是任一论文公开的 schema。

| 当前已有证据 | 可以说 | 暂时不能说 |
| --- | --- | --- |
| 单条轨迹 + 明确契约 + 产物/工具结果 | 此次发生了可定位的契约偏差 | 该 Skill 导致失败，删除它必然改善 |
| 再有实际加载的 Skill 片段且行为吻合 | 有依据的 Skill 归因候选，可提出范围很小的修订 | 已排除 agent 采样差异、环境与评测偏差 |
| 再有同初态的受控对照及重复验证 | 该设置下有更强的 Skill 效应证据 | 所有日常任务上净收益为正 |
| 只有“任务完成”叙述、用户没继续说话或最后一句感谢 | 仅有自述/弱用户信号 | 正确完成，足以自动沉淀成功经验 |

迁移价值最大的组合是：取 SkillEvo 的“可修复性过滤 + 证据限定编辑范围”，取 SkillTriage 的“解释执行差分 + 输出具体证据位置”。对于没有人工 gold、没有可控重跑条件的日常日志，应先产出可审阅、可验证的局部反馈，并保留未知责任；这一步已有实际价值，不必伪造完整因果结论。
