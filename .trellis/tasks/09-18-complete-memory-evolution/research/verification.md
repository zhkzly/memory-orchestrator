# 完整交付验收记录

2026-09-19。基线81c162f；任务为实现原定完整Python记忆演化，不删减功能或以MVP结项。O01–O16的输入→处理→实际消费者→行为证据见 [稳定实现索引](../../../../docs/blueprint/implementation-evidence.md)（归档后从仓库根的同一路径进入）。

## 最终检查

- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v`：**268/268通过，65.457秒**，原始日志full-tests-final.txt。
- `python3 -m compileall -q src/memory_orchestrator examples/memory_evolution`通过；源码/文档diff空白检查通过。原始unittest失败日志有6处输出行尾空格，保留原字节并在提交空白检查时只排除这些原始测试输出；没有改写失败证据。项目没有另外配置Python lint/type-check任务，不虚构其结果。
- 官方mutation：**68/68检出并精确恢复**。A18、B20、C18、root12；每项都是原GREEN→注入后RED→工具按原字节恢复→GREEN。命令、原始输出和hash分别保存在A-mutation-results.json、B-mutation-evidence/results.json、C-mutation-results.json、root-mutation-evidence/results.json。窗口完全串行。
- 总纲v1.7：14要求、28问题、11节点、17不变量、6提示词、42Schema和19设计示例保留。check/render/verify通过，self-test的37个结构负例和6个视图检查通过；HTML内嵌JSON与脚本语法通过。最后文案/记录概要改动只更新打包源hash；另验同源契约，不重写运行schema/prompt正文。
- 当前源码/测试/协议/文档使用同一消费者；Trellis implement/check上下文各8条校验通过。
- 没有原生客户端/CLI/MCP适配，没有改旧TS，也没有浏览器视觉QA或正式benchmark。

## 实际SDK接线

使用gpt-5.6-terra、localhost:8317/v1、环境OPENAI_API_KEY；最多8次调用、每次4000输出token、累计480000输入字符、30秒单次timeout，SDK无隐式重试。一轮构造CSV任务。

- 受限环境首次发生APIConnectionError，完整失败账本保留在live-canary-restricted；这是执行环境证据，未据此修改模型配置或产品。
- 在允许访问本机服务的环境中实际4次调用，78.401861秒；已报输入23956/output3791/total27747 tokens。没有价格，费用未知；本地执行回调的未知token未被补成0。
- 提取、语义维护、归因和提案实际返回，生成1个候选并执行对照。4个检查义务通过，2个必需义务没有可信材料引用，VerificationRecord和ValidationRecord为unknown，**0发布**。没有补造材料、删检查或降低门槛。
- summary、原始模型结果/usage/errors/candidates/validations/releases/验证计划与结果存live-canary；源hash与配置在summary中。live检查源hash为当时文档元数据版本，后续只调整文案与打包来源hash，模型schema/prompt正文和执行代码未改变。

这证明一次有限的实际SDK/学习/准入交接，不证明模型学习收益。正式benchmark、语义提取准确率、未见任务与全成本收益仍未知。

## 独立复核与根因修复

A↔B/C、C→A复核记录及可重跑探针分别见A-review-B、C-independent-review、C-review-A；B-review-root保留两条原P2和关闭复核。

过程中保留并修复的实际反例：跨层未索引父来源绕过禁学；候选别名义务顺序不稳定；公共任务混入私有验收字段；追加高分检查稀释原质量目标；provider明确费用跨层丢失；外部配置引用影响已冻结实验臂；中断模型周期误报完整成本及provider等待混入本地维护。相应RED记录未删除。

初次全套出现的旧report失败源于新冻结ID与旧legacy假设混用。修正真正legacy fixture并保留其歧义unknown；新计划只按精确反馈ID恢复，外来不同ID不覆盖本次原结果。项目/run/state/revision矛盾与未闭合禁学检查全部保留，20项report专项和最终全套通过。

## 复盘

此前偏差的根源是把“主线能运行”当成“原文档全部功能完成”，实现分解与验收未逐项约束生产者/消费者。本轮固定16项义务，再按已确认范围实现；语义判断正确率及benchmark效果留在独立效果列，不与功能缺失混写。

新增约定已回填python-learning.md、architecture-current.md和project-contract.md：原质量集必须固定；配置冻结须约束实际读取对象；异常调用保留未知且避免维护时间重复计量；新/旧记录的恢复依据不同；Schema内嵌定义须与独立定义等价。未新增未来服务框架或原生集成前置条件。
