# Coding Agent 的反馈究竟从哪里来：ReasoningBank 与 Reflexion

核验日期：2026-09-18。结论置信度：高，限于下列论文版本和冻结源码；没有运行模型或复现实验。

**一次 LLM 调用可以参与判断或反思，但它的输入不是孤立的“是否通过”。** 两个系统都把任务、执行记录和反馈组合起来。区别在于：ReasoningBank 用 LLM 根据执行证据生成 correctness proxy，再把成功/失败经验写入跨任务记忆；Reflexion 编程分支首先真实执行测试，然后让 LLM 根据代码、失败断言及实际输出解释错误，主要服务于同一任务的下一轮尝试。[ReasoningBank SWE 实现][RB-SWE]、[Reflexion 主循环][RF-RUN]

本次仅回答三个问题：没有标准答案时如何形成反馈；从轨迹到可操作经验具体经过哪些调用；这些证据能证明到哪一层。一个需要排除的假设是“反思器收到一个布尔值就能定位错误”：布尔值只能触发、停止或选择提示词，错误定位需要额外的执行证据，仍可能定位错。

取证版本：

- ReasoningBank：[arXiv 2509.25140v2，2026-03-16][RB-PAPER]；官方 [google-research/reasoning-bank][RB-REPO]，commit `ed80611788292ea739f1effd31f16c53823b8a0d`（2026-05-18）。初版论文里的观测近似与当前开源实现不完全相同，以下分别标记。
- Reflexion：[arXiv 2303.11366v4，2023-10-10][RF-PAPER]；官方仓库当前为 [noahshinn/reflexion][RF-REPO]，commit `218cf0ef1df84b05ce379dd4a8e47f17766733a0`（2025-01-13）。论文旧链接使用 `noahshinn024`，当前已不可直接克隆。公开代码和论文的若干配置也不相同。
- 证据标签：【源码级】调用和数据流已静态核验；【实验级】作者报告的测量，未在本次复现；【推断级】从上述机制得到的解释或工程判断。没有增加第三篇论文；这两篇的一手材料已足以回答问题。按任务边界，只保存本地文档，不上传分析或更新远端记忆。

## 1. ReasoningBank：task → observed trace → feedback source → diagnosis → memory update

### Task

网页任务输入是用户 intent；SWE 输入是 `instance["problem_statement"]`。开始当前任务时，用任务文本检索过去经验，取最相似的一个 experience，把它包含的 memory items 加进 actor 的 system prompt。这里的 top-1 是一个过去的 experience，可以带多个 item，不是仅一条记忆。[网页检索][RB-WEB-RUN]、[SWE runner][RB-SWE]

### Observed trace：judge 与 extractor 并没有拿到完全相同的上下文

| 分支 | 实际提供给 judge 的证据 | 截断或信息损失 | extractor 另一次调用看到什么 |
|---|---|---|---|
| 当前 WebArena text 路径 | intent；按顺序组合的全部 `think/action`；最后最多 5 个有 action 的 step 的 `axtree_txt`；最终 `send_msg_to_user` 回复 | 每份页面文本只保留前 40,000 **字符**；没有 axtree 时回退到 think；无 action 的 step 被跳过，所以“最后页面”不保证等于独立抓取的任务终态 | intent + 全部提取到的 `think/action`，并追加 judge 的 `thoughts`。它不直接接收这些原始 axtree |
| 当前 SWE 路径 | task + 保存的全部非 system 消息，按顺序直接拼接 content | 不是 raw shell 全量日志；actor 的单次命令输出达到 10,000 字符时，模板保留前/后各 5,000 字符和省略长度。拼接时没有重新保留消息 role 字段；原 system prompt，包括已检索记忆，被过滤 | 同样的 task + 非 system 消息轨迹；通过成功/失败两套 system instruction 传入分类结果，未额外传 judge 理由 |

