# Skill 演化论文：固定源码核查

取证日期：2026-09-17。保留固定提交的源码事实与许可观察；未运行作者实验。原来的“先复现/先验证立项”执行建议已被当前总纲替代，不再作为实施指令。原文可从 Git 检查点 db20db8 回查。

## 固定源码事实

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

## 当时的代码复用与许可观察

- Evo-Harness 的 [LICENSE](https://github.com/A-EVO-Lab/a-evolve/blob/3c7c7b8c62a3f07da1d4407aa03f0ca079954bcf/LICENSE) 明确为 MIT；引用或复用时保留相关许可和署名。
- ReasoningBank 的 [LICENSE](https://github.com/google-research/reasoning-bank/blob/ed80611788292ea739f1effd31f16c53823b8a0d/LICENSE) 为 Apache-2.0。
- SkillFlow 的完整树快照未见 LICENSE/COPYING/NOTICE。当前选择是按论文公开协议自行实现，不把仓库代码整段并入项目。
- SkillSmith README 有 MIT 标识，但本次完整树未见独立许可证文件；如后续实际并入源码，应先核清许可文本。
