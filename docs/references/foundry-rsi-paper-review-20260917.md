# Foundry 与 Agent 自进化：六篇论文对照

日期：2026-09-17。用途：判断 Foundry 与“演化”的真实关系，以及面向 Agent 工程、算法岗位的项目表达。阅读范围是六篇论文的方法、评测和局限；未复现实验，也未覆盖收藏文章中的全部论文。

结论（定位置信度高；路线建议置信度中）：Foundry 已包含执行反馈驱动的任务演化与可信轨迹生产；目前找到的证据不足以把它描述成已验证有效的求解 Agent 自进化系统。它与自进化研究的环境、课程和评测基础设施直接相关。

## 研究契约与证据等级

回答三个问题：

1. 代表论文更新了哪个对象，更新怎样进入后续任务？
2. Foundry 实际更新的对象是什么，哪些能力已有代码或执行证据？
3. 怎样以最少的新工作补足研究问题，而不把已有项目改名当成成果？

已知：用户同时考虑 Agent 应用/平台与算法/研究岗位。种子假设：Foundry 可能与演化关联不大。下述判断分别从论文机制与本地代码/实验报告两条证据链检验，未把种子假设作为结论。

等级：实验级表示论文或本地报告有执行/对照记录，不表示本次独立复现；实现级表示核对了源码或产品契约；推断级表示本次分析或候选建议。

## 六篇论文：更新对象与验证方式

