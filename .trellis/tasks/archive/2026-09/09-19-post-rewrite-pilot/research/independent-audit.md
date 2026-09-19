# 重写后小批试跑：独立结果审查

审查范围：本任务冻结文档与 `research/pilot` 中已经落盘的 baseline 产物。没有调用模型/API/benchmark，没有改产品、提示词、参数、评分器，也没有读取 test001 内容或 gold。整体执行统计由根代理负责；本文只核对 Teacher 的实际数据链及失败性质。

**本轮确实进入了局部整理，但没有形成被接受的局部摘要，因而没有执行 extract、diagnose/propose、候选比较或发布。** 首次摘要正常返回；四处嵌套 JSON 的精确引用不匹配，随后修复的完整输入超过单次阶段上限。这能定位一次明确的接口与容量阻塞，不能评价尚未执行的 Skill 提炼或演化效果。

## 一、独立核实的事实

| 环节 | 落盘事实 | 证据 |
| --- | --- | --- |
| 实际局部输入 | 物理请求为 `summarize_trace_v1`；从真实 SDK messages 解码的 EvidencePacket 与 ObservedTeacher 保存的输入逐字段相同。 | [SDK 请求](pilot/calls-live/call_0006.start.json)、[Teacher 输入](pilot/baseline/teacher-inputs/01-summarize_trace_v1.json) |
| 第一包内容 | 任务原文、原始用户事件、一次读取 `answer_template.json` 的工具调用、该返回的前 600 字节，以及官方反馈的 214–1814 字节。动作/结果共享实际 call_id。 | [Teacher 输入](pilot/baseline/teacher-inputs/01-summarize_trace_v1.json) |
| 实际覆盖 | 源事件总数 138；首个实际发送包有 3 个 source event 正文。计划扫描 138，计划投影 12、遗漏 126，标记 `segment_budget`、`raw_body_complete=false`。 | [运行结果中的 trajectory_processing](pilot/baseline/result.json) |
| 首次返回 | `finish_reason=stop`；provider 报告 input 6028、output 742、total 6770，未报告价格。不存在本次返回被 length 截断或 transport timeout 的记录。 | [SDK 返回](pilot/calls-live/call_0006.return.json) |
| 草稿内容 | 三项观察：任务要求、具体 `read_input` 动作、官方评分反馈。草稿同时说明没看到 memo/API 查询/最终提交正文，且局部包不代表完整轨迹。 | [模型报告](pilot/baseline/store/records/reports/a62b3a0f148a983b0428fbb4759d8f2d13980b720c06ac2e9416fe287d34676d.json) |
| 首个拒绝 | `summary_evidence`：观察 2 的 excerpts 1–4 不是对应 fragment 的精确子串。任务的两条引文、完整工具动作引文、外层 `outcome=fail` 引文均精确匹配。共核对 8 条，4 匹配、4 不匹配。 | [模型报告中的 attempts/diagnostics](pilot/baseline/store/records/reports/a62b3a0f148a983b0428fbb4759d8f2d13980b720c06ac2e9416fe287d34676d.json) |
| 修复未发出 | 下一次完整输入由 18830 增到 24228 字符；估计 token 从 6616 增到 8649，超过 summarize 单次上限 8000，`preview.fits=false`。第二次 provider 调用没有发生。 | [错误记录](pilot/baseline/store/records/errors/3ca0bc378a787d05b357ed04b8f4b264cacf6a075d762f7e8f2369da5f2c046f.json) |
| 总额度未耗尽 | 拒绝时 Teacher 全局输入还剩 153972、输出还剩 23258；summary 累计还剩输入 25972、输出 3258，并还有 3 次调用额度。挡住的是单次完整输入，不是累计额度用尽。 | [错误记录中的 preview.budget.remaining](pilot/baseline/store/records/errors/3ca0bc378a787d05b357ed04b8f4b264cacf6a075d762f7e8f2369da5f2c046f.json) |
| 停止与后续 | 第一段 failed，其余三段 `not_analyzed_after_stop`；接受的 summary_count 为 0。learning/engine 均 abstained，experience/candidate 为空，diagnosis/comparison/release 为 null。 | [最终结果](pilot/baseline/result.json) |
| 实际发布状态 | active generation 仍为 0，bootstrap 为空库，release_id 为 null，committed_release_ids 为空。 | [active 指针](pilot/baseline/store/projects/ebf0a1b496d76f1a18936e0de4adc723381e2bf0893d3fbfce2d334a5a2dcb53/active.json) |

