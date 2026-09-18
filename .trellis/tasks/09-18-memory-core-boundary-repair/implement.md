# 执行清单

- [x] A：事实与生命周期。对照 F02/F04/F06/F07，先补跨节点反例；收口已知源关系、组闭合与部分轨迹，固定现有评分政策，提供单一评估关联给报告消费。
- [x] B：证据投影。对照 F03，保持 call/goal/role/parent 等已知结构；同步生成/补读/验证、Schema/示例和模型可见预算。
- [x] C：候选与报告粒度。对照 F05/F08/F09/F10，保留尝试账本、比较唯一快照、从原始结果重建报告；统计终态、purpose/mode、唯一候选与验证次数。
- [x] D：整体审查。跨边界验证原 9 项与同因合法场景，检查新共享函数的实际消费者和未增加的抽象；局部检查后分段提交。
- [x] E：总纲/HTML与任务。更新实现覆盖与证据，清除旧暂停文案，逐项保留未接通能力；不靠删要求达到“完成”。

责任划分：存储/采样与共享源关联、证据/学习、比较/发布/报告分别由实现者负责；主会话负责契约、Schema/打包同步、全链路测试和文档。共享文件先协商交接，禁止互相覆盖。

检查入口：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v
node docs/blueprint/build.mjs check
node docs/blueprint/build.mjs verify
node docs/blueprint/build.mjs self-test
python3 .trellis/scripts/task.py validate .trellis/tasks/09-18-memory-core-boundary-repair
git diff --check
```

改动前用实际探针衍生测试观察 RED；GREEN 后使用官方 mutation_license.py 逐关键绑定检查，工具自己按原字节恢复。不同 worker 不同时做依赖相交的 mutation。新增/修正行为的许可工具要求绿色基线，不能把原来的红测伪装成验收绿；提交前保留执行记录与实际范围。
