# 设计

复用 `examples.gdpevo_pilot.run`，不新增实验框架。新 study 从归档 pilot 机械复制 `prelearning-store` 与 `learning-input.json`，用新的空 ledger 和 120 秒 timeout 启动 `stage=revised`。

数据流：归档 Episode → v1.10 Teacher → Experience/Diagnosis/Patch → 若有 Candidate，则 GDPevo train001/train004 base-candidate 对照 → Validation/Selection/Release → report。

公开任务输入给 Actor，私有 evaluator 只在独立评分回调中使用。`test_001` 保留不读。本轮是开发集证据，不声称 unseen 泛化。
