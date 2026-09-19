# 完整消息与累计 token 预算的最小接缝

状态：规划研究，2026-09-19。只读审查 `model.py`、真实调用方和现有测试；没有修改产品、运行模型或新增实验。读取的总纲为 v1.7.1，source SHA-256 `3a8255b5a94249be66529f98f55152c4dbccbc7772198760bdf64fa9b3538aa6`，对应 N04/N06 及 Q10/Q28。根代理已确认下述最小接口方向；本文仍是规划依据，不表示实现已完成。

**建议在现有 StructuredModel 中扩展预算，不另建模型框架。** 完整渲染后的消息是计量对象；局部整理、抽取、补读重抽取、归集、诊断、多个候选及修复共享一次学习周期的账。token 预估/预算预留与 provider 实测用量必须分开保存。

## 1. 当前真正生效的边界

| 代码与测试 | 实际行为 | 本轮需要补上的部分 |
| --- | --- | --- |
| [model.py:28–45](../../../../src/memory_orchestrator/model.py#L28) | 接受六个固定字符/调用/输出上限；其他 `limits` 键不进入 `self.limits`。明确说字符不是 token。 | 新 token 配置必须显式解析并冻结；错误拼写不能继续静默忽略。 |
| [model.py:56–85](../../../../src/memory_orchestrator/model.py#L56) | 完整渲染 system、user、输出 schema、可见限制；不是只计算 evidence packet。 | 这是 token counter 的正确接入位置。不要另在 learning 里拼一份近似 prompt。 |
| [model.py:95–116](../../../../src/memory_orchestrator/model.py#L95) | 每个 attempt 计算 `len(JSON(messages))`；调用前累计字符和调用数。 | 没有累计输入/输出 token，也没有阶段额度。 |
| [model.py:125–180](../../../../src/memory_orchestrator/model.py#L125) | provider token 只接受非负整数；缺失保留 null；返回后检查单次 output token 上限。 | 实测 token 当前未用于下一次调用准入；未知 usage 也没有 token 预留。 |
| [model.py:199–208](../../../../src/memory_orchestrator/model.py#L199) | 格式与纯语义检查共用有限修复循环；原输入、被拒输出和诊断进入下次 messages。 | 每次修复必须重新计完整消息，不能复用第一次的 token 估计。 |
| [learning.py:295–348](../../../../src/memory_orchestrator/learning.py#L295) | teacher 的全部调用经过一个 `call()`，usage 统一落账；补读和候选循环复用同一个 model。 | 新局部整理也必须走这个入口；不能直接 invoke 或每块新建 model。 |
| [feedback.py:403–425](../../../../src/memory_orchestrator/feedback.py#L403) | proxy 的 model limits 必须等于冻结配置；有独立记录与恢复边界。 | token 配置若藏在新对象中而不进 limits，会逃过已有冻结检查。proxy 与学习周期不能无说明混账。 |
| [experiments.py:154–173](../../../../src/memory_orchestrator/experiments.py#L154) | 每周期创建 fresh teacher；实验臂另累计调用数。 | 周期累计 token 不自动等于整臂累计 token。 |
| [sdk.py:61–96](../../../../examples/gdpevo_pilot/sdk.py#L61) | GDPevo 外层把完整 messages/tools/options 按字符计量，先存 start 再调用；可以跨 reopen 计调用数。 | 它是现成的外层物理调用记录，不是核心当前已具备的累计 token 实现。 |

现有 packet 的 `ceil(UTF-8 JSON bytes / 3)` 已标为估计，见 [evidence.py:533–538](../../../../src/memory_orchestrator/evidence.py#L533)、[evidence.py:598](../../../../src/memory_orchestrator/evidence.py#L598)。它只约束 packet，既不是 tokenizer 实测，也不包含 schema、system、相关经验、修复消息等完整开销，不能把它直接当 model 的累计 token 计数器。

## 2. 建议接口与明确作用域

保留现有 `generate(prompt_id, inputs, *, check=None)`，只在构造和纯预览处增加接缝：

```python
StructuredModel(invoke, *, limits, token_counter=None)
model.preview(prompt_id, inputs)  # 纯函数式预检：不调用 invoke、不扣款、不消费调用额度
model.generate(prompt_id, inputs, *, check=None)
```

`limits` 保留当前六个字段，新增一个显式可选的 `token_budget`。最小形状如下，所有金额与阈值由调用方配置，本文不指定科学默认值：

```text
token_budget = {
  counter_id,                      # tokenizer/估算实现和版本身份
  count_kind: "tokenizer_estimate" | "documented_estimate",
  max_input_tokens,                # 单次完整 rendered messages 的估计上限
  max_total_input_tokens,          # 本 model 生命周期内的预留/结算累计上限
  max_total_output_tokens,
  stages: {
    <已注册 prompt_id>: {
      max_calls,
      max_input_tokens,
      max_output_tokens,
      max_total_input_tokens,
      max_total_output_tokens
    }
  }
}
```

- 阶段直接用现有固定 `prompt_id`；goal binding、局部整理（新 prompt 名由总纲确认）、extract、maintenance、diagnose、propose、proxy 分别计量。不新增调用者任意填写的 stage 字符串。多个候选的 propose 和多次补读的 extract 不各开一份额度。
- token 模式下，用到的 prompt 必须有 stage 配置；不能漏配后默认为无限。保留全局字符上限，作为独立的内存/序列化保护，不改名为 token。
- `token_counter(messages) -> int` 接收即将发出的完整消息深拷贝，覆盖每个 role/content 及该计数实现的聊天包装开销；返回 bool、负数、小数、异常均在调用前拒绝。计数器身份和估计方法进入 `limits.token_budget`，函数本身不序列化。
- 不能仅凭网关别名 `gpt-5.6-terra` 猜出 tokenizer。根代理确认允许默认估算器：对**完整 rendered messages 的 UTF-8 JSON 字节**计算 `ceil(bytes / 3)`，在配置和结果中明确标为 `documented_estimate`，计数器身份可为 `utf8-json-bytes-div3-v1`；不能当成 tokenizer 实测或保守数学上界。调用方可注入匹配 tokenizer 替换它。本轮不添加 tokenizer 下载器或模型注册表，也不在注入的 counter 抛错后静默回退。
- tokenizer 预估也不自动等于服务端实测：服务端模板、额外 framing 以及 transport 添加的字段可能不同。counter 的适用范围必须记录；只有已知保守上界才可声称输入硬上限，否则是“预估准入 + 实测超额后停止”。不能承诺精确账单上限。
- `preview` 与 `generate` 共用一个内部 renderer，返回 `fits / estimated_input_tokens / effective_output_cap`，附 `messages_hash / input_chars / blocking_reason`。局部整理据此缩小窗口，窗口内的 schema、指令和来源元数据也占预算。preview 本身不预留，generate 发出前重检，不能凭旧 preview 绕过已消费的额度。
- 预算可见说明必须先放入 messages，再计数；计数后不得继续追加字段。避免把“本次估计 token 数”不断回填进同一 prompt 造成自引用。修复时仍以实际准备发送的 messages 为准。

阶段 cap 是上限，不自动保证后续阶段有足够额度。最简单的配置方式是预先划定各阶段配额、让阶段总配额不超过周期总配额；本轮不需要动态借贷或预算调度器。局部整理额度不能被配置成可以无条件吃完整个周期。

根代理确认的**可配置参考分配**为：局部 summarize 阶段最多 4 次，累计输入 16000、累计输出 1600；extract 阶段最多 2 次，累计输入 8000、累计输出 1400。因此“局部整理 + 提取”自然受到输入 24000、输出 3000 的合计子上限，无需另造 scope 框架。上述数字不是写死的算法常量；完整 Teacher 总预算另覆盖 goal binding、maintenance、diagnose、propose 等实际阶段，每阶段单次上限仍在有效配置中明示。

## 3. 每一次真实尝试的预留与结算

对 attempt `a`，令 `e_a` 为完整输入估计，`o_a` 为实际传给 transport 的输出上限。`o_a` 来自明确的全局与阶段配置，不因余额不足悄悄变成一个过小的 JSON 输出预算。

1. **调用前准入。** 同时检查字符、单次 token、总调用、阶段调用和输入/输出累计余额；拟预留 `(e_a, o_a)`。任何一项不足都不调用 provider，不增加“实际调用数”；记录拒绝原因和尚未运行的阶段/候选。
2. **先预留再 invoke。** 全局与阶段同时扣减可用额度，attempt 消费一次调用。局部整理仍按顺序运行即可；若后来并行，预留必须原子化，不能由各线程分别先读余额后扣减。
3. **独立结算两种用量。** 有合法 provider `input_tokens` 就按它结算输入；否则保留 `e_a` 的预算占用。有合法 `output_tokens` 就按它结算输出；否则保留全部 `o_a`。缺少分项时，不由 `total_tokens` 拆出分项，不把生成文本长度当完整输出 token。
4. **失败不退款为零。** transport 异常、无 envelope、缺 usage、截断、格式/引用/语义失败都保留该 attempt。格式或语义修复的新 attempt 重新预留完整 messages；异常不新增隐式重试。现有 SDK `max_retries=0` 保持。
5. **实测超额如实保留。** 若 provider 回报高于预留，记录实际量和 overrun，停止后续调用；不能截小 usage 来维持“未超预算”的表象。本次生成也不能记成预算检查成功。预估失准是边界事件，不是自动获准扩大额度。
6. **每周期仅一份状态。** 一个 learning cycle 的所有 local/extract/maintain/diagnose/propose 调用共享 model 状态。`max_format_repairs` 仍是单次 generate 内的修复上限，且同时受整个周期和阶段的额度约束。

建议每个现有 usage entry 增加 `budget` 旁注：`counter_id / count_kind / estimated_input_tokens / reserved_input_tokens / reserved_output_tokens / input_debit / output_debit / debit_basis / budget_status / messages_hash`。这里的 debit 是额度占用，不是财务结算。

现有 `input_tokens/output_tokens/total_tokens`、`measurement` 和归一 `usage.tokens` 继续只保存 provider 合法报告。未知时仍是 null。`learn.persist_call` 已保存 `raw=entry`，因此预算旁注有真实存储消费者；项目报告的实测 token 统计不能把 reserve 再加一次。显式 monetary_cost 仍只来自 transport，不从 token 猜价格。

## 4. 真正接入位置与短轨迹兼容

- **N04/N06 局部整理**：先用完整 renderer 的 preview 判定局部窗口能否容纳；调用经过现有 `learning.call()`，输出再参与后续提取。分层后的结果更短，不代表整理模型自己的输入已受控；整理前的窗口和每轮追加的上下文都要计量。
- **普通短轨迹**：能直接容纳时走已有 extract 路径，不为展示分层机制额外调用一次压缩模型。没有 `token_budget` 的旧调用方保留六字段字符语义；有新预算的短轨迹仍保持原阶段顺序、引用校验、候选/发布规则。新配置不承诺生成文本逐字不变。
- **配置冻结**：token 配置保留在 `model.limits` 内，现有 learning cycle 的 `model_limits` 快照及 proxy 的配置相等检查自然覆盖。counter 身份也必须被快照记录。`_visible_limits()` 同时显示字符和估计 token 的剩余额度，不能把全部剩余统称字符。
- **失败出口**：新增预算错误建议仍归入 `model_budget_exhausted`，用 details 区分全局/阶段/input/output/计数器缺失；或者同步调整 [learning.py:573–576](../../../../src/memory_orchestrator/learning.py#L573) 的分类。不能令“正常预算耗尽”意外变成不可解释的产品错误。
- **scope 边界**：默认是单个 model 生命周期/学习周期，不是整个实验或账号。`experiments` 每周期重新创建 model；若产品本轮承诺“每实验臂总 token”，必须像现有 `arm_calls` 一样从所有周期的预算占用累计并传剩余额度，不可只改周期类就声称完成。
- **中断边界**：当前核心 `generate` 仅捕获 Exception，`learn` 在 BaseException 时没有逐 attempt 的已持久化预算记录；现有 pilot 外层才有先写 start 的记录。这意味着仅在内存加 counter 无法证明进程重启后仍遵守同一累计上限。若本轮要求同一周期恢复，必须在 invoke 前把预留写到已有周期相关账本，重开时先重建未结算占用，未知 started 不自动退款/重跑；否则明示仅支持当前周期实例，恢复不得冒称同一未耗预算。无需因此重建通用调度层。

## 5. 验收场景（建议，不是本轮已运行结果）

| 场景 | 必须观察到的结果 |
| --- | --- |
| 小 evidence packet + 很长 system/schema/related memories | counter 看到完整 rendered messages；合计超限时 provider 调用数为 0。 |
| 中英文/标点混合，同字符数但注入 counter 给出不同 token 数 | 按 counter 决策；字符数保留且明确独立，不当 token 实测。 |
| preview 后先执行另一个调用 | generate 重检剩余额度；不能用旧 preview 越界。 |
| local block 连续多次调用，单次都合格但累计超限 | 终止后续 block；保留已花费调用和未处理范围，不能重新创建 model 逃逸。 |
| local stage 耗尽但总预算尚有余量 | local 不再运行；阶段拒绝原因可见；后续合法阶段额度不被偷偷改写。 |
| extract 补读一次、diagnose 修复一次、两个 propose 候选 | 每次 attempt 都归正确 prompt stage，重复输入逐次收费；总账不按最好候选筛选。 |
| 第一轮 JSON/引用错误导致修复消息很长 | 修复前再次估计完整消息，超限不调用；第一轮用量仍存在。 |
| transport 异常或回报 null/非法 token | 调用次数已消费，输入估计和输出 cap 继续占预算；report 实测仍是 null，不归零。 |
| 只回报 total_tokens，或只回报 output_tokens | 各分项独立结算；不推算缺失项，也不重复把 total 加到 input+output。 |
| provider 回报超过预留/上限 | 保存原实测、标 overrun、阻止后续调用；不改小报告数字。 |
| 足够短的原流程 fixture | 不新增 local 整理调用；现有结构/引用/反馈/候选行为仍通过，旧字符模式兼容。 |
| proxy 与 learn 冻结配置、重开/跨周期范围 | 新 token 配置变更可检出；未实现的跨进程或整臂预算不得被测试名称包装为已完成。 |

这些验收应以 injected counter + FakeCall + 真实 Store 的定向测试完成，无需付费模型验证预算机制。已有保护应继续保留：[model tests:59–105](../../../../tests/test_memory_model.py#L59) 的修复/异常/调用前拒绝、[model tests:155–181](../../../../tests/test_memory_model.py#L155) 的非法 usage、[learning tests:372–400](../../../../tests/test_memory_learning.py#L372) 的跨阶段计量、[report tests:71–89](../../../../tests/test_memory_report.py#L71) 的分项缺失，以及 [GDPevo SDK tests:24–69](../../../../tests/test_gdpevo_sdk.py#L24) 的先写调用与重开记录。它们目前没有覆盖新增累计 token 和分阶段预算，不能以旧测试存在声称本轮机制已完成。

## 6. 收口

最先应修的是**预算消费的统一位置**，而不是增加更多摘要层：完整 renderer → 预检 → attempt 预留 → provider → 合法 usage 结算 → 原有结构/语义校验与有界修复。分层整理只是这条链上的一个新 prompt。本文仅提供上述接口与当前边界，未更改提示词、总纲、状态、代码或测试。