外层 `baseline/result.status=completed` 只表示运行程序完成，不能写成“学习成功”。同样，`analyzed_event_count=0` 与 `summary_count=0` 是没有被接受的局部学习结果，不能写成“没有向模型发送任何轨迹”：真实第一包已经发送，草稿也已经返回。

## 二、四处引文失败的实际性质

四个被拒 quote 的内容分别指向：

- `SP001_order_set_and_count`，matched=true；
- `SP002_inventory_statuses_and_shortages`，matched=false；
- `SP004_customer_exceptions`，matched=true；
- `SP007_shipping_quotes`，matched=true。

它们的 id 与布尔值都确实出现在该次已提供的 feedback fragment 中，也与原 [官方反馈记录](pilot/baseline/store/records/feedback/f7fbdb8587be385ff731ad6c0c135aeadcae92c43ea79e03d9a5fee5da5fa76a.json) 一致。本审查仅读取既有评分返回，没有读取评分器 gold。

可复核的字符串区别是：模型 quote 使用普通 JSON 片段，例如 `"id":"SP001_order_set_and_count","matched":true`；实际 fragment 是序列化的 Feedback，内部 `reason` 又是一个 JSON 字符串，所以该段原文仍含转义反斜杠。独立检查四项均得到：

```text
quote in provided_fragment: False
quote.replace('"', '\\"') in provided_fragment: True
```

这支持“**嵌套表示的精确复制失败**”，不支持把这四个评分值直接称为凭空编造。宿主也没有错误接受它们：现行引用契约要求原文子串，拒绝符合冻结规则。这里仍有两层不同的判断：

1. 内容对应了已有评分证据，不等于原文引用有效；本次失败在这一层被拦住。
2. 即使把引文复制正确，评分匹配/未匹配也只能说明结果类别，不能单独证明某个订单、库存记录或决策步骤导致了失败，更不能证明修改后的 Skill 有效。

三条草稿中包含具体文件路径、任务输出要求和评分项，不能说它只是完全无内容的泛泛摘要；但它也没有形成订单级错误归因或可复用修复步骤。由于 extract/diagnose/propose 根本没运行，当前没有可供评价的“生成 Skill 太泛”结果。

## 三、对证据的解释与仍未测项

**由本轮记录支持的推断**：首次局部包能容纳并正常返回，不代表同样的 8000 单次输入预算能容纳“原消息 + 被拒稿 + 多项诊断 + 修复限制”。实际修复预检拒绝使剩余累计预算和其他计划段没有被消费。因而本轮最早的有效阻塞链是“精确引文失败 → 修复输入容纳不下 → 本次局部学习停止”，而不是“模型超时”“输出被截断”或“所有 Teacher 额度烧完”。

**本轮没有证明**：改变引用表示或调整修复预留后，模型一定会形成更具体的经验；一次已接受摘要足以覆盖 138 事件；新 Skill 会改善 train001、保持 train004，或能迁移到未见任务。这些环节没有执行，不能用本轮 abstention 填上效果结论。

**成本边界**：这里的 6028/742 是唯一已观察摘要调用的 provider 用量，6616/8649 是宿主估算，不能相加当实测。摘要尝试失败仍保留其用量；价格字段缺失，本文不估算货币收益。整体 Actor/Teacher 成本与任务分母以根代理的全运行统计为准。

**冻结纪律**：本审查没有提出在这次运行中修改阈值、跳过精确引用检查或补发调用。后续若决定验证不同表示或修复容量，需要单独保留新的配置与运行身份；本轮原始负结果继续有效。

## 四、审查执行记录

只使用本地 JSON 读取，独立完成以下检查，均正常结束（exit 0）：

- SDK `call_0006.start/return` 与 Teacher 报告绑定同一 request_id `resp_0c348421ff2e27a4016aae115b2ab487d0ae0daa609af2a0c1`；从真实 messages 中解出的 packet 与 ObservedTeacher 输入相等。
- 逐项检查 8 个 quote 是否属于指定已提供 fragment，并对四个不匹配项验证一次 JSON 引号转义后的对应关系。
- 将草稿列出的评分项与已存官方反馈结果对照，未访问 gold 或 test001。
- 检查所有四个计划段的终态、learning/engine 决策、空候选列表及 active 发布指针；没有仅凭最外层 completed 判断成功。

本文没有重复遍历/汇总全部 SDK 调用，也没有启动额外任务执行。其结论限于以上已落盘证据。
