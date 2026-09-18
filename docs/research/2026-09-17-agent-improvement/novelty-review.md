# 独立新意审查：Memory Orchestrator 与现成 Coding Agent

审查时间：2026-09-17 至 2026-09-18（Asia/Shanghai）。范围：公开论文原文和官方源码，只读；未运行模型或基准，未修改产品，未向 OpenViking 导出项目分析。初始论证独立开展；随后根据协调者提示，额外核对 GRASP 和反事实归因路线。没有读取其他审查员的结论文档。

**结论：本轮没有确认可以承诺“方法首创”的 gap。** 把现成 Agent 的轨迹转为记忆或 Skill，再加入失败归因、验证、回滚、可靠性、适用边界、在线更新或因果估值，均有直接近邻。把这些组件接入 Codex / Claude Code，可以有工程价值，但本身不能作为论文方法贡献。置信度：高。唯一暂留的问题是原生 Coding Agent 中既有 Skill 库事故的可复现诊断；它目前是**有待建立动机的实证/产品假设**，不是已成立的研究空白。

证据等级：下文“论文实验”指作者报告，均未独立复现；“源码”指读取了对应公开实现；“审查推断”指本审查对贡献边界的判断。检索覆盖内置网页检索、另一公开搜索引擎和学术检索。未检索到某机制，不能推出无人做过。

## 1. 指定四项：宽泛主张已被覆盖

