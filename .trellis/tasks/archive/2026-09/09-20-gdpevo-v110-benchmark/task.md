# v1.10 GDPevo Benchmark
目标：在稳定 provider 前提下，测量 v1.10 记忆演化的 development 候选效果，并守住 test 冻结边界。
不变量：固定产品/contract/GDPevo/model/prompt/evaluator/门槛，结果出现后不改配置。
不变量：复用归档 train001 Episode；新 ledger 只统计本任务真实调用，失败与 unknown usage 保留。
不变量：candidate 才触发 train001/train004 对照；development 通过和重复证据完成前不读 test001。
不做：不为获得正分修改产品，不把 readiness、Teacher 自评或单次最好结果写成 benchmark 提升。
金标：上一轮 call_0006 真实 diagnosis payload、归档 prelearning-store/learning-input、GDPevo 官方 scorer。

## 追加

- 选择：readiness 使用上一轮完整 diagnosis payload，只验证 transport + JSON object；结果 23.46 秒通过，17,721 Token。
- 备选：用短 health/chat 请求或直接重跑整套流程；前者不代表长请求，后者会把 provider 故障混入算法结果。
- 翻案证据：若 development 仍发生 transport error，则本轮保留为运行中断，不据 readiness 推断后续稳定。

- 选择：development 的 `needs_evidence`/0 Candidate 按原门收口，不执行 train001/train004 或 test001。
- 备选：提高 Token 后盲重跑；确定性审计显示 inventory 首次位于第22段，仅小幅加预算不能解决选择顺序。
- 翻案证据：若新的通用片段排序能在同等或明确冻结预算下呈现反馈相关 action/result，再用新实验验证 Candidate 和任务效果。

- 边界澄清：设置阶段读取了 group manifest 和文件名；benchmark runner 未打开或执行 test001 的 prompt/payload/notes/output/evaluator。

- 检查返工：首次完整性脚本取错 `comparison` 层级，首次单测命令缺 tests 导入路径；均为检查命令问题，按实际结构/官方入口修正后 21/21 focused tests 与完整性断言通过，未改产品。