【源码级】网页来源是 `autoeval.evaluate_trajectory.extract_think_and_action()` 与 `Evaluator.eval_text()`。提炼记忆走另一个 `induce_memory.extract_think_and_action()`，后者只提取 think/action。[网页证据提取][RB-WEB-TRACE]、[judge 组装][RB-WEB-EVAL]、[memory 提炼][RB-WEB-INDUCE]。SWE 来源是 `process_instance()` 保存 `.traj.json` 后的处理；`DefaultAgent.get_observation()` 把真实命令结果写回 user observation；输出裁剪由 YAML 模板实施。[SWE 主循环][RB-SWE]、[消息记录][RB-AGENT]、[输出裁剪][RB-SWE-CONFIG]

这里的 `think` 是框架能保存的显式输出字段：代码先读 `agent_info["think"]`，没有时尝试读取可见 `chat_messages` 中 `<action>` 之前的文本。SWE 的 `THOUGHT` 同样是正文格式要求。**它们不是对模型私有、未暴露推理过程的访问能力。**给原生 Coding Agent 接这类机制时，只能承诺利用实际可取得的消息、工具调用和返回值，不能把“trajectory”默认为包含不可得的内部推理。[字段提取][RB-WEB-TRACE]、[SWE 正文格式][RB-SWE-THOUGHT]

这也解释了“轨迹”一词容易造成的误解：论文 §3.1 对网页长 observation 使用 agent thinking 作为近似；当前代码已经让 judge 读真实 accessibility tree，但网页 extractor 仍主要依赖 actor 自述和 judge 的文字结论。不能把论文的逻辑图概括成“所有原始工具输入输出原封不动送给每一个模型”。[论文 §3.1][RB-PAPER]、[当前网页数据流][RB-WEB-TRACE]

### Feedback source：无 gold 分类，不代表没有环境证据

网页 `build_text_eval_prompt()` 的真实输入槽位包括 `User Intent`、`Action History`、页面状态、bot response。当前 system prompt 要求核对三件事：约束是否完整满足；答案里的值是否能追溯到 observation；是否作用于正确对象。遇到不确定应标 failure。输出包含 `Thoughts:` 和 `Status:` 两行，不只是布尔值。[真实提示词][RB-WEB-PROMPT]

SWE 的真实函数 `llm_judge_status(task, trajectory, model)` 更简单，其末尾要求：

> Did the agent successfully complete the task? Answer with 'success' or 'fail' only.

但这句前面是 task 和整个上述消息轨迹。它用同一个 `model.config.model_name`，temperature 0；没有执行额外检查的 tool。若 actor 在轨迹里运行过复现脚本、仓库测试或读取过报错，这些是 judge 可以用的环境事实；若没有，它不会凭这次调用自动取得隐藏测试结果。[`llm_judge_status`][RB-SWE]

【源码级】网页默认 `--judge autoeval` 使用 `rm`；另有显式 `gt` 分支读取 `summary_info.json` 的 `cum_reward`。autoeval 记录同时保存 `gt` 和 `rm`，但 `gt` 不进入 `build_text_eval_prompt()`。SWE 的记忆提炼也没有调用 SWE-bench 官方判分器，而是立即对消息轨迹 self-judge。因此，作者最后报告的 benchmark resolve rate 与在线 memory induction 使用的标签，是两条不同的数据流。[网页流水线][RB-PIPELINE]、[autoeval 保存字段][RB-WEB-TRACE]、[SWE runner][RB-SWE]

### Diagnosis：换调用和提示词，不是换成一个具有额外真相的模型

actor、judge、extractor 使用同一 backbone/model 名称，但运行在重新构造的调用上下文中。judge temperature 0；extractor temperature 1。成功标签选择 `SUCCESSFUL_SI`，要求解释成功策略；失败标签选择 `FAILED_SI`，要求解释失败并提炼避免重犯的措施。当前 WebArena extractor 还收到 judge 的一句或几句理由；SWE 只通过不同 system instruction 告知成功/失败。[网页流水线][RB-PIPELINE]、[网页提炼器][RB-WEB-INDUCE]、[SWE runner][RB-SWE]