| 一手来源 | 已有机制与证据 | 对本项目的约束 |
|---|---|---|
| [OpenViking 官方源码](https://github.com/volcengine/OpenViking/tree/20ec78a149a0889a85b038627dddc70b46dceae3) | 不只是上下文存储。当前源码已有 session skill extraction，以及轨迹分析、skill gradients、streaming policy trainer 和实际 Skill 更新路径；见下文。 | 不能用“OpenViking 只管存和搜，我们才让 Agent 从经验更新 Skill”建立差异。 |
| [SkillFlow，2604.17308](https://arxiv.org/html/2604.17308v1) | 166 任务、20 家族；原生 Claude Code / Codex CLI 等执行，轨迹与 rubric 驱动 Skill 的增删改。GPT-5.3-Codex 的完成率从 52.41% 降至 46.39%；每个家族重置库，明确不以异质工作流交错检索为目标。〔论文实验〕 | “接现成 Agent”“在线维护 Skill”“发现负迁移”都不是新意。家族重置是其评测边界，但还要对照下列跨场景工作，不能直接当空白。 |
| [Evo-Harness，2608.15071](https://arxiv.org/html/2608.15071v1) | 已研究 frozen agent 的在线单次执行学习、general/topic skills、反馈粒度、跨任务和跨模型迁移；self-generated feedback 在 CL-Bench / SWE-bench Lite 均低于不演化，外部诊断反馈更可靠，但更细反馈并非处处更好。〔论文实验〕 | “噪声轨迹蒸馏”“按失败在线更新”“外部反馈比自评可信”“泛化技能与局部技能分离”均已被直接研究。 |
| [SkillSmith，2606.01314](https://arxiv.org/html/2606.01314v1) | Skill–Tool 原子联合编辑、技能共现的互补/冲突效用、anti-pattern memory、测试与回归门、淘汰。共现效用来自分类难度残差的观察性比较，不是随机干预。〔论文方法/源码〕 | “区分工具与 Skill 问题”“多个 Skill 相互干扰”“失败模式长期保留”“治理后发布”已有近邻；观察性估值的限制也不等于干预估值没人做过。 |

### OpenViking 必须以源码而非滞后概念描述为准

冻结版本为 `20ec78a149a0889a85b038627dddc70b46dceae3`，从官方目录页面的 `currentOid` 读取。可直接复查：

- [compressor_v3.py](https://github.com/volcengine/OpenViking/blob/20ec78a149a0889a85b038627dddc70b46dceae3/openviking/session/compressor_v3.py#L794)：`_session_skill_extraction_enabled` 检查配置与 skill processor；`extract_session_skills` 提供独立于 Agent Evolution memories 的提炼路径；约 L1026 / L1087 的轨迹分析与梯度提交连接到 skill trainer。
- [session.py](https://github.com/volcengine/OpenViking/blob/20ec78a149a0889a85b038627dddc70b46dceae3/openviking/session/session.py#L2754)：会话提交路径读取 `session_skill_extraction_enabled`。
- [skill_operation_updater.py](https://github.com/volcengine/OpenViking/blob/20ec78a149a0889a85b038627dddc70b46dceae3/openviking/session/skill/skill_operation_updater.py#L93)：已有 Skill 创建与 `SKILL.md` 替换更新。
- [experience_lineage.py](https://github.com/volcengine/OpenViking/blob/20ec78a149a0889a85b038627dddc70b46dceae3/openviking/session/memory/experience_lineage.py#L29)：已有 experience–trajectory lineage，以及 success / failure / partial / unknown / unfinished 的结果分类。

[概念文档](https://docs.openviking.ai/en/concepts/02-context-types)仍描述相对静态的 Skill 定义。这不能覆盖掉上述新源码。这里证明的是**已有受配置控制的实现路径**，没有证明默认开启、用户本机启用、端到端效果或可靠性。也不能因本轮未审完整个 trainer，就声称其“没有验证机制”。

另外两处实现级复核：SkillFlow 的 [runner](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L721)实际应用 patch 并记录历史；SkillSmith 的 [loop.py](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L167)实际包含 integration / capability holdout / validation regression 检查。不是只从摘要推断存在。

## 2. 主动找到的否决证据

以下是最接近反例，不是替本项目推荐一套组件清单。

| 想宣称的改进 | 已经做过什么 | 剩余边界，及不能作出的跳跃 |
|---|---|---|
| 先验证、无回归才发布，失败后缩窄 trigger | [GRASP，2605.29668](https://arxiv.org/html/2605.29668v1) 在平衡的过往通过/失败 probe 上重新运行当前库与候选库，要求净收益与硬回归预算；还用对比修订缩窄 trigger 或增加 guard。 | 其主要场景与原生编码不同，但换场景不能独立构成新方法。**直接否决“回归门 + 可回滚发布”首创。** |
| 区分可修知识缺口、能力不足和评测噪声，避免把失败写成错误知识 | [SkillEvo，2608.13120](https://arxiv.org/html/2608.13120v1) 已采用这三类 collective attribution，仅知识缺口进入更新；双侧评价区分模拟用户与服务 Agent 责任，并治理膨胀、引用破损和过度泛化。 | 它有云服务工单及 human reference，不能据此确认无参考答案的编码场景已解决。但**先归因再更新已经不是 gap**。 |
| 让技能携带来源、适用边界、验证规则和可靠性 | [MSCE，2607.16621](https://arxiv.org/html/2607.16621v1) 已定义 evidence anchors、boundary、verification、reliability 与反证修订；作者明确承认 gain / value 只是启发式，非因果效应。 | 不能把字段更齐全叫方法贡献；因果限制需继续对照下面的 SkillSV、SkillMaster、CMI。 |
| 观察成功次数不可靠，改为后验置信度驱动 patch/split/retire | [Bayesian-Agent，2606.08348](https://arxiv.org/html/2606.08348v1) 已有 feature-conditioned categorical posterior、对应技能维护决策及 Claude Code 等 adapter。 | “给现成 harness 加证据与不确定性层”已有直接实现；该论文也不宣称完整 Bayesian model selection。 |
| 用少量撤销实验而非共现相关性估计 Skill 价值 | [SkillSV，2608.04562](https://arxiv.org/html/2608.04562v1) 已做依赖有效的 coalition、成对删除与等长 padding、有限 rollout 预算下的 chain-coupled estimator、共享 task window 与不确定性估计。 | 其对象是固定 Skill 内部单位、固定 Agent 和任务分布。把多个 Skills 当作 units 并直接移植，仍是强基线或工程应用，**不是反事实估值首创**。 |
| 用前后技能库在相关任务上的差分奖励更新 | [SkillMaster，2605.08693](https://arxiv.org/html/2605.08693v1) 已在 held-out related probes 上分别 rollout 原技能库与编辑后技能库，以成功及步数收益训练技能编辑。 | 它需要训练不代表其 probe 思路可重新主张为新；冻结 Agent 只改变部署约束。 |
| 对错误/有害记忆做干预式选择 | [CMI，2605.17641](https://arxiv.org/html/2605.17641v1) 已比较无记忆、带记忆、扰动记忆；内部 utility 使用 task scorer，最终报告另用 judge。 | 文中明确有额外推理成本及 label-free 设置的待研究限制。可问缺少现成 scorer 时的实用性，不能声称首个因果记忆选择。 |
| 对技能事故定位第一个行为分歧 | [CTA，2605.11946](https://arxiv.org/html/2605.11946v1) 已对 SWE-Skills-Bench 成对轨迹分阶段、对齐与定位差异；[SkillTriage，2608.11888](https://arxiv.org/html/2608.11888v1) 已归因 307 个功能/效率退化案例。 | CTA 明确是描述性对比而非严格因果估计，主要实验每项 r=1。这允许改进实证严谨性，但**“可复现技能事故诊断”这个主题本身也已有论文**。 |

另外的实验边界不能遗漏：

- [Rethinking Skills，2608.02636](https://arxiv.org/html/2608.02636v1) 已固定演化程序比较成功/失败反馈，记录 rollback、验证选择，并测 robustness、transfer 和额外推理对照。作者报告 388 个候选只有 55 个成为 byte-distinct validation best。不能把“多轮不单调”当新发现。
- [Demystifying Agent Skills，2608.14036](https://arxiv.org/html/2608.14036v1) 已在 Codex / Gemini CLI 区分经验表示、结果标注、跨框架迁移、检索与真实使用；[SkillEvolBench，2605.24117](https://arxiv.org/html/2605.24117v1) 已采用 acquisition 后冻结库，测试 context shift、adversarial shortcuts 与 composition。因此“原生 Agent + 迁移边界”也不足。
- [RoMeRL，2608.02508](https://arxiv.org/html/2608.02508v1) 已研究同一轨迹奖励误记给共同检索的无关经验；[AEL，2604.21725](https://arxiv.org/html/2604.21725v1) 在其短期、高噪声金融实验中报告复杂 credit 不如 uniform credit。后者是必须保留的反结果，不能推广成编码领域必然失败，也不能假设更复杂归因天然值得成本。
- [Memory Portability，2609.05339](https://arxiv.org/html/2609.05339v1) 已分离 writer / reader / embedder 与原始材料保留的迁移影响，但实验是 48 段合成历史和两个小型模型，不能直接替代 procedural Skill 的编码迁移证据。
- [Neuro-Symbolic Skill Induction，2605.01293](https://arxiv.org/html/2605.01293v1) 已根据冲突状态修订条件分支与 feasibility region。因此“通过反例学习适用前提”也不是一个可直接承诺的方法空白。

## 3. 唯一暂留的条件性实证问题

**在原生 Coding Agent 的既有 Skill 库发生真实退化时，能否在固定诊断预算内，比原生排查及已有成对/估值方法更准确地定位最小有害内容或组合，并恢复未来任务表现？**

这不是“自动进化”或“因果归因”的新定义。它成立至少需要三个尚无项目证据支撑的前提：

1. 真实库里有足够频繁、成本足够高、可冷启动重现的事故；并且不是普通模型随机性、工具版本漂移或环境故障。
2. 现成 Agent 自查、逐个禁用、回到已知良好库等简单方法不能以更低成本解决大部分事故。
3. CTA / SkillTriage、SkillSV、必要时 GRASP 的合理适配仍留下稳定的准确率或成本差距。

若缺第 1 条，动机不存在；缺第 2 条，产品没有必要；缺第 3 条，只剩集成工程。研究贡献需要由实验发现来决定，不能先承诺“没有人处理原生 Agent 的事故”。

### 一项可以否决它的实验

做一个**冻结事故集上的预算匹配诊断与修复试验**，先不建设新演化平台。

- **样本入口**：在事先选定仓库/任务范围里记录连续出现的候选事故及总分母，不只收集已知会被方案解决的案例。保留 Skill 快照、版本、工具/仓库快照、输入、输出、测试和消费证据。独立确认其中多少真由 Skill 可见性或内容变化造成。少量人工注入冲突只用于机制校准，不能替代真实事故动机。
- **对照**：原生 Agent 获得同样日志后排查；简单逐个禁用/回到良好库；CTA / SkillTriage 的成对诊断；将库内依赖闭包映射为有效 units 的 SkillSV。候选诊断器只有在这些基线上仍有问题时才值得引入。用相同模型、诊断信息、可调用工具及总 rollout/费用预算。
- **裁决**：在与诊断器隔离的重置环境中复验提出的禁用/修补，并在未见但相关任务及过去正常任务上测恢复与回归。对小库可用独立重复的有效组合审计建立裁决参考；其成本单列，不能算成算法免费的知识。判定不是复述诊断报告，而是查看介入后的任务结果。
- **主要量**：正确定位率、错误归责/错误禁用率、修复后的净成功任务数、诊断与修复总费用、到恢复的时间。必须报告未复现、无归因、未修复及超预算实例。相同预算上的总体净收益是主终点，漂亮的解释质量只作辅助。
- **原生执行契约**：随机分配的是 Skill 的可见性/可加载性。读取与遵循是介入之后的行为；主效应先报 exposure 的 intention-to-treat，不能按“实际 read”筛掉未遵循样本，再把差异叫因果效果。Codex 与 Claude Code 分别做同一 executor–model 配对内的比较，不能把模型差异当 harness 效果。
- **否决规则**：预先定义值得承担维护成本的最小收益。如果真实事故稀少/大多不能稳定重现，或简单原生排查已解决同等问题，或 SkillSV/SkillTriage 在同预算下达到同样恢复与误归责水平，停止新方法路线。对于结果不确定，应说“证据不足”，不能用不显著差异证明等价；可在预算允许时用等价检验或收益上置信界低于预设门槛作停止依据。

最强反证并非再找一篇同标题论文，而是**把既有 SkillTriage 或 SkillSV 做最小适配，就在该冻结事故集上达到相同诊断效果与成本**。那会同时否决“方法必要性”和“需要复杂新 controller”的假设。

## 4. 对当前主决策的第二轮意见

“不把已知演化、归因、估值重新包装为新方法”是有证据支持的决定。收缩到既有 Skill 库事故诊断也比泛化的自进化平台更容易验收，但目前**没有可以承诺的研究 gap**：CTA / SkillTriage 已研究诊断，SkillSV 已研究有限预算估值；仅补原生 CLI adapter 不足以越过它们。

现在可承诺的是一个边界清楚的工程/实证产出：记录真实故障分母，复现事故，建立强基线，测已有诊断方法在原生执行约束下的效果与成本，并允许得到负结论。只有这一步暴露出稳定、可定位的剩余失败机制，才应进一步提出方法。当前不应因项目需要论文定位而先发明 gap，也不应宣称“OpenViking 未做”就等于全领域未做。

## 5. 证据限制

所有数字均来自作者公开报告，未复跑；公开源码存在不等于实现与论文完全一致，更不等于生产可用。部分新论文为预印本；新颖性覆盖广不代表每个方法的实证强度相同。本轮没有用户真实 Skill 事故语料、原生排查成功率或任何同预算比较，所以对产品必要性只能给条件性判断。临时原文缓存位于 `/tmp/novelty-review-public-sources/`，本文件的外链与固定 commit 才是可携带的证据入口。

## 6. 工程目标澄清：仓库级经验维护可条件性立项

用户澄清后的目标是：**服务现成 Coding Agent，把真实仓库的执行与 review 纠正转为版本化 Skill，验证后续同类任务是否减少重复人工纠正；不要求算法首创。** 按这个目标，允许条件性工程立项。前文针对方法首创的否决，不应扩展为“模块已有，所以整个项目没有价值”；也不应继续把“既有 Skill 事故诊断”当成唯一可做的产品。事故诊断可以是维护流程中的一个环节。

**一句 gap 假设：在不修改现成 Coding Agent 的前提下，真实仓库中的执行与人工 review 纠正，能否通过有来源、适用范围和版本记录的 Skill 维护流程，在后续同类任务上持续减少重复人工纠正，且收益不被维护费用与回归抵消，是本项目需要用真实样本补齐的部署证据缺口。** 这是目标部署中的待证问题，不是“全领域无人做过”的断言。目前还没有本项目的纠正频率、可复用比例或净收益证据。

### 最近邻与方法归属

整体最近邻是 **SkillFlow 的原生 Agent 顺序执行与 Skill 更新协议，加上 Evo-Harness 的在线经验编译**。本项目拟把学习与验收单元放到真实仓库的连续工作流和人工纠正上；这一区别可以形成明确场景与实证问题，但不能预先宣称已有工作不支持仓库场景。

| 本项目所需环节 | 可复用方法及准确归属 | 需要本项目补证的部分 |
|---|---|---|
| 执行轨迹与结果转为可持久 Skill patch | [SkillFlow](https://arxiv.org/html/2604.17308v1) 已在原生 Coding Agent 上增删改技能；[Evo-Harness](https://arxiv.org/html/2608.15071v1) 已编译在线单次经验，并区分 general / topic skills。 | 真实仓库哪些经验会再次出现；episode 的局部修复能否变成跨任务有效的规则。 |
| 判定 review 指向什么，避免错误归因 | [SkillEvo](https://arxiv.org/html/2608.13120v1) 的责任划分与 repairability screening 可借鉴。其云服务实验使用工单、人类参考方案和模拟交互，不能等同于自然发生的编码 review。 | review 中规范偏好、真实缺陷、环境问题与一次性要求如何区分；只凭有限反馈时误写率多高。 |
| 限定适用范围并保留证据 | [MSCE](https://arxiv.org/html/2607.16621v1) 已有来源锚点、边界、验证规则与可靠性；OpenViking 源码也已有 lineage。 | 仓库、依赖版本和任务类型变化时，哪些范围条件必要；这些元信息能否实际帮助维护。 |
| 更新后接受、修订或撤回 | [GRASP](https://arxiv.org/html/2605.29668v1) 的当前库/候选库成对探针、通过/失败平衡与回归预算可以直接作为基线；[SkillSmith](https://arxiv.org/html/2606.01314v1) 提供集成和回归验证的近邻。 | 真实仓库能负担多少验证；可重复测试不足时应保留多少人工判断。无需为立项先发明新的 gate。 |
| 证明后续收益，不把多写文档当改进 | [Rethinking Skills](https://arxiv.org/html/2608.02636v1) 的候选版本记录、验证选择和冻结部署评测，以及 [SkillEvolBench](https://arxiv.org/html/2605.24117v1) 的 acquisition / frozen deployment 分离可复用。 | 改善是否出现在之后的未见同类任务；人工纠正与维护总成本是否一起下降。 |

因此，可能的贡献归属是**仓库经验维护系统、真实连续任务/纠正数据及其效果证据**。方法章节应明确哪些更新、验证和归因机制来自上述工作；系统贡献要说明接入真实工作流后新增了什么可验证能力，而不是把已有组件改名。

### 与 OpenViking 的互补关系

可将 OpenViking 作为上下文持久化、检索、会话归档、lineage 及可复用经验/Skill 提炼的底座。Memory Orchestrator 则可以承担一个面向仓库工作的薄流程：连接执行和 review 的来源，明确经验候选适用范围，将候选绑定到 Skill 版本，按选定验证规则决定启用或撤回，并记录后续任务的实际收益。此处是**建议的产品职责划分**，不是声称 OpenViking 做不到这些事。

不能承诺的差异包括：OpenViking 只存静态技能、没有自动更新、没有来源追踪、没有验证或训练路径；也不能承诺本项目必然提高任务成功率、减少纠正、实现跨仓库迁移，或同时适配所有 CLI 行为。这些分别需要完整源码/配置核验及真实执行证据。若 OpenViking 的已有能力足以承担某一步，应直接复用；独立产品问题不要求独立重写底座。

### 条件性立项的第一道验收

先选定有限的仓库与重复任务类型，连续记录真实纠正及其总分母。预先定义“同类重复纠正”，区分正确性缺陷和用户偏好，保留未能抽出通用经验的案例。经验更新只使用此前任务，后续未见任务作为评测，避免拿修过的同一任务证明长期收益。

核心对照应包含按实际版本固定的原生 Agent 记忆/仓库指令工作流、OpenViking 单独使用的明确配置，以及简单的反馈总结后追加/修订 Skill。它们获得相同历史反馈与可比预算；本项目再测版本与验证流程带来的增量。主要终点是**每个合格后续任务的重复纠正率、人工时间、成功率/回归与总维护费用**，不是 Skill 数量、写入次数或读取率。编码任务数量、任务类型和仓库须保留分母，避免任务分布变简单造成虚假进步。

若同类纠正确实重复出现，而且该流程相对基线降低人工负担、守住回归并有可接受成本，即使全部复用已有算法，也足以支持一个完整的工程研究论证。若简单工作流同样有效，就收缩系统复杂度并如实报告；若没有稳定复发或净收益，则调整产品问题。**现有模块并不构成立项否决；真实需求与可验证收益才是工程立项条件。** 本澄清段仅使用本轮已读材料，未新增检索、模型执行或产品改动。
