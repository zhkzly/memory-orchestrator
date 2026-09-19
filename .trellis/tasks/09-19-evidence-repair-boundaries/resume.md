# 当前检查点

- 总纲：当前v1.8.0，目标v1.8.1；只同步N04/N06固定字段来源、summary提示词必要披露及参考容量，其他节点职责不变。
- 节点：N04证据索引、N06局部学习；N07–N10只做边界回归，不预设修改。
- 允许路径：design.md列出的evidence.py、run.py、新反馈/修复测试与真实fixture、总纲及生成物、职责/实验/spec/任务记录。
- 独占编辑：feedback_text_fix负责evidence.py和test_memory_feedback_text.py；根代理负责run.py、test_memory_summary_repair.py及fixture、任务记录；blueprint_viewer负责总纲与生成物。
- 已完成：固定字段来源、12k容量及对应红绿/mutation；双视图挤压已用同反馈共享选择单元修正。原42k GDPevo供证5/5恢复，相关108/108绿，反馈21/21绿；新增7个mutation全检出。源已冻结。
- 下一步：全部test_*.py完整回归和独立复审正在执行；通过后总纲回填机制状态，冻结新版并启动一次有界实盘。原失败和首差日志保留，未增加生产packet预算或删业务断言。
- 实盘约束：同一train001学习经历；最多新增4个开发对照执行、36次SDK调用、300万输入字符、120秒/请求、无自动重试；test001不运行，不使用gold调试。
- 发布：只本地commit；公开原始实验日志未获明确授权，不push。
