# 设计

## 边界

本任务复用现有 `examples.gdpevo_pilot.run` 和 v1.10 普通 `evolve` 路径，不新增产品能力。允许写入当前任务目录下的 plan、ledger、Store 副本、结果与报告；禁止修改产品代码、prompt/schema、评分器、GDPevo 数据和既有归档。

## 三道顺序门

1. **Provider readiness**：把上一轮 `diagnose_v1` 失败请求的完整 payload 原样发送到同一模型。transport 返回、`finish_reason` 存在且正文能解析为 JSON object 才通过。这里只判断服务能否承载代表性长请求，不评价诊断语义。
2. **Development candidate**：机械复制归档的 `prelearning-store` 与 `learning-input.json`，新 ledger 从 0 开始，运行 `stage=revised`。Teacher 输出经 N06–N08 的原检查进入候选；有候选才由 N09 比较 train001 target 与 train004 regression，N10 按原门决定是否发布。
3. **Repeated/frozen evaluation**：只有 development 发布成功才创建重复计划；重复运行保持同模型、任务、预算和 scorer，并保留全部请求。重复证据完成后，才允许现有 `stage=probe` 读取 test001，比较空基线与已发布记忆。若前一道门不通过，后续阶段记录为 `not_started`，而非 0 分。

## 数据与声明

公开任务输入进入 Actor；私有 criteria 只交给 GDPevo 官方 scorer。学习只消费归档 train001 Episode；train004、test001 轨迹不回流。报告同时给出任务分数、候选/发布状态、请求分母、失败与 unknown usage；development 结果只支持局部修复声明，test 才能支持冻结未见任务声明。

## 停止条件

- readiness 一次失败：停止并报告 provider-blocked。
- development 出现 transport error：保存部分状态并停止；不在同一实验中换模型、缩 prompt 或调 timeout。
- NOOP/abstain/无候选/被拒：这是有效实验结果，停止后续 test。
- 只有发布成功才进入下一门；任何新配置都必须成为新的实验版本。
