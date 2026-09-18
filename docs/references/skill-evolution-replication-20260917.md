# 现成 Coding Agent 的 Skill 演化：论文与代码复现对照

日期：2026-09-17。证据范围：作者仓库的固定提交、关键提示词、执行器与论文。只读源码调研，未安装上游依赖，未运行模型或基准；下述改造尚未实现。

结论（选型置信度高；预期效果未知）：第一版先复现 SkillFlow 的“现成 Agent 执行 → 轨迹与验收反馈 → Skill 文件补丁 → 后续任务使用”协议。先测出这一基础机制的收益或负收益，再单独引入 Evo-Harness 的批次整理；SkillSmith 的候选筛选作为另一条明确区分的增强路线。

## 1. 本轮问题与取证方式

1. 论文的反馈、反思、Skill 修改和后续使用在代码中如何连接？
2. 哪条路线适合 Codex、Claude Code 等现成 Agent？
3. 当前项目需要补哪些最小能力，才能复现并测量效果？

使用论文作者链接、GitHub API 和火山检索交叉定位仓库。SkillFlow 有同名的检索系统，本次只研究 arXiv:2604.17308 对应的 ZhangZi-a/SkillFlow。完整固定提交与文件入口见同目录 sources 清单。

## 2. 代码证据

### SkillFlow：最贴近现成 Agent 的基础路线

固定提交：`7b49ff5a7e26cd7706e959bfa0dba4746d18440d`。