真实 `FAILED_SI` 要求先想失败原因，再给至多 3 个条目；每项包含 `Title / Description / Content`。当前网页版本的 Description 特别要求说明何时或何时不适用；Content 为 1–3 句具体恢复步骤，避免复制产品名等偶然细节。**从 failure 到“哪一步导致失败”是 LLM 的归因，不是布尔标签直接提供的事实，也不是执行了所建议的反事实路径。**[网页 extraction prompt][RB-MEM-PROMPT]、[SWE extraction prompt][RB-SWE-INSTRUCTION]

### Memory update：append，然后供下一道任务检索

新 experience 直接追加 JSONL，网页记录 query、think/action、status、memory items 等；当前 SWE 记录 task id、query、memory items、status。没有看到基于再次执行验证后才入库的门槛，也没有条目级合并/删除流程。下一任务按 query embedding 的相似度取过去 experience，再把其 items 注入 system prompt。**更新的是外部文本上下文，不是模型权重；作者描述的经验逐渐发展，也不应理解成有一个已实现的原位条目进化控制器。**[网页 append][RB-WEB-INDUCE]、[相似度检索][RB-MEMORY]、[actor 注入位置][RB-WEB-ACTOR]、[SWE append/inject][RB-SWE]

可核验案例是论文 Figure 17：用户要 Sony 蓝牙耳机完整名称和价格范围；搜索结果含大量无关商品，agent 持续翻页直到耗尽交互额度；图中据此归因为查询不精确和导航低效；提炼的措施是优化查询、调整每页数量、使用过滤器。这是从执行模式到操作建议的例子。**该图没有展示这些措施重放后的成功轨迹，也没有给出逐字 judge 响应，不能把它当成反事实原因已验证的证据。**[公开原图][RB-CASE]

## 2. Reflexion 编程：task → observed trace → feedback source → diagnosis → memory update

### Task

给函数签名、docstring/自然语言规格；`run_reflexion()` 先生成内部测试，再生成第一版实现。当前代码在一般编程任务调用 `gen.internal_tests(item["prompt"], model, 1)`；LeetCode 分支则读取公开的 `visible_tests`。测试生成器只根据规格生成，不接收当前实现，也不接收隐藏 `item["test"]`。[主循环][RF-RUN]、[测试生成上下文][RF-GENERATOR]

### Observed trace

这里主要不是开放式 repo agent 的几十轮 bash 日志，而是“当前函数实现 + 针对这个实现的测试结果”。`PyExecutor.execute()` 真实运行每条断言，构造通过测试列表、失败测试列表；失败项带 `# output: ...`，可能是实际返回值、`TIMEOUT` 或异常文本。`RsExecutor.execute()` 先跑 `cargo check`；有编译错误就返回错误文本，否则逐个运行测试，并返回运行错误。**仅给反思器一个 `False` 的概述漏掉了这里最关键的信息。**[Python 执行器][RF-PY-EXEC]、[Rust 执行器][RF-RS-EXEC]

测试生成使用 AST/语法有效性过滤，再从有效候选采样；语法过滤不保证期望值正确，也不保证边界覆盖充分。论文描述最多 6 个内部测试；冻结源码的上述调用实际上最多取 1 个，不能把两者当完全相同的复现设置。[测试过滤函数][RF-GENERATOR]、[论文 §4.3][RF-PAPER]

### Feedback source

`is_passing` 来自程序执行，不是 LLM 看代码后说“感觉正确”。不过，内部测试的预期答案通常由模型自己提出，因此“执行是真实的”和“判断标准是真实完整的”仍是两回事。[`execute`][RF-PY-EXEC]

隐藏 benchmark tests 在 `exe.evaluate(entry_point, implementation, item["test"])` 才使用。对于论文及 CLI 默认的 `pass_at_k=1`，这是内部测试全过或修复预算耗尽后的评分，隐藏测试文本、失败项不送给 reflector；若内部测试误放行，代码会结束这次尝试，不能期待 hidden-test failure 再提供一次修复机会。该 harness 的确持有标准答案测试；严谨说法是“修复循环不读取隐藏测试”，而不是“整个实验不存在 gold”。泛化到 `pass_at_k>1` 时还要重新核对外层采样停止逻辑，不能直接沿用这句话。[主循环 L33–91][RF-RUN]、[CLI 默认值][RF-MAIN]

