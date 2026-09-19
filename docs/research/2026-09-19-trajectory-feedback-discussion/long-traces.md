# 长轨迹怎样进入学习：ReasoningBank 与 SkillFlow

核验日期：2026-09-19。结论置信度：高，限于以下论文版本与冻结实现；没有复现实验。**这两篇没有统一采用“让学习器读取完整原始轨迹”：ReasoningBank 网页分支使用显式 think/action 表示，SWE 分支拼接已保存消息；SkillFlow 先按位置与字符裁剪。所查学习调用均没有按需回读原轨迹的工具循环。**

本次只回答三个问题：学习模型实际看到什么；丢失信息能否补读、任务边界在哪里；哪些实验与局限支持或限制这些选择。旧 references 仅用作入口，本次重新打开原文和冻结源码。没有重新下载此前被拒的 SkillFlow 任务数据，没有改产品、提示词或 HTML，也没有调用模型。

证据标签：**【源码级】**冻结代码的静态数据流；**【原文级】**作者声明；**【实验级】**作者报告而非本次复现；**【推断级】**我们的机制判断。没有把源码存在等同于本机跑通。

| 对象 | 本次核验的版本与入口 |
| --- | --- |
| ReasoningBank | [论文 v2](https://arxiv.org/html/2509.25140v2)，2026-03-16；[源码 ed80611788292ea739f1effd31f16c53823b8a0d](https://github.com/google-research/reasoning-bank/tree/ed80611788292ea739f1effd31f16c53823b8a0d)。现存只读 checkout 的 HEAD 与此相同，工作树干净；重新读取下列函数。不是声称该 commit 是最新 HEAD。 |
| SkillFlow | [论文 v1 PDF](https://arxiv.org/pdf/2604.17308v1)，2026-04-19，另核对 [HTML](https://arxiv.org/html/2604.17308)；[源码 7b49ff5a7e26cd7706e959bfa0dba4746d18440d](https://github.com/ZhangZi-a/SkillFlow/tree/7b49ff5a7e26cd7706e959bfa0dba4746d18440d)。本次直接打开该 commit 的 raw 文件。 |

## 1. 先区分三种不同的上下文

| 环节 | 要回答的问题 | 不能混用的证据 |
| --- | --- | --- |
| 当前 Actor 做题 | 当前目标、工具返回、已有记忆如何供给执行器？ | Actor 能搜索文件，不代表事后提炼器也能搜索原轨迹。 |
| 事后提炼器学习 | 当前经历、结果、失败细节、旧经验具体以何种表示进入新调用？ | 论文写 trajectory，不代表全部页面、原工具输出或原生私有推理均进入调用。 |
| 下一题复用 | 应注入原历史还是提炼后的条目/Skill？ | 复用时少量记忆更有效，不直接证明提炼时少看原证据更有效。 |

下面分别核对这些接口；不将“提炼之后的记忆很短”写成“提炼器先读了一个可靠摘要”。

## 2. ReasoningBank：不同分支实际读的内容不同

### 2.1 网页：保留行动序列，用 Actor 的显式文本代替大量 observation

【原文级】§3.1 脚注明确用 Actor 的 thinking 近似冗长网页 observation；并非先由另一个压缩模型无损总结全部页面。§3.2 结束一题后以任务和轨迹取得 proxy 标签，再提炼经验。[论文 §3.1–3.2](https://arxiv.org/html/2509.25140v2#S3)

【源码级】`WebArena/induce_memory.py::extract_think_and_action()` 按 step 文件顺序读取全部**有 action 且能解析**的步骤，提取 `think/action`；`format_trajectory()` 串成一个文本。`main()` 加用户 intent，并在 autoeval 模式下附 judge 理由，单次调用成功或失败提示词。这里没有把原始 `axtree_txt` 传给记忆提炼模型，也没有逐片段补读协议。[induce_memory.py L47–186](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/induce_memory.py#L47)

【源码级】judge 的输入另有真实页面：`autoeval/evaluate_trajectory.py` 为有 action 的步骤读取 axtree，每份最多前 **40,000 字符**，没有时回退到 think；`Evaluator.eval_text()` 给全部 think/action，再给最后最多 **5** 份页面文本和最终回复。因此，judge 看到的证据比 extractor 多，但也不是所有完整页面。跳过无 action 步骤意味着这里不能保证包含独立的最终环境快照。[页面抽取 L45–149](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/autoeval/evaluate_trajectory.py#L45)、[judge 组装 L70–98](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/autoeval/evaluator.py#L70)

这里的 think 是 `agent_info` 或可见输出中保存的显式字段，不是取得服务商未暴露的内部推理。该表示会保留 Actor 认为重要的解释和动作，但可能丢失 Actor 当时没提到的数值、失败前状态和反证；后一点是【推断级】的信息损失风险，不是本次测得的错误率。[字段回退逻辑 L27–42](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/autoeval/evaluate_trajectory.py#L27)

### 2.2 SWE：全部已保存的非 system 消息，但工具结果事先已裁剪

【源码级】`process_instance()` 读取保存的 `.traj.json`，将所有非 system 消息的 `content` 按序连接；同一文本用于 `llm_judge_status()` 和经验提炼。没有在提炼前再做按相关性选步或模型摘要；system 中的旧记忆被排除，原消息 role 也没有在拼接字符串中重新标注。[swebench.py L227–263](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/run/extra/swebench.py#L227)

【源码级】这仍不等于全部原始命令输出：`DefaultAgent.get_observation()` 保存的是模板渲染后的 observation；SWE 配置在单次输出达到 **10,000 字符**时只保留前后各 **5,000** 字符，标出省略长度。模板建议 Actor 用 `head/tail/sed` 或更精确搜索重查。**这是做题阶段可以重新操作环境，不是提炼器回读已省略证据。**[get_observation L104–109](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/agents/default.py#L104)、[输出模板 L172–196](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/config/extra/swebench.yaml#L172)

### 2.3 提炼产物、多个轨迹与边界

【源码级】网页成功/失败提示词都要求最多 3 个 `Title / Description / Content` 条目；Description 说明何时适用或不适用，Content 为简短可执行经验，避免抄产品名等实例内容。它约束的是**最终经验**，不提供原文定位、引用校验或缺证补读。写回是直接追加 JSONL，不是独立验证后晋升。[memory_instruction.py L15–60](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/prompts/memory_instruction.py#L15)、[追加位置](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/induce_memory.py#L176)

【原文级】MaTTS parallel 把同一 query 的多条轨迹一起比较，sequential 在同一任务内继续检查；这是增加经历/对照信息，不是设计了一个只查缺失片段的索引器。基础流程仍可从单轨迹提炼，不能把所有 ReasoningBank 实验都描述为多轨迹归因。[§3.3 / Appendix A.3](https://arxiv.org/html/2509.25140v2#S3.S3)

【源码级】网页流水线以已知 task ID 为单位顺序执行、judge、extract，按网站保存记忆；SWE 从 `problem_statement` 开始独立 run。检索根据当前任务找相似的既往 experience，取其已提炼 items。所查路径没有从任意长会话推断 A→B→A 目标修订的逻辑。[pipeline_memory.py L47–85](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/pipeline_memory.py#L47)、[select_memory](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/memory_management.py#L138)、[SWE task 入口](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/run/extra/swebench.py#L161)

## 3. SkillFlow：固定裁剪后的单次补丁生成

### 3.1 真正的输入变换

【源码级】`TrajectoryCompactor.compact()` 处理 ATIF，策略是首步 + 最近 `N−1` 步，并非选出因果相关片段或先让模型总结。`CompactionConfig` 默认 N=20，而 runner 命令行默认 N=60；不能把前者写成所有实际实验的配置。[compactor](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L90)、[CLI 配置 L842–860](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L842)

该 compactor 的保留/损失如下；数字均为**字符或步数**，不是 token：

| 字段 | 实际处理 |
| --- | --- |
| agent message | 所选 agent 步骤的非占位正文保留，未见该字段的总长度裁剪。 |
| 工具参数 | 字符串只保留前 100 字符；数字/布尔保留；嵌套 dict/list 只留下类型与数量。 |
| 工具返回 | 所选 agent 步骤的 `observation.results`，每项默认取前 3,000 字符并标截断。 |
| user 要求 | 虽保留首步位置，却只为 `source == agent` 复制正文；普通 user 首步只剩 source，任务正文未被该分支保留。 |
| 其他 | step 的度量、ID等未进入此投影；丢掉的中间步骤没有回读引用。 |

[同一转换函数 L106–170](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L106)。这是确定性字段裁剪，不能称为已经保留完整任务约束的“结构化摘要”。agent message、结果数量及旧库大小仍可增长，局部上限也不等于严格的总输入预算。

【源码级】runner 在 trial 结束后组装任务名/来源、reward、异常、失败测试名、精简轨迹及当前 Skill 文件快照，再 `generate_patch()`；然后应用文件补丁供下一 trial 使用。提供评分信息不等于提供了全部原始 verifier 诊断；本轮未访问另发的任务数据，不能进一步声称核验了每项任务评分器。[on_trial_ended_hook_sync L580–670](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L580)

### 3.2 fallback 不是补读

【源码级】连接/超时等错误可触发更小 prompt：旧库前 8 文件、每文件前 4,000 字符，轨迹首 2 + 尾 6 步，序列化轨迹最多 12,000 字符，最终消息最多 2,000 字符。解析重试也没有增加新原证据。所谓 full 模式已经读取的是 compacted trajectory，不是未损失的 raw trace。[`_build_user_prompt` / `generate_patch`](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L619)

提示词的 progressive disclosure 是要求**生成的 Skill**把长资料放到 `references/`，让未来执行器按需读取；不能把它当成学习器按需展开本次原轨迹的实现。[SYSTEM_PROMPT L313–335](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L313)

### 3.3 已知任务族边界，不处理混杂日常会话

【原文级】同族任务按难度顺序执行，从空库开始，每题后更新，换 family 重置。论文主动不评估不同工作流交错时的精准 Skill 选择。【源码级】`build_group_job_config()` 固定任务列表、同组串行，目录按 group 隔离；可并行的是不同 group。[论文 §2.4](https://arxiv.org/html/2604.17308#S2.S4)、[runner L424–499](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L424)

因此它适合研究同类流程的连续变体；没有直接解决用户在同一 session 多次更改目标时，旧失败应绑定哪个要求的问题。将后者加入产品是我们自己的问题定义，不能说“照论文已经解决”。

## 4. 负结果和不能推出的结论

| 证据 | 实际支持什么 | 不支持什么 |
| --- | --- | --- |
| 【实验级】ReasoningBank，WebArena-Shopping / Gemini-2.5-flash：检索 1/2/3/4 个 experience，SR 为 49.7/46.0/45.5/44.4。[Appendix C.1](https://arxiv.org/html/2509.25140v2) | 下一题注入更多记忆可能有害。 | 不能推出提炼器应少看原始证据，更不能证明按位置裁剪最优。 |
| 【原文级】ReasoningBank 承认 judge 会出错，检索/追加策略简单。[Appendix E](https://arxiv.org/html/2509.25140v2) | 写出经验不等于标签或归因真实；本次未发现基本 ReasoningBank 整体退化的主实验结论。 | 不能把模型判 success 当独立真实反馈，也不能说已解决长期冲突/淘汰。 |
| 【实验级】SkillFlow，GPT-5.3-Codex：52.41%→46.39%；Sonnet 4.6 完成率持平但所报成本上升。[Table 1](https://arxiv.org/html/2604.17308#S3) | 会写、会读 Skill 仍可能退化或不划算。 | 不能归因这些回归一定来自轨迹裁剪；没有该变量的独立消融。 |
| 【实验级，数值冲突】SkillFlow 原历史上下文对照：§3.3 / Table 6 为 51.04%，Appendix C.2 却为 47.41%；HTML 与 PDF 均如此。[PDF p.8、22、25](https://arxiv.org/pdf/2604.17308v1) | 两处都报告该单模型 raw-history 对照弱于基线；具体差值应待作者澄清。 | 这是给下一任务 Actor 历史的实验，不是提炼输入“完整 vs 压缩”的消融；不能据此认证当前 compactor。 |

## 5. 对当前讨论的有限启示

【推断级】两篇支持“经历经提炼后复用”的路线，但没有给出一套被证明最优的长轨迹取证方法，也没有证明我们当前的几段证据足够归因。它们减少上下文负担的方式各有明确损失；不宜把任一种裁剪直接奉为标准答案。

当前需要先讨论的是：学习单元能否按已知 task/revision 划定；哪些原要求、反馈、动作与返回构成可重算的证据链；不足时是补读、保留假设还是暂不形成规则。尤其在数据计算任务中，“类别都看见一些”与“同一个对象的输入到产物能对上”是两种不同的完整性。这是我们的设计判断，并非两篇已完成的实验结论。

若以后做对照，应固定同一源经历与反馈，分别比较完整可容纳的单任务表示、位置裁剪、按关联证据补读；评价提炼的具体性、错误归因、下次任务效果及总维护成本。此处仅列讨论方向，不实施新方案、不追加模型实验。
