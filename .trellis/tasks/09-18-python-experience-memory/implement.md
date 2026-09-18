# 记忆演化核心执行清单（实施中）

文档对齐和草稿清理已完成；本清单把既定节点组织为可验收交付，不另定义演化规则。2026-09-18 用户明确继续，当前 in_progress / implementation_allowed=true，总纲 1.4.1。

## 开工转换（实施开始时一次完成）

- [x] 核对当前用户实施范围，将任务状态、总纲 current_delivery / meta / runtime、恢复笔记和 Python 规范中的阶段说明同步为当前实施阶段；保留旧 TS 和客户端暂缓边界。
- [x] 同步 docs/blueprint/build.mjs 及必要模板：已将校验器、提示和自检改为显式许可状态，不能只翻转 JSON 字段。检查应接受明确的当前许可状态，拒绝缺失或错误类型；生成视图如实显示状态。仅阶段信息变化，不改 N01–N11 的职责和验收条件。
- [x] 重新生成视图，运行下方文档/上下文检查；通过官方 task.py start 启动本任务。将本次总纲版本、起始提交和 M1 范围记入 resume.md。

开工转换涉及当前任务/父任务检查点、必要的 .trellis/spec/ 阶段说明和 docs/blueprint/；它不要求再次设计架构或先证明项目必要性。

## 改动范围与实现次序

产品文件限定在 src/memory_orchestrator/、tests/test_memory_*.py、examples/memory_evolution/ 及实际需要的 pyproject.toml。模型提示词和 packaged schema 跟随 Python 包，保持与总纲一致。文件按实际消费拆分，11 个逻辑节点不对应 11 个服务。

旧 src/*.ts、package.json、现有 CLI/MCP/wrapper 及用户数据保留。execute/evaluate 使用普通 Python 函数；不为未来客户端预建插件注册器、兼容层或调度服务。

### M1：事实、经历与可追溯召回（N01–N02，N04–N05 的存储交接）

- [ ] 落地当前会使用的记录与本地持久化：用户/项目事实、经历、反馈、不可变库快照和 ContextManifest。导入允许未知 task/snapshot/context/feedback；已知身份与项目引用必须校验。
- [ ] 实现显式事实保存/纠正、经历追加和迟到反馈关联；来源事实与派生结果分开，后续学习器无权按 reward 改写用户事实。
- [ ] 先固定库版本，再选择适用 Skill，处理空库、空选择、预算、依赖及声明冲突。记录实际提供内容，不能把提供清单当作使用证明；候选不进入默认召回。
- [ ] 在 tests/test_memory_store.py 和 tests/test_memory_context.py 验证重开持久化、跨项目拒绝、缺失输入、反馈绑定和运行版本固定。N10 的候选发布门在 M3 完成，M1 不另开切换 active 的捷径。
- [ ] 更新 resume.md 中的实际文件/用例/未完成项，审查后提交 M1。下一段以此提交为检查点。

### M2：采样、证据、归因与受限候选（N03–N08，依赖 M1）

- [ ] 系统组织 execute/evaluate 的请求与记录：单例、同题多次、跨题、固定快照批次；每个计划项保留结果、异常或 unknown，不能只保存成功项。
- [ ] 为目标修订和长轨迹建立索引，构造有界 EvidencePacket，允许按引用补读并计入预算；反馈只作用于对应要求/状态。提取经历中的经验及反例，支持多轨迹归集。
- [ ] 按现有提示词/schema 接通模型边界与宿主检查：明确输入、预算、输出、引用校验、未知与失败处理；记录实际模型和用量，不从旧草稿继承隐含默认值。
- [ ] 从经验和当前库选择修改对象，保留归因假设及非 Skill 问题的 NOOP。实现 ADD/PATCH/RETIRE/NOOP、同一 base 的有限多候选、依赖/冲突及附属资产检查；关系分数只供已定义的选择/归因消费者使用。
- [ ] 在 tests/test_memory_sampling.py 和 tests/test_memory_learning.py 验证完整分母、目标变化、预算耗尽、伪造引用、反例、操作越界、候选隔离和 NOOP。模型替身用于检查确定性边界；实际模型调用结果另记，不相互替代。
- [ ] 审查 N03→N08 的真实数据流并提交 M2；此时可以保存候选，不宣称已完成验证发布。

### M3：比较、选择、发布与后续复用（N09–N11，依赖 M2）

- [ ] 冻结 EvaluationPlan/EvalProtocol，明确 execute/evaluate 的语义、案例身份、重复数、准入与选择规则；组织基线/全部候选比较，汇总所有结果和成本。调用形式不决定奖励真值，次数/阈值不由历史教学值自动填充。
- [ ] 分离 ValidationRecord 与 SelectionRecord；测试缺请求、错版本、错案例、重复结果、评分异常及 unknown 的处理，验证期间不写回被测库。
- [ ] N10 核对项目、完整资产、候选、协议、选择、base 与 generation 后原子发布；过期候选不能自动 rebase。回退指向已发布历史并产生新代次；后续召回读取对应版本。
- [ ] 在 tests/test_memory_evaluation.py、tests/test_memory_release.py 和 tests/test_memory_flow.py 覆盖实际函数调用、错误候选发布拒绝、并发/存储失败保留旧版、回退及下一任务复用。
- [ ] examples/memory_evolution/ 提供可直接调用的 Python 闭环示例，带真实执行的本地任务函数与独立检查结果；示例/构造测试只证明其覆盖的行为。效果报告另行固定任务划分与预算，计入学习、失败候选、比较和补救成本。
- [ ] 独立审查全链路的消费者、写入权和失败分支，完成整体验收后提交 M3；复用同一核心进行后续 benchmark，不为运行实验重建系统。

## 验收命令与证据

以下 Python 用例路径是后续交付目标，目前文件未创建，不能报告已经通过；必须检查实际运行的用例数，0 个用例不算验收。

```bash
# 开工转换后以及总纲变更时
node docs/blueprint/build.mjs check
node docs/blueprint/build.mjs verify
node docs/blueprint/build.mjs self-test
python3 .trellis/scripts/task.py validate .trellis/tasks/09-18-python-experience-memory

# 每段实现后，覆盖该段及已完成各段的用例
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v
git diff --check
```

每段记录实际命令、分母、失败、修改路径和提交号；公共契约变化先同步总纲及对应检查，再继续。局部实现失败在当前阶段修复，不丢弃用户数据或改写历史快照；发布失败保留原 active。需要撤回代码时针对该段提交修正，不重置整个工作区。

不把接入 Codex/CLI/MCP、原生日志采集或目录同步作为上述交付的前置条件，也不因此删掉采样/评价/发布能力。旧 pyproject/tests 草稿保存在 db20db8，不成为新 API 或参数依据。