### Diagnosis

真实函数 `generic_generate_self_reflection()` 构造一个新消息列表：system instruction + few-shot + `[function impl]` + `[unit test results]` + `[self-reflection]`。它看到当前完整实现和结构化为文本的测试结果；不是复用 actor 所有过往隐含上下文。独立的原始 task 参数没有传给这个函数，规格能否被看到取决于实现中是否带签名/docstring。actor、test generator、reflector 共享 `run_reflexion()` 中创建的同一个 model 对象；evaluator 则是执行器，不是第三个独立 LLM。[反思上下文构造][RF-GENERATOR]、[模型初始化和调用][RF-RUN]

`PY_SELF_REFLECTION_CHAT_INSTRUCTION` 要求解释为什么实现违背测试，并产生供下一次使用的几句提示。下一次 `generic_generate_func_impl(strategy="reflexion")` 收到上次实现、测试反馈、最新反思，以及原始函数任务，输出修正版代码。[真实 Python 提示词][RF-PY-PROMPT]、[actor 消费反思的消息顺序][RF-GENERATOR]

### Memory update

同一任务继续使用这组内部测试。所有 reflections 被保存到日志，但传给下次 actor 的是当前最新 `reflection`；下一条 dataset item 开始时，`reflections/implementations/test_feedback` 重置。**这个编程实现提供的是任务内重试经验，不是后一个新任务检索前一个任务经验的系统。**这不否定它能改善同题修复，但不能直接作为跨项目、跨任务持续学习的实验证据。[`run_reflexion` L26–98][RF-RUN]

可核验的真实记录：官方 HumanEval 日志第 2 行为 `HumanEval/1`，任务是把多个括号组分开并忽略空格；保留的反思说旧实现把嵌套括号误拆成独立组；最终代码用栈追踪括号闭合，仅在栈为空时输出一组；记录 `is_solved: true`。这能核对“具体错误描述 → 改变判定条件的实现 → 作者记录成功”。**这份旧日志没有保存失败实现或逐项测试反馈，所以不能从它声称某个具体失败输入已在该轮观测到。**[官方结果 JSONL 第 2 行][RF-LOG]

## 3. Reflexion 其他实验不能全归成“无 gold 的自评”

| 环境 | success/failure 从哪来 | reflector 实际可见内容与裁剪 | 记忆消费边界 |
|---|---|---|---|
| HotpotQA | `EM(answer, key)` 使用 gold answer 得到 correct/incorrect；Search/Lookup 返回维基文本 | question + Thought/Action/Observation scratchpad + 反思示例；`truncate_scratchpad()` 默认压至 1,600 token，优先把最长 Observation 替换为截断标记，保留其他轨迹文字；actor prompt 超 3,896 token 或超步数会 halt | 新 trial 重置 scratchpad，把已有反思放进同一问题的 prompt；当前 React 默认 actor/reflector 都是 gpt-3.5-turbo，但分别构造调用 |
| ALFWorld | 环境完成信号加失败启发式；不是只有一个 LLM 凭空判断世界状态 | 失败任务的文本行动和环境 observation，外加这个环境此前最多 3 条 plan。`_get_scenario()` 去掉任务之前的 few-shot 前缀；反思提示明确面向同一任务的下次尝试 | per-environment 保存 plan，reset 环境后重试这个任务；actor 只注入最近 3 条 |

[HotpotQA 环境判分][RF-QA-ENV]、[ReactReflectAgent/截断][RF-QA-AGENT]、[ALFWorld reflection prompt][RF-ALF-REFLECT]、[历史注入][RF-ALF-HISTORY]

配置差异也需保留：论文 ALFWorld 失败启发式描述为相同 action/response 超过 3 轮或 action 超 30；当前开源 `alfworld_run()` 上限是 49 轮，`EnvironmentHistory` 在重复同一 action 后即 exhausted，且 `done` 会直接触发成功返回（代码读取了 `info['won']`，但这个返回分支用的是 `done`）。这不是在本次验证其环境 API 的全部语义，而是提醒不能把论文阈值抄成当前代码事实。[当前 ALFWorld 控制流][RF-ALF-RUN]、[exhausted 实现][RF-ALF-HISTORY]

