# 边界修复的验收记录

工作提交：`41d54de035ebcdc52ef80548318e94f53002f4fd`。命令与原输出保留执行时的活动任务路径；归档后复跑探针时使用本目录中的同名脚本。

本次共享边界修复已完成最终验收。结论限下列机制和条件；完整项目的未实现项与未获得的效果证据仍保留在总纲 coverage。

- 文档反例：`node docs/blueprint/build.mjs self-test` 退出 1；既有 33 个反例命中，新增 4 个完成度反例未被识别，见 `blueprint-red.json`。
- 各模块的真实 RED、GREEN 和 mutation 结果分别由 A/B/C 记录；最终集成结果将在本文件回填。
- 本轮真实模型、网络和 benchmark 调用均不在范围；不据本地行为验收宣称学习收益。

## 修复对应的消费者

| 审查项 | 改动落点 | 区分性验收 |
| --- | --- | --- |
| F02 | `lineage` 解析已知来源，Store 反馈入库消费 | 早到正确反馈可存；错误 run/产物/修订不能 bound；外部未知导入仍合法 |
| F03 | build/expand/validate 共用结构投影，提取/归因收到实际证据 | 同正文而 call/goal 不同，实际 StructuredModel 输入必须不同；结构篡改和预算越界被拒 |
| F04 | 本地组及微批成员闭合，学习入口/父源/检索/历史合并共用资格检查 | 开放时 0 调用 0 学习写入；同一来源闭合后可学习；旧混合污染不能重入 |
| F05 | proposal 尝试与 snapshot 内容分开，比较/选择/发布同步 | 2 个相同内容提案只产生 1 个快照比较；保留两次提案/费用，未冻结别名不能发布 |
| F06/F07 | sampler 保留部分事件并记录初态对照 | timeout/cancelled/budget 的合法事件仍可索引；明确 A/B 矛盾不写成未提供 |
| F08 | report 从计划与原始结果读成绩 | Validation 写入前中断仍显示已保存成绩，验收状态单列 missing |
| F09/F10 | 明确 assessment 关联与报告分组粒度 | 采样质量/用途/模式/终态和 any/all-success；唯一快照、提案、验证尝试分别计数 |
| F01 澄清 | 两条执行路径和发布复核共用 scoring_policy | 非完成但有可验产物的正例保留；严格政策没有评价调用；取消不自动算失败 |

## 已执行的检查点

- 首次全量集成：158 项 Python 检查通过，见 `full-tests.txt`。后续新增同因边界与 schema 等价断言仍需最终重跑。
- 文档：37 个派生负例和 6 个生成视图检查通过，见 `blueprint-green.json`。禁用 coverage 验证的变体被官方工具杀死并恢复，见 `blueprint-mutation.txt`。
- 新增 v2 证据示例由实际 `index_episodes` → `build_packet` 生成，并通过 `validate_packet`/JSON Schema；仍标为教学数据，不是模型效果样本。
- 实际生成 HTML 的 1 段可执行 JavaScript 通过 `vm.Script` 语法解析。浏览器视觉与交互检查未执行，未绕过已有 URL 策略。
- A/B/C 交叉检查及各自 RED/GREEN/故障注入详情见相邻的 `A.md`、`B.md`、`C.md`；C 的独立 A 探针使用真实临时 Store 与有限线程等待，结果见 `C-independent-A-result.json`。

## 最终复核发现的同因中断点

162 项全量检查及构造 demo 已通过后，C 在实际 sampler 的 `put('runs')` 前中断，复现评分已经落盘但报告仍 unknown。原因仍是用生命周期汇总的存在作为读取成绩的前提。现已补齐 Feedback→Assessment 和 Assessment→RunBundle 两个中断点；成绩按冻结槽位及原始身份/反馈读取，缺失汇总和未闭合状态继续保留。不合成 Bundle/Assessment，歧义与错来源仍 unknown，同一材料仍不能学习。探针及前后结果见 `C-sampling-interruption-probe.py`、`C-sampling-interruption-before.json`、`C-sampling-interruption-after.json`。

## 最终验收

| 检查 | 实际结果与工件 |
| --- | --- |
| 全部 Python 行为检查 | **163/163**，退出 0；`final-tests.txt` |
| 构造本地完整循环 | 两轮 proposed、两次发布、新版复用均 pass、一次历史回退；`final-demo.json`。Teacher 是 scripted，不是模型效果实验 |
| Python 编译 | `PYTHONPYCACHEPREFIX=/tmp/memory-boundary-final-pycache .venv/bin/python -m compileall -q src/memory_orchestrator` 退出 0 |
| 总纲 check/render/verify | v1.6.0，K14/Q28/N11 保留，30 records、19 schemas、19 examples；均退出 0 |
| 文档自检 | 37 个派生负例、6 个生成视图检查通过；`blueprint-green.json` |
| HTML 静态检查 | 内嵌 JSON 与源一致，1 段可执行脚本解析通过；`html-static.json`。视觉/浏览器交互未验收 |
| 官方故障注入 | A 10/10，B 11/11，C 11/11；最后受影响报告 6/6（含复验），root 2/2。各记录含命令、原输出和精确恢复哈希，不把重复检查计为新增缺陷 |
| 独立审查 | C复核A的早到/闭合；B复核C别名/发布；A复核B投影/复用；root核对最终报告分支与全链路，没有新确认的本轮阻断项 |
| Trellis / diff | 当前任务上下文验证及 `git diff --check` 退出 0；旧 TS、package.json 与旧 skills 无差异 |

全量命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v`。

构造循环命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python examples/memory_evolution/demo.py`，使用临时 Store，未改用户记忆数据。

最终代码/测试/blueprint 的 34 个文件哈希见 `final-source-hashes.json`，其中 source SHA-256 为 `129ba6c47f740b9f58a4642c04c8e7ed0e1e7ca3811f1503f8ae52e703520cc7`。本轮没有真实模型、网络、benchmark 或原生客户端调用；不据上述结果声称学习收益或全部设计完成。
