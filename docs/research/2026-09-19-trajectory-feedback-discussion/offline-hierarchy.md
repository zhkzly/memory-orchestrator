# 分层处理发生在哪里：SimpleMem 与 Tree-of-Experience

核验日期：2026-09-19。**先分块再提取，确实是一个独立且必要讨论的问题；“最后产出层次化经验”并不证明提炼器的第一层输入已经有界。** 本次可确认 SimpleMem 的写入器先按消息数切窗、每窗提取；没有确认一个“窗口摘要→跨窗口摘要→程序性经验”的三级学习器。ToE 的层次主要组织分析视角和推理路径，并非长工具轨迹预处理器。

范围按根代理最新分工调整为 ToE + SimpleMem，不继续展开 ExpeL，也不重复其他 worker 的 STAIR 调研。只读论文与源码，没有运行模型、实验或下载 benchmark 数据；仅写本文。标记：**【源码级】**静态调用链；**【原文级】**论文说明；**【实验级】**作者报告；**【推断级】**由机制得到的判断。

## 1. 版本与核验边界

- **SimpleMem**：[论文 v3，2026-01-29](https://arxiv.org/html/2601.02553v3)；公开代码固定为 [`db80b6a7c591e0ea730a058e9f5fc4eb06572299`](https://github.com/aiming-lab/SimpleMem/commit/db80b6a7c591e0ea730a058e9f5fc4eb06572299)，2026-07-24。代码晚于论文，不声称它与论文实验逐项相同。核对核心写入、模型调用、存储及检索路径，不将当前仓库其他扩展一概归入本论文实现。
- **Tree-of-Experience**：[论文 v1，2026-08-10](https://arxiv.org/html/2608.09044v1)。论文说代码在 supplementary，但正文/摘要未提供可核验的作者仓库；有限精确检索未找到官方固定 commit。因此 ToE 以下仅到原文级，不给虚构源码函数，不把“未找到”说成不存在。

## 2. SimpleMem：实际写入链不是多级总结树

### 2.1 模型调用之前：先切窗口，不先把全历史送给模型

【源码级】实际链路：

```text
Dialogue(id, speaker, content, timestamp)
  → MemoryBuilder 缓冲区
  → 按消息条数选一个连续窗口
  → 完整字符串化该窗口 + 少量已有 memory restatement
  → 一次 LLM 直接生成 MemoryEntry[]
  → 解析 → embedding → 数据库 insert
```

入口是 [`SimpleMemSystem.add_dialogue/add_dialogues/finalize`](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/main.py#L104)。窗口在模型调用**之前**由 [`MemoryBuilder.process_window()`](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L121) 用列表切片选出；`_generate_memory_entries()` 才拼接正文并调用模型。[生成入口 L156–199](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L156)

每次调用实际包含：

| 路径 | 本次正文 | 跨窗口信息 | 后续处理 |
| --- | --- | --- | --- |
| 顺序 `process_window` | 一个窗口的完整 `str(Dialogue)` | 前次留下的最多 3 个 MemoryEntry 的 `lossless_restatement` | 本窗直接生成条目，写库；这些条目成为之后的参考。 |
| 并行 `_generate_memory_entries_worker` | 每个 worker 只处理一个窗口 | 所有 worker 使用这批处理前的共享 `previous_entries[:3]`；不能读取同批尚未产生的前窗结果 | 收集各窗口条目后拼接，一次写库；没有跨窗口第二次 LLM 总结。 |
| `process_remaining` | 剩余缓冲区全文 | 同上 | 正常自动处理后通常是尾窗；函数本身并不再次按 W 拆分。 |

[顺序/尾窗 L121–169](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L121)、[并行 L311–392](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L311)。批处理大于两倍窗口大小时默认可进入并行路线；这不是“先串行形成各窗摘要、再串行综合”。

### 2.2 窗口数量有界，不等于输入 token 有界

【源码级】该 commit 的内置配置是 **W=40 条消息、overlap=2 条、步长=38**；调用方可覆盖。论文 §3.1 的实验设置 W=20，二者要分开报告。[settings 默认值](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/settings.py)、[步长 L38–43](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L38)

`Dialogue.content` 没有长度约束，`__str__` 完整输出 speaker/content/timestamp；builder 没有字符或 token 计数、单消息进一步分块或超预算递归拆分。`LLMClient.chat_completion()` 将传入 messages 原样交给 SDK，重试也没有缩短输入；settings 中的 `MAX_TOKENS` 在这条调用里没有被使用。[Dialogue L65–76](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/models/memory_entry.py#L65)、[SDK 边界 L43–113](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/utils/llm_client.py#L43)

【推断级】因此一个窗口可以包含一条极长日志；只限制 40 条，不能保证提炼模型装得下。用户质疑的“第一层本身怎么处理超长输入”在这条公开实现中仍没有完整答案。若调用方关闭自动处理并积累缓冲区，`process_remaining()` 也依赖调用方此前正确推进，不能被当成所有入口的强制窗口上限。

### 2.3 一次生成同时承担提取与综合，没有独立二级归纳调用

【源码级】实际 extraction prompt 要求覆盖有价值信息、消解代词与相对时间，并输出 `lossless_restatement/keywords/timestamp/location/persons/entities/topic`。输入是原窗口和前次少量 restatement，没有单独传入一个第一阶段 facts 列表再做第二调用。[`_build_extraction_prompt` L209–280](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L209)

【原文级】v3 把第二阶段称为写入期间的 Online Semantic Synthesis；早期摘要的 Recursive Memory Consolidation 名称不能证明该 commit 存在后台递归汇总。**【源码级】**已查写入器只有窗口级生成，随后 [`VectorStore.add_entries()`](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/database/vector_store.py#L55) 对 restatement 编码并 insert，不在这里再次调用总结模型。该存储函数也已从此 commit 的完整 diff 核验。

跨窗口确实有“带前三条旧记忆帮助消歧/避免重复”的弱连接，但它不等于层次树，也不等于整个会话的二级综合。并行结果按完成顺序收集；写后的 `previous_entries=all_entries[-10:]` 也不是严格按原时间顺序选出的末窗摘要。这是静态实现限制，不是本次测得的效果回归。

### 2.4 这是事实型聊天记忆，不能直接充当工具轨迹经验学习证据

【源码级】核心 `Dialogue` 只有 speaker/content/timestamp，`MemoryEntry` 以事实重述和检索属性为主，没有 tool call/result 配对、目标修订、verifier outcome 或成功/失败归因字段。调用方可以把工具日志塞进 content，但该表示不自动保留这些结构。[数据结构](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/models/memory_entry.py#L13)

builder 虽收集 `dialogue_ids`，其 `_parse_llm_response()` 没把这些 ID 写入条目；原始措辞、调用顺序以及原文定位不在存储结构中。所谓 lossless 是提取目标，不是代码保证或可逆编码。[解析 L283–309](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/memory_builder.py#L283)

【源码级】检索阶段确有 planning/reflection 追加搜索，但搜的是这些 MemoryEntry，再用其回答当前问题；它不是离线写入阶段重新读取原始窗口、也不是写出新的程序性经验层。[`HybridRetriever._retrieve_with_planning`](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/hybrid_retriever.py#L70)、[`_retrieve_with_intelligent_reflection`](https://github.com/aiming-lab/SimpleMem/blob/db80b6a7c591e0ea730a058e9f5fc4eb06572299/simplemem/core/hybrid_retriever.py#L744)

## 3. ToE：层次组织经验，不是给任意长日志分块

以下均为【原文级】，代码未核验。金融分支的数据路径是：新闻→预先标注行业/因子→按前缀检索或扩展 analysis_direction→带经验路径预测→未来环境结果更新该路径可靠性→必要时合并方向。行业/因子缓存减少重复推理；三级 CSV 路径是经验组织结构，不是原始轨迹三级摘要。Game of 24 则保存经过确定性验证的规范化子状态与解题后缀。[方法与实现附录](https://arxiv.org/html/2608.09044v1)

论文允许从多条模型推理路径聚类抽象初始树，但未给“任意长度 tool logs→有界叶块→局部摘要→总括经验”的首层预算与预处理实现。它面向数学推理/金融分析；不能把结果直接等同于处理原生编程助手的冗长工具轨迹。其层次主要贯穿推理路径生成、经验存储与复用，而非用户提出的日志压缩器。

## 4. 效果与未证明处

- **SimpleMem【实验级】**：LoCoMo 的 GPT-4.1-mini 消融中，完整模型 F1=43.24，去 semantic compression 为31.29，去 online synthesis 为38.24；支持聊天记忆构造的价值。其原文报告 LongMemEval 的部分分项也低于其他方法，例如 mini 模型 knowledge-update 79.48% 低于 LightMem 的92.30%。这些不验证上述晚期 commit 的每个实现细节，更不证明工具失败归因准确或 Skill 会改进。[论文 Tables 2、5](https://arxiv.org/html/2601.02553v3)
- **ToE【实验级】**：作者报告金融任务 Qwen 的10日 Overall tsIC 从无经验0.0349降至0.0322；LLM 直接更新可靠性也弱于其公式更新。收益有条件，且未做长日志分块策略的独立消融。[论文 Tables 1、3](https://arxiv.org/html/2608.09044v1)
- **共同未证明**：两者都不能证明“分层输出天然保证不丢因果证据”。SimpleMem 的单窗长度及源引用有实际缺口；ToE 缺公开源码核验，且研究对象不是通用日志压缩。

## 5. 可以直接用于讨论的结论

**应把三个设计问题拆开：首层输入怎么有界；局部事实怎么带来源汇合；最后怎么跨片段归纳成经验。** SimpleMem 给出了第一步的消息窗口实现，但没有严格 token 上限，也没有明确的跨窗口第二轮经验总结。ToE 给出了经验组织与更新的层次，但不负责第一步。

因此，“先局部整理、再全局归纳”是值得认真设计的候选方向；仅说按需补读并未回答首轮怎么读完关键事实。若采用层次处理，中间产物应保留要求、动作—结果对应、关键数据、失败/恢复和原文引用，而不是只有自由摘要；各层输入均须有预算。这个建议是我们的【推断级】设计判断，不冒充上述论文已经验证的统一方案，本轮不据此修改系统。
