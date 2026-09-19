# 固定执行设计

直接使用已有examples.gdpevo_pilot.run.main，不修改产品或另写执行框架。新的research/pilot目录作为独立study；baseline stage负责新任务执行、保存prelearning-store、学习和原候选比较。SDK设置通过既有显式budget manifest传入；空初始ledger用于核对0次旧调用，再使用calls-live记录真实调用。程序原有不可覆盖阶段、私有评价隔离、原始返回保存与预算拒绝均保持。

源commit/数据commit、全部有效配置、提示词摘要与实现文件hash由已有plan记录。根代理监控真实进度，独立审查只读产物，不另外发模型请求。运行结束后分析Teacher输入/输出、真实评分、候选准入与统计口径，不把构造测试或人工审查算作benchmark样本。
