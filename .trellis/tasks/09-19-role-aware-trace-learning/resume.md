# 恢复检查点

- 当前已规划用户要求的重要性分层轨迹预处理与累计预算，产品基线69980a6，总纲1.7.1；新修订拟1.8.0。
- 原始136事件真实fixture：tests/fixtures/gdpevo_context_train001.json；不运行新的真实模型/benchmark，不改评分器/发布边界/旧TS。
- worker python_learning负责evidence.py与新test_memory_trajectory.py；python_evaluation负责model.py与新test_memory_model_budget.py；blueprint_viewer负责总纲/生成视图及packaged JSON；root负责learning.py、集成测试、示例/规范及最终独立审查。
- 初始task.md契约冻结，变更追加；先真实验收RED及官方mutation后改实现，提交前复验。
- 摘要是派生旁注，必须附已提供原文quote；宿主验证并派生短引用，原文byte-range规则不能放松。
- 当前研究文档尚未commit，均为本会话所写，允许随规划一并提交。
- 用户最新要求直接重写这部分：root将取消旧build_packet→optional_prepare入口，统一新计划→短轨迹直提/有预算局部整理→extract；task/design已有追加。A补段级晚期失败优先RED；C预算18个mutants已通过、窗口释放；B的独立review记录F01回读丢失/F02局部失败丢摘要，作为重写验收。
