# 实施与交付顺序

1. [x] 固定O01–O16、共享函数与数据形状，登记生产者/消费者/验收；同步总纲工作状态。
2. [x] A/B/C并行完成各自持有的实际能力；先补会失败的消费者用例，再实施，不留只有schema的功能。
3. [x] 主会话接通任务相关召回、阶段/长期报告与完整实验入口；入口示例及专项可执行用例覆盖新增能力和互斥的正常/未知/拒绝分支。
4. [x] 按原28问题逐条对账，交叉验证正常/失败/歧义/中断/跨版本组合；审查功能义务是否遗漏。
5. [x] 串行官方mutation、全量测试/编译/构造完整流程；必要的受限真实模型接线另记录预算与结果。
6. [x] 对齐HTML与完整证据，分段本地提交；只在16项义务都具备消费者与通过记录后完成本任务。

公共检查：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v`；blueprint check/render/verify/self-test；task validate；git diff --check。

新增行为先观察RED；官方mutation工具需要GREEN基线时，不伪称提前获许可，修正后逐关键边执行并恢复。不同代理的mutation窗口必须串行，禁止对同依赖同时测试/注入。
