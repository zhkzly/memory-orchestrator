# 执行计划

1. 核对 contract v1.10.0、产品 commit、GDPevo checkout、归档学习输入及上一轮 diagnosis payload hash。
2. 在任务 research 目录写不可变 readiness plan，用新 ledger 发送一次代表性长请求并生成机器可读 summary。
3. readiness 通过后，创建独立 development study，复制归档 Store/input 和空 ledger 配置，运行现有 `stage=revised`。
4. 汇总 Experience、Diagnosis、Candidate、train001/train004 base-candidate 结果、Validation/Selection/Release 和完整调用成本。
5. 若 development 发布成功，再固定重复计划并执行；重复证据完成后才运行现有冻结 `stage=probe`。否则明确记录未启动原因。
6. 运行 task validate、blueprint verify、结果一致性检查与 git diff 检查，写自包含报告；不根据结果修改产品。
7. 提交实验材料并推送当前远端分支。
