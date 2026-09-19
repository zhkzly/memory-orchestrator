# 执行与验证

1. 完成evidence/model消费边界勘察，确定接口并独立审查设计；更新N04/N06契约。
2. 从真实136事件fixture派生验收，先确认旧路径不能满足新要求；对既有目标文件用官方工具取得mutation执照。
3. 实现确定性分层与有界局部包；检查磁盘/内存一致、目标隔离和原文引用。
4. 实现完整请求累计预算与重试/未知usage计量；局部整理接入learn和上层输入。
5. 同步prompt/schema包、示例配置、总纲及生成HTML；检查真实shape可放入所选预算。
6. 运行针对性验收、独立跨层审查、官方mutation复验，再跑Python完整回归/compileall与总纲check/render/verify/self-test。
7. 分阶段commit，记录行为证据和效果边界，更新规范并归档任务。

参考命令：PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -v；python3 -m compileall -q src/memory_orchestrator；node docs/blueprint/build.mjs check|render|verify|self-test。无真实模型调用。