- [共享目录挂载](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/terminus_env/environments/shared_skills_env.py#L15) 将一个任务族的 Skill 目录挂到容器内多个客户端目录，包括 Claude 和 Codex。这里证明的是上游基准的容器接入方式，不是本机所有客户端版本已验证。
- [Agent 适配器](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/harbor_noinstall_agents/agents.py#L7) 基于 Harbor 的现成 CLI 适配器；[组配置](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L487) 固定任务顺序并让同族 trial 串行。
- [任务结束回调](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/iterative_shared_skills_runner.py#L630) 读取标准轨迹、任务结果和 verifier 记录，再将当前 Skill 快照与精简结果交给 patcher，随后直接应用文件补丁并保存差异历史。
- [输入/输出与提示词](https://github.com/ZhangZi-a/SkillFlow/blob/7b49ff5a7e26cd7706e959bfa0dba4746d18440d/libs/skill_evolution/patcher.py#L310) 要求提炼可复用操作，优先修订已有 Skill，允许空补丁。产物仅用 summary、upsert_files、delete_paths 表达。

重要边界：这条路径没有逐补丁的独立任务回归准入。后续任务继续使用更新库，整体收益在实验层评估。“每个补丁先跑 A/B 才可写入”不是该方法的原始行为。

### Evo-Harness：批次反思与整理

固定提交：`3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf`，作者论文指定 `release/evo-harness` 分支。

[CL-Bench 实现](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/evo_harness/cl_bench.py#L1187) 在失败后利用 Solver 原会话提出候选，批次 Curator 决定接收、合并或跳过，并从跨上下文失败提炼通用规则。它使用上下文相关与通用两层 Skill；检查到的 CL 注入路径使用前者正文和后者描述，不能一概写成所有 Skill 全文注入。

[论文启动脚本](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/scripts/run_cl_evolve.sh) 显式启用 `--no-retest`；同文件函数还支持重试失败任务的另一模式，复现时必须区分。[SWE Solver](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/agent_evolve/agents/swe/react_solver.py#L231) 是自有 ReAct/API 执行循环，不能把整个仓库当作现成 Codex/Claude 插件直接装入。

适合后续单独验证：当逐任务 patch 出现重复或碎片化时，增加批次整理、容量限制及合并。

### SkillSmith：有实际候选验收，但运行时更重

固定提交：`2cbbd37c5293c3c06f1f5efc5709382639763cfa`。

[主循环](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L80) 生成候选 Skill/工具 bundle，创建候选状态，经启用的检查后进入验证与 frontier 选择。[具体检查](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L164) 包括失败任务改善、capability holdout 和验证集回归判断；这些调用依赖配置，并非不可关闭。

[评测入口](https://github.com/yangforever17/SkillSmith/blob/2cbbd37c5293c3c06f1f5efc5709382639763cfa/src/skillsmith/loop.py#L351) 实例化自身 SkillSmithAgent。因此，它提供了上一轮讨论中“候选—评测—选择”的参考，但要服务现成 CLI，需要另接执行适配，不能假定直接兼容。

适合后续单独验证：是否用更多评测成本换取更少的坏 Skill 更新。

### ReasoningBank：有用的记忆基线

固定提交：`ed80611788292ea739f1effd31f16c53823b8a0d`。

[README](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/README.md) 与 [SWE 入口](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/SWE-Bench/run.sh) 使用 WebArena 和修改后的 mini-swe-agent 实验路径。论文的策略记忆机制可作对照，但并未提供本项目所需的现成 Coding Agent Skill 文件更新接口；本次未审计其全部实现。

## 3. 第一版应忠实复现什么

先保留一条简单链：

```text
一个任务族，固定任务顺序与模型配置
→ Agent 在新任务环境中读取当前 Skill 目录
→ 执行任务并留下可见轨迹
→ 收集真实验收结果
→ 用轨迹、反馈和 Skill 快照生成文件补丁
→ 保存旧快照并更新实验 Skill 目录
→ 下一项任务使用新版目录
```

同族共享 Skill，任务会话和环境重新开始；不同实验组各有独立库。记录第一次执行结果，不能用学习反馈后的同题重试覆盖它。

参考 SkillFlow 的三个补丁字段即可。下面是本次编写的接口示意，不是论文中的真实实验产物：

```json
{
  "summary": "将已观察到的验收遗漏提炼为可复用的检查步骤",
  "upsert_files": {
    "artifact-validation/SKILL.md": "<完整 Skill 文件内容>"
  },
  "delete_paths": []
}
```

不需要先引入向量数据库、知识图谱或通用记忆管理。现成 Agent 通过自己的 Skill 机制使用这些文件。生成文件与实际读取是两项证据，实验应同时记录 Skill 版本和观察到的使用事件。

## 4. 从研究代码到日常接入：明确区分新增选择

以下是本项目的适配建议，不能标成上游论文原设计：

- 日常会话必须有可信反馈入口：实际测试结果、外部验收或明确用户纠正。模型说“完成了”不自动等于任务成功；缺少结果或基础设施异常保留 unknown，不当作失败经验训练。
- 先在独立实验目录应用 patch，保留快照和差异；检查写入路径属于该目录。SkillFlow 的 apply_patch 是直接文件操作，不能直接照搬到用户的全局 Skill 目录。
- 日志适配负责把两种客户端的可见交互转为统一记录。上游 Harbor 回调属于评测框架，不能冒充 Codex/Claude 原生 session-end hook；本机客户端的安装、刷新、捕获机制要另行核实。
- Evo-Harness 批次整理、SkillSmith 准入与回归门分别作为后续实验变量，不在第一版混成“论文复现”。
- 第二个客户端先证明格式和执行接入兼容；同一套 Skill 在不同客户端/模型上是否迁移，是独立效果问题。

## 5. 对当前 Memory Orchestrator 的最小改造建议

当前已有 CLI、MCP、vault 配置、来源记录和维护报告，适合作为接入与存储基础。需要补齐的行为是：

| 所需行为 | 当前边界 | 建议 |
| --- | --- | --- |
| 接受一次可复现的任务结果 | 当前 session summary 主要提取标记行 | 接受可见轨迹、验收结果、证据引用和使用的 Skill 版本 |
| 根据结果修改可复用策略 | 当前 verify 主要检查证据数量，controller 主要做记忆维护 | 增加独立的 patch 生成流程，输入与输出先按 SkillFlow 固定 |
| 让现成 Agent 使用产物 | 当前 wrapper 主要输出上下文环境变量 | 交付标准 Skill 目录，实际验证客户端读取 |
| 分析是否值得继续演化 | 当前结构分不代表任务表现 | 用任务完成、成本与回归记录比较有无更新 |

保留已有通用记忆功能，不把 Skill 文件硬塞成 personal/project/evidence/session 四类记录的一种；本次没有决定删除任何现有功能。

## 6. 最小实验与停止条件

第一步是流程复现：选 SkillFlow 中一个可本地执行的任务族，冻结实例、顺序、模型、起始 Skill 库、执行预算与 verifier。运行“无 Skill 更新”和“逐任务 patch”两组。初始库必须实际存在且内容明确，不能只凭 README 的模板路径假定资源齐全。

第二步再扩展任务族、任务顺序和重复次数，检查收益是否稳定；若引入批次 Curator，增加独立第三组。所有组都报告 Solver 与更新器各自的 token/耗时/成本；另提供总预算匹配对照，防止把额外计算误认为更好的学习机制。

正向指标：后续任务的首次完成率、解决步骤、成本；负向指标：原本能做的任务变差、规则污染、Skill 膨胀及更新失败。SkillFlow 已报告部分配置退化，因此必须允许无收益或负收益结论。

若补丁经常生成，但后续任务没有更好，先分析反馈质量、适用范围和实际使用，不继续增加存储与检索功能。小规模流程跑通仅证明集成，不能直接写成泛化提升。

## 7. 代码复用与来源

- Evo-Harness 的 [LICENSE](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/LICENSE) 明确为 MIT；引用或复用时保留相关许可和署名。
- ReasoningBank 的 [LICENSE](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/LICENSE) 为 Apache-2.0。
- SkillFlow 的完整树快照未见 LICENSE/COPYING/NOTICE。当前选择是按论文公开协议自行实现，不把仓库代码整段并入项目。
- SkillSmith README 有 MIT 标识，但本次完整树未见独立许可证文件；如后续实际并入源码，应先核清许可文本。
- 本文提出的是带归属的复现与工程适配，不声称算法原创或已获得上游论文的效果。

## 8. 本次交付与未完成项

已完成：固定四个仓库版本、读取关键路径、对照提示词和更新语义、确认最适合现成 Agent 的基础协议，并形成改造与对照方案。

未完成：产品代码实现、上游依赖安装、真实 CLI 端到端运行、模型调用和收益实验。这些没有用静态检查替代。
