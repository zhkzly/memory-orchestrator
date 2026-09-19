# 当前代码架构

核对日期：2026-09-19。以下分别描述保留的 TypeScript 原型与当前 Python 核心；目标契约在 [项目总纲](../../../docs/blueprint/project-contract.json)，实际能力仍以源码和运行证据区分。

## 模块与消费者

| 模块 | 当前职责与调用关系 |
| --- | --- |
| `src/cli.ts` | 命令参数、CLI 流程、Agent 启动、内嵌 review UI；调用 core/config/identity/kb/controller |
| `src/core.ts` | 候选采集、分类、验证、会话摘要、上下文构造、rubric 与清理 |
| `src/store.ts` | Markdown 读写、元数据解析、引用哈希、检索计数 |
| `src/config.ts`、`src/identity.ts` | 配置/记忆根目录与项目/会话身份解析 |
| `src/types.ts`、`src/schemas.ts` | MemoryItem 静态类型及 Zod 输入形状 |
| `src/mcp.ts` | MCP 工具入口；通过 schemas 校验后调用同一 core |
| `src/kb.ts` | 外部知识库注册、关联、检索与读取 |
| `src/controller.ts` | vault 维护建议、结构检查、风险/可逆性判断及提案日志 |
| `skills/`、`examples/` | 产品工作流指导与 Codex/Claude wrapper；不是独立策略所有者 |
| `scripts/harness.mjs` | 隔离临时目录、mock Agent 和 CLI 行为检查 |

依据：[core](../../../src/core.ts)、[store](../../../src/store.ts)、[CLI](../../../src/cli.ts)、[MCP](../../../src/mcp.ts)、[controller](../../../src/controller.ts)、[README](../../../README.md)。

## 当前能力的精确边界

- `summarizeSessionTranscript` 调用 `extractSessionSections`，按 Decision/TODO/Evidence 等标记行提取；尚不能据此声称解析了原生工具轨迹。
- `verifyCandidate` 主要依据记忆种类和 evidence 条数返回状态；`verified` 在该路径不等于语义真值已被独立验证。
- `buildContextPack` 按 personal/project/session/evidence 等层提供内容，并使用条目数上限；不等于已实现模型 tokenizer 驱动的上下文预算。
- `buildContextPack` 会调用 `touchMemoryFiles` 写回计数/时间。它不是无副作用读取；检索计数不证明模型已读取、采用或受益。
- `spawnAgent` 设置 `MEMORY_ORCHESTRATOR_CONTEXT` 等环境变量并启动 CLI；这不独立证明原生模型消费了上下文。
- controller 的 `evaluateProposal` 使用风险、目标、可逆性等结构条件；它没有测量 Skill 更新后的任务成功率。
- 旧 TS 的 `MemoryKind` 为 personal/project/evidence/session；它没有 Python 核心的 Episode、目标修订索引或 Skill 快照，不能将两者混用。

## Python 记忆演化核心

`src/memory_orchestrator/` 是当前独立 Python 库；具体例子见 [调用说明](../../../examples/memory_evolution/README.md)。

| 模块 | 实际职责 |
| --- | --- |
| store / schemas | 本地不可变记录、事实修订、原文/反馈关联、完整资产快照、Schema 与原子提交原语 |
| context / sampling | 任务相关事实、固定库版本与关系范围筛选；先记录单题/微批计划与输入，保存/恢复实际调用，保留所有槽位 |
| lineage / outcomes | 现有消费者共享的本地来源关联、学习闭合和评分资格；区分反馈记录、证据使用与执行终态 |
| trace / goals / evidence | 磁盘增量索引、原文范围与有界依赖回找；缺标用户目标旁注，原始材料不改 |
| model / learning / maintenance | 按显式模型预算提取/补读、失败检索、语义关系维护、能力/必要性比较、归因和提案 |
| feedback | 冻结准则/请求、多标准聚合、有界代理评价、原始返回与费用、恢复处置 |
| candidates | ADD/PATCH/RETIRE/NOOP 与完整资产检查；仅生成候选 |
| verification / assets / relations | 检查义务并集与材料绑定、真实脚本编译/功能执行、依赖完整局部对照及范围化效果 |
| evaluation / release | 原质量集与追加检查分开、可恢复候选比较、选择、完整候选复核/CAS/回退 |
| report / telemetry / experiments | 真实调用/维护/墙钟计量、纵向库及消费报告；相同基线与冻结配置的三臂实验 |
| engine | `evolve()` 组合学习、比较、选择和发布，调用方提供实际执行与评价能力 |

实际实现采用本地文件、普通函数和有界线程池；没有 OS 隔离或硬取消任意 Python 回调的能力。构造测试和真实 SDK 调用分别记录，不能据此宣称原生 Agent 接入或 benchmark 收益。

### LLM、框架与调用方的分工

- LLM 负责局部轨迹摘要、经验含义与边界、语义去重/冲突、原因假设、Skill 必要性判断及候选内容。引用校验通过不等于这些判断正确。
- 框架负责索引/选择/补读、原文引用、请求预算与记账、受限修改操作、对照协议、版本选择、发布和回退；不依据某次评分硬编码业务经验。
- 调用方负责实际任务环境、执行 Agent、工具和可信评分/检查能力。框架通过明确的 execute/evaluate 函数调用，不要求调用方重写演化策略。
- `engine.evolve()` 已连接 learn → compare_candidates → selection → publish；没有候选、证据不足或验证未过时保留相应结果。真实学习运行是否走过这些阶段以及是否得到收益，按逐轮报告确认，不能由入口存在或单元测试数量推导。

首轮冻结实盘停在第一份摘要的引文/修复容量处，见 [重写后诊断](../../../docs/experiments/gdpevo-post-rewrite-pilot.md)。v1.8.1修复后，[同轨迹回放](../../../docs/experiments/gdpevo-evidence-repair-replay.md)已执行提取/归因/候选和四次对照；目标没有提升、回归分数较低，候选未选中、0发布。输入边界修复与学习内容有效性分别记录，不据此重写其它节点职责。

总纲 coverage 逐项对应实际机制与行为检查；完整索引见 [实现证据](../../../docs/blueprint/implementation-evidence.md)。新采样保存批次成员、评分政策及多标准 TaskAssessment；模型证据包含受预算约束的结构关系。比较按唯一快照执行且保留全部别名义务；报告从原始结果读成绩，准入决定另列。构造执行不证明提取准确率、真实benchmark或净维护收益。

## 修改位置

旧TS的修改保持CLI/MCP共用原型核心。Python演化修改遵循上表的实际责任边界；执行/评价函数供给环境证据，不在wrapper另写演化策略。新增字段必须有当前消费者，不能仅把旧字段改名为新能力。