## 4. 任务内重试与跨任务学习要分开计数

| 机制 | 增加了什么经验 | 新经验先帮助谁 | 是否改模型参数 |
|---|---|---|---|
| Reflexion 编程重试 | 同一规格下新实现、真实测试结果、反思 | 同一题的下一版实现 | 否 |
| ReasoningBank 常规任务流 | 当前题结束后的成功/失败经验条目 | 之后检索到它的不同任务 | 否 |
| ReasoningBank MaTTS parallel（论文） | 同一题多条独立轨迹，比较异同后提炼 | 当前题的候选选择及之后任务的记忆 | 否 |
| ReasoningBank MaTTS sequential（论文） | 初次完成后继续 re-check，增加纠正/确认片段 | 当前题后续检查及之后任务的记忆 | 否 |

MaTTS 的附加反馈依然可能只是多条 self-generated 轨迹的相互一致或分歧；相互一致不能自动升格为 correctness oracle。此处引用的是论文机制和公开提示词，**未把开源 scaling 脚本视为已经执行验证的完整复现**。[MaTTS 论文 §3.3/A.3][RB-PAPER]、[parallel/sequential 提示词][RB-MEM-PROMPT]

## 5. 正、负结果和 proxy 的边界

| 【实验级，作者报告】 | 能支持什么 | 不能支持什么 |
|---|---|---|
| ReasoningBank v2：WebArena-Shopping 上 Gemini-2.5-flash judge 对 gold 的准确率 72.7%；模拟 70%–90% 标签准确率时任务成绩接近，100% 最好 | 这组记忆管线可容忍一定标签噪声 | 单条 self-judged success 可信；真实误差分布等同随机翻转；所有 coding 场景同样稳健 |
| ReasoningBank：检索 1/2/3/4 个 experience，SR 为 49.7/46.0/45.5/44.4 | 记忆量增加可能伤害效果 | 越多经验越好 |
| Reflexion：MBPP Python 77.1%，基线 80.1%；内部测试全过但最终不正确的比例报告为 16.3%，HumanEval Python 为 1.4% | 自写测试会误放行，导致提前停止 | 跑过自写测试就证明功能正确 |
| Reflexion：HumanEval Rust hardest-50 消融，完整方法 68%，去掉测试生成 52%，基线 60%，去掉反思 60% | 在这组问题上，缺少测试反馈的自我修改可能有害；反馈与诊断各有贡献 | 任意自然语言反思都有效，或单纯重复更多轮就可靠提升 |

[ReasoningBank v2 §5/C.1][RB-PAPER]、[Reflexion §4.3 Tables 1–3][RF-PAPER]。这些是已知有 gold 的评测环境中测到的最终效果；部署时自己给出的标签不等于这套外部测量。

还有一条更细的【文本证据级】反例：Reflexion 附录 D.1 的第一轮把演员查错为 Gorden Kaye，返回 Rene Artois；第二轮改查 Sam Kelly，返回 Captain Hans Geering，环境标 correct。但是该例打印的 reflection 仍建议查 Gorden Kaye，和成功重试不一致。**这份展示本身不足以证明反思完成了正确因果诊断，不能因为下一轮成功就倒推它的解释正确。**[附录 D.1 完整轨迹][RF-PAPER]

当前源码还提供两种【推断级】边界：SWE `llm_judge_status` 用子串 `"success" in response` 解析标签；网页 autoeval 异常可生成 `rm=None`，而 induction 对非 1 值走 failure 分支。它们说明 label 还可能混入输出解析或执行设施的问题。这里只指出代码可发生的路径，没有声称它们造成了作者的测量结果。[SWE 标签解析][RB-SWE]、[autoeval 异常][RB-WEB-TRACE]、[标签分流][RB-WEB-INDUCE]

## 6. 对“原生 Coding Agent 从轨迹学习”的直接回答