| 工作 | 角色与更新对象 | 核心机制和评测边界 |
| --- | --- | --- |
| [ReasoningBank](https://arxiv.org/html/2509.25140v2) | 方法；可复用推理记忆 | 从自判成功/失败轨迹提炼策略，按任务检索并注入后续模型输入。比较无记忆、原始轨迹记忆、工作流记忆；基本 consolidation 是追加，不应转述成已实现复杂的自动纠错治理。 |
| [Evo-Harness](https://arxiv.org/html/2608.15071) | 方法；自然语言 Skill/Harness 指导 | 冻结 Solver；失败后提取 lesson、trigger、evidence、scope_hint，批次结束由 Evolver 增加、合并、修订或跳过，指导后续任务。其 Harness 更新不等同于执行代码自修改。 |
| [Darwin Gödel Machine](https://arxiv.org/html/2505.22954v3) | 方法；Agent 自身的工具、工作流等代码 | 从版本集合选父代，分析其评测日志并修改自身代码，再运行编程基准。能编译且保有编辑代码能力的版本可入集合，不只保留立即涨分的版本；外层版本管理和选择规则固定。 |
| [SEAL](https://arxiv.org/html/2506.10943) | 方法；self-edit 生成策略与模型参数 | 内层按模型生成的 self-edit 做 SFT；外层根据适配后任务表现训练更好的 self-edit。普通固定数据 SFT/GRPO 不能直接等同于这种学习更新策略的双层机制。 |
| [SkillFlow](https://arxiv.org/html/2604.17308) | 基准与协议；被测 Agent 的 Skill 库 | 同一工作流族连续执行任务，用轨迹与 verifier 文本反馈生成增删改 patch；比较有无演化。同族共享流程，实例与难度变化；不同族重置 Skill 库，不能据此声称无限跨领域终身学习。 |
| [GDPevo](https://arxiv.org/html/2608.03764) | 基准与自动构建流程；被测 Agent 的持久经验 | 每组共享环境、5 个学习任务和 5 个测试任务；学习任务暴露规则片段，测试重组规则。与无学习经历基线比较，检验经验迁移。其环境、任务和验收资产与 Foundry 的职责最接近。 |

上述方法判断来自论文方法节，效果判断来自评测节；均为单篇论文的报告，不是相互复现。本文没有把不同 benchmark、模型或预算的分数横向排名。

## 负结果与局限

- **SkillFlow，实验级**：GPT-5.3-Codex 的完成率由 52.41% 降到 46.39%，下降 6.02 个百分点；Sonnet 4.6 持平。错误 Skill 可持续影响后续任务，Skill 数量和紧凑程度均不能单独证明收益。见论文 §3.2–3.3。
- **GDPevo，实验级**：其三个任务组的跨域测试中，fewshot 的六个非对角迁移有五个为负，最差 -5.0 pp；范围很小，不能外推所有跨域学习。基准构建还用预期学习增益校准任务，因此对外部任务分布的泛化需另测。见 §3.4、§4.3。
- **ReasoningBank，机制局限**：成功/失败信号依赖 LLM judge，错误判断可能产生噪声；本次没有找到它在主实验中整体退化的证据。见 Appendix E。
- **Evo-Harness，实验级与范围限制**：CL-Bench 的 EDS 子类在部分模型上退化；实验使用自然语言指导，未覆盖可执行程序形式的 Skill，也未验证多 Agent 场景。见 §4.3、Limitations。
- **DGM，资源与实现限制**：论文报告一次 SWE-bench 演化运行约两周且 API 成本高；版本选择流程本身不演化。不能因其开放搜索机制就声称获得无成本或无限自改进。见 §3、§6。
- **SEAL，实验级**：连续 self-edit 后旧任务表现下降，仍有灾难性遗忘；作者尝试的 PPO/GRPO 训练不稳定，采用 ReST-EM。见 §3.1、§5。

GDPevo 当前网页正文说明实验采用 V1+V2、24 组共 240 个任务。收藏文章中的 120 指最初 V1，不能拿旧数量描述当前全文实验。以上数字均绑定当前读取的论文设置。

## Foundry 当前证据

主要核对工作区：`/home/kelong/pycodes/foundry-s3-sft-trajectories`，当前提交 `e32eaa2`。训练交接核对：`/home/kelong/pycodes/foundry-s4-verified-agent-learning`，提交 `c25dbb3`。旧 Direct rewrite 分支的 README 与主线不同，不混合其状态。

### 产品与实现

- [PROJECT.md](/home/kelong/pycodes/foundry-s3-sft-trajectories/PROJECT.md:3) 定义 Need → 环境 → 高质量任务 → 可验证 Episode → 下游 SFT/RL。
- [task_evolution.py](/home/kelong/pycodes/foundry-s3-sft-trajectories/src/agent_env_foundry/task_evolution.py:62) 实现 prerequisite、discovery、outcome_extension 三类任务扩展，结合父任务、公开起点、工具语义和受限反馈提出新 FrozenIntent。
- [propose_frozen_intent](/home/kelong/pycodes/foundry-s3-sft-trajectories/src/agent_env_foundry/task_evolution.py:950) 的更新对象是任务候选；代码明确区分直接提案与带父代/反馈的提案。
- [task_evolution_campaign.py](/home/kelong/pycodes/foundry-s3-sft-trajectories/src/agent_env_foundry/task_evolution_campaign.py:123) 包含直接覆盖、直接意图、演化及关闭反馈的演化模式，并记录谱系和反馈。
- S3 负责执行策略、关闭重开、终态判定以及 1/0/null 结果，不负责训练模型。见 [PROJECT.md](/home/kelong/pycodes/foundry-s3-sft-trajectories/PROJECT.md:159)。

### 执行证据及限制

2026-09-06 的任务已归档到 `.trellis/tasks/archive/2026-09/09-06-s2-task-evolution/`，task.json 标为 completed。根 README 仍链接旧路径并写 planning，因此不能只用该 README 判断实现状态。

[交付报告](/home/kelong/pycodes/foundry-s3-sft-trajectories/.trellis/tasks/archive/2026-09/09-06-s2-task-evolution/REPORT.md:1) 记录：实现和真实比较已完成，效果为 inconclusive，没有证明多步任务产出收益。该冻结六组实验共 266 个提案、67 个不同 TaskPack，多步选择为 0；这些是同一历史实验的分母，不与后续版本或重复 Episode 混用。报告中还有基础设施与审查失败，不能把所有失败当作模型能力不足。

[S4 交接文件](/home/kelong/pycodes/foundry-s4-verified-agent-learning/.trellis/tasks/08-31-s4-verified-agent-learning/gpu-handoff.md:13) 仍记录 CPU/config 已验收，GPU SFT、模型驱动 rollout、GRPO 更新、checkpoint 冷加载与继续 rollout 尚未执行。本次没有检查远端服务器，不能排除另有尚未归档的新结果，也不能据此声明已经完成训练收益验证。

## 对照判断

实现级：Foundry 包含任务演化，已经超出静态题库或简单文档检索。

推断级，高置信度：任务候选经反馈变化，与求解 Agent 的持久策略经反馈变化，是两个不同层次。任务更长、合法任务更多，都不能直接推出后续 Agent 更强；这个判断与六篇论文对“更新对象—后续使用—评测”的区分一致。

推断级，中高置信度：Foundry 当前最适合定位为“可执行环境与任务演化基础设施”。若进一步面向 RSI，GDPevo/SkillFlow 的任务族与迁移评测设计，比直接模仿 DGM 的代码搜索更贴合已有投入。

## 候选方向：把任务质量连接到学习价值

下面是讨论建议，不是已批准的实现任务。

先选一个确有可迁移规律、可独立验收的任务族。让 Agent 在若干学习任务上获得反馈，提炼并修订小型 Skill 库；随后固定 Skill，在未参与更新的新任务上评测。模型、工具、任务集合和执行预算保持可比较，更新器不能接触最终测试答案或反馈。

至少比较：无持久经验、直接追加摘要、反馈驱动的 Skill 更新。记录 Agent 真正接收的 Skill 版本和输入；分别统计成功率、配对救回/回归、更新额外成本、延迟与不确定性。再用新规则组合或另一任务族检查迁移边界。

关键研究问题是“所生成的任务能否提供可迁移的学习信号”，不是“能否生成更多、更长的任务”。这会让 Foundry 的环境、任务与验收能力成为实验主体的一部分，同时保持 Agent 更新机制清晰可替换。

岗位表达建议：工程侧突出真实环境、任务采样、隔离与证据；研究侧只有在新增对照成立后，才补充“面向 Agent 自进化的任务生成/评测”及实测收益。已有任务演化与实验无增益结果仍可作为真实研究经历陈述。

