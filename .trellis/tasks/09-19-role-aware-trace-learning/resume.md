# 完成检查点

- 本轮在69980a6基线上完成轨迹学习入口重写，总纲v1.8.0与prompt/schema包、HTML/context同源；原K/Q/N和后续Skill演化边界保留。
- 原始136事件真实fixture：tests/fixtures/gdpevo_context_train001.json；不运行新的真实模型/benchmark，不改评分器/发布边界/旧TS。
- worker python_learning负责evidence.py与新test_memory_trajectory.py；python_evaluation负责model.py与新test_memory_model_budget.py；blueprint_viewer负责总纲/生成视图及packaged JSON；root负责learning.py、集成测试、示例/规范及最终独立审查。
- 初始task.md契约冻结，变更追加；先真实验收RED及官方mutation后改实现，提交前复验。
- 摘要是派生旁注，必须附已提供原文quote；宿主验证并派生短引用，原文byte-range规则不能放松。
- 研究与规划已提交a91d7c2；模型预算与初始合同已提交26ab29f；后续源与执行证据随收尾提交。
- 用户明确要求直接重写：旧build_packet→optional_prepare入口已移除，统一新计划→短视图直提/有预算局部整理→extract。用户前缀、晚期失败、局部失败保留、续读和真实依赖消费均经独立审查与反例检查。
- 366项完整回归通过；用户放宽参考预算后42项相关检查再绿；66项最终官方故障变体检出。当前参考局部8k/1k×4、提取16k/3k×2，两阶段累计64k/10k，全Teacher12次/160k输入/24k输出。
- 默认token数是估计，预算仅单model实例，初始preview不预留后续份额；额外metadata读取与选择扫描分开报告。没有新的真实模型/benchmark执行，原51次SDK记录不改。完成任务归档后，后续效果实验需另行固定配置与样本。