可以从已完成的 coding session 构造反馈，但需要保留这条因果链：**任务约束 → 实际读写/命令及其结果 → 对照什么标准判定 → 哪个失败模式被证据支持 → 下次在何种条件下采取什么动作。**前两部分是观测，第三部分区分真实判分器与模型 proxy，第四部分是诊断假说，第五部分是待复用策略。这是从上述实现得到的【推断级】建议，不是某篇论文已经验证的通用产品协议。

没有 gold 时仍可能有很硬的局部事实：命令不存在、编译失败、返回值与公开示例不符、测试输出显示哪条断言失败。也可能只有软证据：agent 自称完成、judge 认为方案合理、两个同模型轨迹达成一致。硬的局部事实不足以证明整个需求正确，软证据也不足以验证反事实修复建议。若完整性没有观测依据，应保存“不确定/仅局部验证”的边界，而不是让 success 标签把它抹平。

因此，合理的口头回答是：**“把本次任务和可核查的执行片段交给评估/反思调用；有测试或外部反馈就让它定位这些反馈对应的代码和动作，没有 oracle 就明确用的是自评 proxy；提炼成带适用条件的下一步动作。随后还要用真实后续任务检验这条经验是否有用。”** ReasoningBank 提供了跨任务保存/检索的实证方向；Reflexion 提供了测试结果如何进入诊断和同题修复的具体范式；二者都没有把‘LLM 写出一条经验’等同于‘经验已被验证为正确’。

[RB-PAPER]: https://arxiv.org/html/2509.25140v2
[RB-REPO]: https://github.com/google-research/reasoning-bank/tree/ed80611788292ea739f1effd31f16c53823b8a0d
[RB-SWE]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/run/extra/swebench.py#L144-L263
[RB-AGENT]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/agents/default.py#L68-L135
[RB-SWE-CONFIG]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/config/extra/swebench.yaml#L172-L196
[RB-SWE-THOUGHT]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/config/extra/swebench.yaml#L1-L17
[RB-SWE-INSTRUCTION]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/third_party/src/minisweagent/memory/instruction.py#L16-L62
[RB-WEB-TRACE]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/autoeval/evaluate_trajectory.py#L27-L164
[RB-WEB-EVAL]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/autoeval/evaluator.py#L70-L98
[RB-WEB-PROMPT]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/autoeval/prompts.py#L111-L146
[RB-WEB-INDUCE]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/induce_memory.py#L47-L186
[RB-MEM-PROMPT]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/prompts/memory_instruction.py#L15-L141
[RB-PIPELINE]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/pipeline_memory.py#L47-L101
[RB-WEB-RUN]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/run.py#L161-L193
[RB-MEMORY]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/memory_management.py#L138-L218
[RB-WEB-ACTOR]: https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/WebArena/agents/legacy/agent.py#L130-L148
[RB-CASE]: https://arxiv.org/html/2509.25140v2/emergent_case_study.png
[RF-PAPER]: https://arxiv.org/html/2303.11366v4
[RF-REPO]: https://github.com/noahshinn/reflexion/tree/218cf0ef1df84b05ce379dd4a8e47f17766733a0
[RF-RUN]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/reflexion.py#L8-L101
[RF-MAIN]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/main.py#L23-L28
[RF-PY-EXEC]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/executors/py_executor.py#L10-L88
[RF-RS-EXEC]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/executors/rs_executor.py#L87-L159
[RF-GENERATOR]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/generators/generator_utils.py#L7-L194
[RF-PY-PROMPT]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/generators/py_generate.py#L151-L152
[RF-LOG]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/programming_runs/root/reflexion_humaneval_py_pass_at_1/reflexion_humaneval_py_pass_at_1.jsonl#L2
[RF-QA-ENV]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/hotpotqa_runs/environment.py#L28-L70
[RF-QA-AGENT]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/hotpotqa_runs/agents.py#L249-L371
[RF-ALF-REFLECT]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/alfworld_runs/generate_reflections.py#L8-L47
[RF-ALF-HISTORY]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/alfworld_runs/env_history.py#L4-L52
[RF-ALF-RUN]: https://github.com/noahshinn/reflexion/blob/218cf0ef1df84b05ce379dd4a8e47f17766733a0/alfworld_runs/alfworld_trial.py#L46-L72
