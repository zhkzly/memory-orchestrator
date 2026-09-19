# 长轨迹的运行时压缩：ACON与Context-Folding核查

状态：限定范围核查完成。本轮仅研究，未修改产品、提示词、HTML，未运行模型或下载benchmark。核心项目限定为ACON与Context-Folding；后者不是Alibaba的AgentFold，不混用名称或结果。Complexity Trap只用于简短反证。

**核心结论：压缩后的表示很小，不等于压缩器自己的输入已经有界。** ACON已核主链是“超过阈值→把待压材料交给模型→替换执行器上下文”，没有看到先将任意大tool result分成有界块的通用机制；具体模板或上游环境可能另有限制，本次未核实的部分在下面明确列出。

要回答：实际删/改了哪些输入；何时触发、能否回读；消融证明的是当轮执行效率还是离线经验学习能力。

证据等级：**论文声明**为作者报告；**固定源码静态核对**为实际分支/字段，未运行仓库；**我们的推断**为本项目讨论，不冒充实验结论。

## 固定来源

- ACON：[论文v1](https://arxiv.org/html/2510.00615v1)，[微软官方代码](https://github.com/microsoft/acon)，commit [d63f9ae18959dc7215ff62899c94c5e8c56847ae](https://github.com/microsoft/acon/commit/d63f9ae18959dc7215ff62899c94c5e8c56847ae)，2025-10-14。
- Context-Folding：[论文](https://arxiv.org/abs/2510.11967)，[作者官方代码](https://github.com/MiaoLu3/Context_Folding)，commit [81626e97bb5f4eaa79edca045528829ce8850f5b](https://github.com/MiaoLu3/Context_Folding/commit/81626e97bb5f4eaa79edca045528829ce8850f5b)，2026-01-10。README明确称公开代码的训练结果完整验证仍在进行；源码行为不等于独立复现论文分数。
- 简短反证：[The Complexity Trap v1](https://arxiv.org/html/2508.21433v1)。其结论带具体agent/任务/模型范围，不推广成“摘要都无用”。

## ACON：两种压缩的实际入口

**固定源码静态核对**：`UnifiedAgent.run`在生成下一步动作之前尝试history压缩；执行环境动作之后，如果任务未结束且有observation，再尝试observation压缩，并用结果替换`env.observation`。这改变的是**当前运行下一步看到的上下文**，不是先把整份已结束轨迹提炼成跨任务Skill。[unified_agent.py L351–398](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/unified_agent.py#L351-L398)

| 通路 | 触发判据 | 压缩器实际接收 | 执行器随后使用 |
| --- | --- | --- | --- |
| Observation | 本条observation的token计数大于`obs_summarization_threshold`；类默认-1表示每次压 | task、当前session转成的history文本、本条**完整传入**的observation，以及opt_args | 替换后的`env.observation`；此前历史不会因此全部清除 |
| History | 去掉保留的最近k轮后，对旧history＋上一份summary计token，再与history阈值比较；另可有轮数间隔 | task、上一份summary、被选旧history整体 | 新session：system＋任务/summary＋保留的最近k轮 |

来源：[observation触发与构造](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/obs_optimizer.py#L78-L169)，[history触发与构造](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/history_optimizer.py#L83-L196)，[MemoryManager实际选择范围](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/memory.py#L320-L442)。

## “超过阈值”不是“输入最多这么长”

**固定源码静态核对**：`ObservationOptimizer._build_optimization_prompt`直接把observation和history放入模板参数；`HistoryOptimizer._build_history_prompt`直接放入所选history，并可附prev_summary。触发函数没有把材料裁成阈值大小，也没有切块后归并的循环。[obs_optimizer.py L117–169](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/obs_optimizer.py#L117-L169)，[history_optimizer.py L135–196](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/history_optimizer.py#L135-L196)

因此，一次新工具返回本身就很大时，越过阈值会**触发处理这个大输入**；阈值本身没有解决压缩模型如何装下它的问题。history模式通过只处理当前session旧段、保留尾部、复用已有summary避免每轮重读所有历史，但单轮增量仍可能越过阈值很多；任务、guideline、system和其他history也占压缩调用的输入。

**固定源码静态核对**：GPT名称由`LLMManager.create_llm`送到`ChatGPT`包装器，`_build_messages`直接装配字符串或消息列表，`generate`再发送给API；已读这一分支没有本地input截断。其默认`max_tokens=1024`是生成输出参数，不是输入上限。[agents/utils.py L34–49](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/utils.py#L34-L49)，[llm.py L174–210](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/llm.py#L174-L210)，[llm.py L406–443](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/llm.py#L406-L443)

### 尚未查明的下层边界

- 已核模板渲染器本身只是Jinja render；未逐一读取benchmark选定模板正文，因此不能排除某份模板自行切片，也不能把所有配置都断言为同样输入长度。[ctxopt/base.py L109–123](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/base.py#L109-L123)
- 未逐项追查AppWorld/OfficeBench工具或环境是否已截断返回；这里的“完整observation”只指压缩器函数收到的值，不能保证等于外部原文。
- 未验证远端服务、所有本地推理后端的超窗处理，也未实跑一次超大输入。当前能确认的是这条Python调用链没有通用的预分块保证。
- 仓库还定义V2 optimizer，将raw_history复制后追加压缩指令；但本次读取的`MemoryManager`实际选择的是V1类，不能因为有V2文件就说默认流程已用它。[memory.py L50–58](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/memory.py#L50-L58)，[HistoryOptimizerV2 L302–325](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/history_optimizer.py#L302-L325)

## 哪些角色被压，原文能否回来

**固定源码静态核对**：该实现把环境反馈放在`user`消息；history压缩不是只遮旧tool output，而是对旧assistant/user内容一起做摘要。最近k个assistant-user对保留，代码默认k=1；system和首个任务user消息不进入旧history文本，任务另外传入。它不是直接适用于原生`role=tool`日志的通用转换器。[memory.py L246–318、L386–418](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/memory.py#L246-L418)

**固定源码静态核对**：summary可选择reset或accumulate；代码默认accumulate，会把新summary追加到已有首user内容后，不应假定累计摘要永远固定大小。生成后调用`start_new_session`，重新加入system、任务/summary和尾部消息。[memory.py L31–47](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/memory.py#L31-L47)，[memory.py L443–498](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/memory.py#L443-L498)

**固定源码静态核对**：旧session与压缩调用的prompt/response/prompt_args会留在对象里，`dump_history`可输出会话与optimizer日志。所以“从下一轮上下文删除”不等于“宿主完全丢失”；但已读主链没有向Agent提供按引用取回原始被压片段的工具，落日志也不等于Agent可随时回读。[memory.py L199–226](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/agents/memory.py#L199-L226)，[base.py L157–166](https://github.com/microsoft/acon/blob/d63f9ae18959dc7215ff62899c94c5e8c56847ae/src/productive_agents/ctxopt/base.py#L157-L166)

## 阈值与消融究竟说明了什么

**论文声明，未复现**：AppWorld阈值分析中，history 4096、observation 1024是作者报告的较佳折中；更低阈值增加压缩频率并伤害准确率。这是论文配置/消融结果，不是类构造器的默认硬上限（源码缺省阈值为-1）。[ACON §4.5](https://arxiv.org/html/2510.00615v1#S4.SS5)

**论文实验报告**：Table 3比较的是AppWorld里压缩guideline优化配置，o3配对照反馈51.2，不用对照反馈50.6；它支持这一设置中的guideline优化选择，不证明任何摘要都优于完整证据，也不证明离线Skill学习改善。论文还报告：更强压缩阶段可能牺牲准确率，history压缩由于额外模型调用和KV-cache影响，未必降低实际API费用。[ACON Table 3及成本讨论](https://arxiv.org/html/2510.00615v1#S4.SS5)

ACON另有离线优化guideline和蒸馏compressor/agent的阶段，但运行时被优化的对象仍是后续动作所需上下文；不能因此把它称为跨任务经验抽取或Skill演化机制。对我们来说，runtime执行成功率和offline经验提炼的可核验性需要分别讨论。

## Context-Folding：只作两句对照

**固定源码静态核对**：正常branch路径复制父上下文，分支自己运行，return后父分支只得到回传message，子过程仍在`agents/session_message`中保留；这是缩小父上下文，不是先将摘要生成器输入切成任意小块。[fold_agent_loop.py L472–515](https://github.com/MiaoLu3/Context_Folding/blob/81626e97bb5f4eaa79edca045528829ce8850f5b/verl/experimental/agent_loop/FoldAgent/fold_agent_loop.py#L472-L515)

分支达到`branch_len`等预算时被提示return，可选session-summary路径在response预算95%时另行摘要；这仍属于运行时管理，不能据此宣称已提供Agent可寻址的原文回查，或已经验证离线经验学习受益。[分支边界L836–899](https://github.com/MiaoLu3/Context_Folding/blob/81626e97bb5f4eaa79edca045528829ce8850f5b/verl/experimental/agent_loop/FoldAgent/fold_agent_loop.py#L836-L899)，[可选summary L410–445](https://github.com/MiaoLu3/Context_Folding/blob/81626e97bb5f4eaa79edca045528829ce8850f5b/verl/experimental/agent_loop/FoldAgent/fold_agent_loop.py#L410-L445)

## 简短反证：The Complexity Trap

**论文v1实验报告，未复现**：研究范围是SWE-agent、SWE-bench Verified、五种模型配置。Observation Masking保留动作/推理，只用占位符替换窗口外旧observation；这不是永久删除原始日志，也不是把整段轨迹变成摘要。其Qwen3-Coder 480B结果为masking 54.8% / $0.61，LLM-summary 53.8% / $0.64；不能把小差距未经统计分析写成显著胜出。[方法§3与Table 1](https://arxiv.org/html/2508.21433v1)

同表的Gemini 2.5 Flash thinking配置中，原轨迹40.4%，masking36.4%，summary31.4%：压缩并不保证提高解题率。论文只在特定编码任务/脚手架和启发式触发条件下比较，不能据此认为ERP取证或离线经验提炼也应删除旧工具结果；“摘要掩盖失败信号导致拖长轨迹”是作者提出的机制解释，不能替代对我们日志的验证。[Table 1、§4.4、§5.3](https://arxiv.org/html/2508.21433v1)

## 本项目的讨论边界

**我们的推断，尚未实验**：需要分别约束①环境返回多大，②压缩器实际读多少，③摘要/分层表示多大，④后续Actor或Teacher能否回取证据。仅在③做结构化，不会自动解决②；仅改善runtime成本，也不能认证摘要适合作为之后归因和Skill生成的事实依据。

本轮没有据此提出新的实现约束。保留原始可追查材料、给压缩输入明确预算、区分原始事实与摘要、再比较对执行与经验提炼的影响，是需要继续讨论的选择；两篇方法及反证都没有直接证明哪种选择对当前GDPevo会更好。
