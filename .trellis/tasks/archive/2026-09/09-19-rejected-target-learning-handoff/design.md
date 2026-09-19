# 拒绝target的显式下一轮交接

## 最小行为

`evolve()`仍只执行一轮。比较完成且SelectionRecord为`keep_current`时，framework读取本轮被冻结的plan/validation/result/return，只投影满足以下全部条件的请求：candidate臂、case split=target、对应ValidationRecord=rejected、执行completed、评价已知且绑定。结果写入新Episode+adaptation Feedback，并将稳定ID放进`next_episode_ids`；不自动调用`learn()`。

调用方下一轮执行：

```python
first = evolve(...)
second = evolve(store, first['next_episode_ids'], new_model, ...)
```

这是一条机器可读交接边，不是调度器。每轮预算、case set和版本仍由调用方冻结。

## 来源与防伪

Episode新增source.kind=`rejected_target_evaluation`，reference指向实际EvaluationReturn ID。普通`provided_material`或`execution_function`继续禁止引用comparison return。

framework从原记录重建预期Episode：

- task来自EvaluationReturn保存的public target case；
- snapshot来自冻结request，必须等于candidate digest；
- instruction和result为宿主边界事件；中间events逐项复制实际return并使用evaluation return范围作为source_ref；
- Feedback使用实际EvaluationResult的score/outcome及ValidationRecord失败门，visibility=adaptation；
- source resolver重新核对plan/case split/arm/result/return/validation/selection及Episode字节投影。

只有上述重建完全相等时`require_learning_source()`准入。不能把任意selection_only返回换个reference伪装成外部输入。

## 隔离规则

- target在本轮转换后已成为adaptation材料，后续不能称为未见测试；回归和final不转换。
- 未知/未完成执行、unknown validation、selected candidate和blocked comparison不生成Episode。
- active pointer及候选快照均不变；Episode引用未发布candidate snapshot仅用于分析，不等于部署。
- 新Feedback不携带私有criteria或参考答案，只保留公开score/outcome、失败门和来源ID。

## 修改边界

- `evaluation.py`：确定性重建、授权检查和幂等写入。
- `lineage.py`：新增source kind的严格准入；保留旧comparison-return拒绝。
- `engine.py`：初始化/返回`next_episode_ids`，只在keep_current后调用交接。
- `project-contract.json`及生成schema/views：Episode source枚举和N06/N09回边；prompt不改。
- `tests/test_memory_rejection_learning.py`及真实派生fixture；现有测试只在契约需要时同步。

不修改learning提取、补读、候选生成、评价门、release、sampling或GDPevo评分器。
