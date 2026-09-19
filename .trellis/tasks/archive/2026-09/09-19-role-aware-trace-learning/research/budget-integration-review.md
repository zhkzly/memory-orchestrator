# 独立预算与统一学习入口审查

2026-09-19，只读审查 model.py 和 root 的 learning.py，不复审本人编写的 evidence。未改产品、未运行真实模型/benchmark；使用保存的 GDPevo train_001 fixture、临时真实 Store、明确标记的注入计数器/transport 返回，共六个有界 probe，全部断言通过。

审查基线 SHA-256：

- model.py：`ebeca19f47c1f887861c9f0ed1acc0bc63cf3f3ca89ed2a6834e40d61084c356`
- learning.py：`f0e883b1118b0d992eedbde77a9a8dc49f6013708f0b86f8ccde69d2be6dcf84`

结论：**未发现这批检查中存在超额继续调用、修复/补读免费绕过或将预留冒充实报的缺陷。** 有一项配置相关的效率边界：最初确认 extract 可调用，不等于为它保留后续份额；连续摘要仍可能消耗掉提取器需要的全局余量，最后安全弃权。详情见第3节，未擅自修改。

## 1. 当前实际边界

| 审查项 | 源码数据流 | 判断 |
| --- | --- | --- |
| 完整 rendered messages | `_render` 加 system、模板、输入、输出schema和宿主限额；`_inspect` 计量该完整列表 | 计的是实际调用前消息，不只是证据正文。 |
| preview→generate | preview 不扣费；generate 重新render，并在同一锁内inspect/reserve | 旧 preview 不是通行证，也不是免费持有额度。 |
| 输出预留 | 每次 cap=min(模型上限,stage上限)，先检查全局/阶段余量并预留 | 预留值传入实际 transport；不按模型正文承诺的长度放行。 |
| 实报与未知 | `_settle` 按可用input/output分别结算，缺失维度保持预留 | 默认估算不写到实报token字段；未知不填0。 |
| 修复 | 保留原输入，追加被拒JSON/诊断，再inspect | 同一个stage和全局配额，次数、增大后的输入均重算。 |
| 补读 | `learn` 扩包后仍通过同一model.generate | 读取了更多原文不带来新的免费模型调用额度。 |
| 实报越界 | `_settle` 保存已发生的超额并锁住后续调用 | 估算并非上界；这里只能保留实际消耗并阻止继续，不能撤销已发请求。 |
| 统一入口 | `_learning_packet` 一条新计划路径，内部区分direct/local | short也先经过新计划；不以null关闭该路径。 |
| 下游先验可行性 | local之前preview完整extract prompt+原文锚点 | 提取器本身不可能调用时，避免先付摘要成本。 |
| 局部失败 | 捕获局部DomainError，保存失败report/usage，保留此前有效summary | 剩余额度可用时仍能提取；不是任何失败都清空此前工作。 |

位置：[model.py L89–240](../../../../src/memory_orchestrator/model.py)、[generate L242–389](../../../../src/memory_orchestrator/model.py)、[learning.py 的 _learning_packet / call / 提取补读循环](../../../../src/memory_orchestrator/learning.py)。

## 2. 六个实际 probe

数据与助手复用 `test_memory_model_budget.ModelBudgetTests.extract_inputs`、`test_memory_trajectory_learning.FIXTURE/processing/RecordingTeacher/request_packet`；通过真实 StructuredModel、learn、Store、report 消费，未用替身绕开这些模块。

| Probe | 关键配置/扰动 | 实际结果 |
| --- | --- | --- |
| P1 全输入与preview过期 | counter固定100（标记documented_estimate），全局input总额150；preview后先执行一次实报input100 | 初次fits；counter收到的完整消息hash等于transport消息；第二次generate拒绝，实际仅1次调用。 |
| P2 估算与实报分离 | 默认UTF-8 JSON字节/3；transport构造实报input11/output7 | 估计输入22,514；usage.input_tokens与budget最终input_debit均11；未把22,514算进实报。 |
| P3 局部坏输出＋修复预算不足 | 两段summary，第二段bad JSON；初次counter100、repair消息counter200；summary累计input250。两次summary实报input100但output=None | 请求顺序summary、summary、extract；repair没有实际发送；第一段仍进入extract。三个usage都保存，两个未知output各保留100预留，extract实报7；预算debit合计207，报告output完整总额仍null，仅已知小计7。 |
| P4 提取器预先不可行 | extract单次input上限0；counter100 | 0个summary、0个extract、0 usage；abstained明确说明提取prompt/锚点已超限。 |
| P5 共享output被摘要消耗 | 全局output250，各summary/extract cap100；两段合法summary均output=None | 发送两个summary，保留200未知output预留；之后extract不能预留100，0 extract，abstained。没有超预算，但存在第3节的浪费边界。 |
| P6 补读仍受原stage限额 | 短真实前缀走direct，extract返回合法needs_more_evidence；extract stage max_calls=1 | 原片段从4增至5；第二次extract在stage.calls门被拒；只有1次transport、1条付费usage，另存0-call拒绝report。 |

P3的真实报告还保留 input已知小计300、output缺失调用2、total缺失调用3，未从input/output倒推出total。最终status是脚本化extract的abstained，不是声称产生了正确经验。

## 3. 一项已证实的剩余效率边界

**P5：初始preview只证明当时能提取，不为下游留预算。** 复现参数并不违反当前配置校验：global_output=250，summary stage允许至少2次，各次output cap100，extract cap100；每次summary返回合法局部记录，但transport不报告output。第一次摘要之后还剩150，足够做一次extract；系统继续第二次摘要后只剩50，导致两份有效局部结果均无法进入提取器。

数据路径：`_learning_packet` 的提取可行性检查→完整局部循环→合并summary时再次preview extract。最终summary_count=0、两个segment均completed，reason为局部记录无法与提取prompt/锚点共同适配预算。模型层正确保留未知预留，不能通过假设其实际很便宜来放行。

这不是预算守卫失效，也不产生错误发布；它说明**stage上限不是为stage保留的额度**。当前示例配置已能走通，不把此构造案例外推为示例总是失败。若项目承诺“至少得到一份有效局部记录后优先保留一次提取机会”，需要在每次继续摘要前保留相应份额或明确配置约束；单次启动前preview不足以证明这一承诺。该点已原样通知root，本review不改源码或扩大实现。

root已明确接受这项配置边界：本轮不引入通用调度或预算借贷；阶段cap与全局cap同时生效，余量不足可partial/abstain，不能宣传必然完成后续步骤。参考profile的阶段分配与全局容量需一致。该反例保留为未消除的效率限制，不记作已修复或无风险。

## 4. 复跑要点与证据上限

P3/P5用 `RecordingTeacher` 真实返回格式，覆盖外层usage为 `input_tokens=100, output_tokens=None, total_tokens=None`；extract返回合法abstain且output_tokens=7。模型counter在2条messages时返回100，修复后超过2条时返回200；counter_id固定为 `review-messages-count-v1`，count_kind为`documented_estimate`。局部处理配置沿现有 `processing()`，不是改变原工具轨迹或gold反馈。

P6将真实episode裁到前三个事件，direct threshold=500；从实际发出的包里挑第一个未读目录ref，填入既有 `need-more` 示例；第二次拒绝的保存report中，blocking_reason为 `scope=stage, dimension=calls, consumed=1, requested=1, limit=1`。

未验证真实tokenizer误差、真实摘要质量或效果收益。当前默认估计明确不是token上界；跨进程共享预算不在本次承诺内。所有执行在临时Store完成，本review只写本文，没有修改evidence/model/learning或新增产品测试。
