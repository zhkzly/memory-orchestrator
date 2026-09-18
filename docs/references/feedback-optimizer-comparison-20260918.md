# GEPA：轨迹、反馈与文本优化的责任边界

核验日期：2026-09-18。范围：论文 2507.19457v2、官方 README、`src/gepa/core/adapter.py`、`optimize_anything` 的反馈接口文档及简单问答例子。证据为论文方法陈述和静态源码／文档核验；没有运行模型或复现实验。官方 `main` 与文档为当日可见版本，未固定 commit。

**结论（高置信度）：GEPA 能把轨迹和反馈用于生成、筛选更好的文本；轨迹采集、评分依据和反馈内容由接入方的评估代码提供。支持完整轨迹，不代表接口强制完整轨迹；支持标量分数，也不代表优化器会自动补齐诊断或正确性标准。** [官方 README](https://github.com/gepa-ai/gepa#how-it-works)、[核心接口](https://github.com/gepa-ai/gepa/blob/main/src/gepa/core/adapter.py)、[Evaluator 文档](https://gepa-ai.github.io/gepa/api/optimize_anything/Evaluator/)

| 层次 | 谁构造、包含什么 | GEPA 如何消费 |
| --- | --- | --- |
| 论文方法 | 任务方给系统、任务样本、指标 μ、反馈函数 μf 和预算。μf 返回数值分数与评测文字；文字可来自编译错误、失败规则，也可补充人工评分解释。 | 反思模型结合当前 prompt、执行轨迹、分数和反馈提议 prompt；重评候选，用分数选择。论文中模型权重固定。 |
| `EvaluationBatch(outputs, scores, trajectories)` | 适配器实现者在 `evaluate` 中执行候选、返回逐例输出和浮点分数；`capture_traces=True` 时须返回与样本一一对应的 trajectory，False 时可为 None。 | 引擎不解释 outputs／trajectory 的任务语义；分数用于候选比较。trajectory 是调用方定义的对象，没有统一的“完整会话”字段要求。 |
| `make_reflective_dataset` | 同一适配器实现者从 EvaluationBatch 提取材料，按待更新组件组织可 JSON 序列化的记录。官方建议键为 `Inputs`、`Generated Outputs`、`Feedback`，可加 score 或 trace_id。 | 记录送入提议模型。源码要求提取足够且简洁的上下文，因此可以是轨迹切片；不是引擎自动理解任意日志。 |
| `optimize_anything` 的 `(score, side_info)` | 调用方编写 evaluator，计算高分为优的 score，组装自由格式诊断字典；也可以只返回 score。 | 框架反复调用 evaluator，使用诊断进行反思。`oa.log()` 可把评估期间的日志加入 side_info；`capture_stdio=True` 可采集标准输出／错误。调用方通常不必自行实现核心适配器。 |

依据：[论文 §2–3、Algorithm 1，PDF 第 4–7 页](https://arxiv.org/pdf/2507.19457v2)、[adapter.py：evaluate 与 make_reflective_dataset](https://github.com/gepa-ai/gepa/blob/main/src/gepa/core/adapter.py)、[Evaluator](https://gepa-ai.github.io/gepa/api/optimize_anything/Evaluator/)、[log](https://gepa-ai.github.io/gepa/api/optimize_anything/log/)。当前通用 API 文档把诊断字典称为 `info`，GEPA Engine 的接口称为 `side_info`；通用 API 明确接受裸分数，此时 info 默认为空字典。[当前 optimize_anything API](https://gepa-ai.github.io/gepa/api/optimize_anything/optimize_anything/)

**调用方至少要提供什么。** 核心适配器路径需要可执行的目标系统、可替换文本组件、任务样本、评分和反思材料整理逻辑；已有适配器可以承担部分实现。`optimize_anything` 至少要有 evaluator 或 batch_evaluator，并确定可评价的目标；种子可提供文本／组件字典，也可在 seedless 模式下由 objective／background 启动。单任务搜索不必提供 dataset；要判断跨任务泛化，仍需独立评价样本及评估设计。[README](https://github.com/gepa-ai/gepa#quick-start)、[API 参数契约](https://gepa-ai.github.io/gepa/api/optimize_anything/optimize_anything/)

**一个真实官方非医疗例子。** Quick Start 中的单轮问答样本是：

```json
{"input": "What is 2+2?", "additional_context": {}, "answer": "4"}
```

这里的 `answer` 由样本提供，文档说明默认适配器用它做 substring match；这不是优化器发现的真值，也没有完整多步轨迹要求。[官方 Quick Start](https://gepa-ai.github.io/gepa/guides/quickstart/#option-1-using-the-default-adapter)

不同反馈来源应保留各自证据身份，下面是接入建议【推断级】，不是 GEPA 已实现的来源鉴别器：

| 来源 | 可以作为优化信号 | 不能因此声称 |
| --- | --- | --- |
| 外部测试／环境检查 | 测试得分、实际输出、错误日志；记录检查器与案例。 | 测试通过覆盖了检查范围以外的真实正确性。 |
| 用户评论／人工评分 | 保存评论原文及其对应任务、候选和评分标准；人工解释可作为辅助反馈。 | 自由评论天然等于可比较的数值奖励，或对所有新候选都仍成立。 |
| LLM 评审 | evaluator 可以调用评审模型返回分数与解释；记录模型、rubric 和被评输出。 | 评审意见已由独立环境验证；提议模型的反思理由就是成功证据。 |

论文明确区分执行轨迹与评测轨迹，并允许人工解释；官方 SVG 示例还展示由 VLM 产生分数和 `Feedback`。这说明接口容纳多种来源，不能仅凭字段名判断其权威性。[论文 §3](https://arxiv.org/pdf/2507.19457v2)、[官方反馈接口示例](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/#lets-take-it-for-a-spin)

**用于 Skill 的边界【推断级】。** 可把 Skill 文本作为候选，让 evaluator 用该 Skill 跑任务，再把检查结果和相关轨迹送回 GEPA。优化器不会自动提供任务真值、证明评审可靠、补全未记录的执行步骤，或保证新 Skill 在未见任务上更好。负面边界也很具体：只有标量且没有日志时，接口可接受，但缺少解释失败原因的材料；如果 evaluator 的指标偏了，搜索只能按该指标选择。此次没有验证任何 Skill 的实际收益。
