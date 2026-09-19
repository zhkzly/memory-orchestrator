# Journal - kelong.zx (Part 1)

> AI development session journal
> Started: 2026-09-18

---



## Session 1: Trellis 0.6.17 接入与经验学习架构草案
<!-- trellis-session: v=2 fp=b2e713b96577978e -->

**Date**: 2026-09-18
**Task**: Trellis 0.6.17 接入与经验学习架构草案
**Branch**: `codex/vault-controller-maintenance`

### Summary

升级官方 CLI，接入 Codex/Claude，按真实 CLI/MCP 代码建立规范，整理经验学习架构并保持 planning。

### Main Changes

- 当前实现、拟议架构、待测策略和效果证据分开；产品源码及原有材料未改。

### Git Commits

(No commits - planning session)

### Testing

- [OK] 版本 0.6.17、两平台、8 个任务上下文条目、语法与链接检查通过；原有 79 文件哈希一致。
- [OK] 仅手动 hook 脚本检查；未运行原生新会话、产品 build/harness 或模型 benchmark。

### Status

[OK] **Completed**

### Next Steps

- 审阅架构任务，固定试点任务、验收来源及预算后，再建立产品实现任务。


## Session 2: 纠正推进方向：按关键节点进行参考实现
<!-- trellis-session: v=2 fp=2ccc76433186458e -->

**Date**: 2026-09-18
**Task**: 纠正推进方向：按关键节点进行参考实现
**Branch**: `codex/vault-controller-maintenance`

### Summary

用户要参考论文和源码实现完整系统，不是先验证项目是否值得做。保留更新检查、回归及发布作为产品逻辑。

### Main Changes

- 增加 K01–K14 用户关键节点记录；修订 PRD、design、implement，改为 M1–M6 模块交付。
- 补明单/多轨迹、目标变更、归因目标、Skill 关系、库版本和库内选择的区别。

### Git Commits

(No commits - planning session)

### Testing

- [OK] implement/check 各 5 个上下文条目验证通过，本地文档链接检查及 git diff --check 通过。

### Status

[OK] **Completed**

### Next Steps

- 按参考实现里程碑落实状态、存储、原子操作和接入契约，随后接通提炼、归因与版本发布。


## Session 3: 项目总纲收敛：形式化来源与 HTML 阅读视图
<!-- trellis-session: v=2 fp=1e6e39f1b3242c3a -->

**Date**: 2026-09-18
**Task**: 项目总纲收敛：形式化来源与 HTML 阅读视图
**Branch**: `codex/vault-controller-maintenance`

### Summary

把 14 项关键需求收敛为 11 个职责节点、19 种记录和 14 条不变量；同源生成 HTML 与约 3.5KB 摘要，保存中断恢复规则。

### Main Changes

- 重复设计转为导航，6 份原文快照保留哈希；默认上下文不再加载整份历史研究。

### Git Commits

(No commits - planning session)

### Testing

- [OK] 文档结构、10 个派生错误样例、过期视图拒绝、内嵌数据、脚本语法和清单检查通过；44 个原有产品文件未变。
- [OK] 浏览器 URL 策略阻止 file:// 页面；未绕过，视觉与交互未实测。

### Status

[OK] **Completed**

### Next Steps

- 从总纲和 resume.md 恢复，按当前节点推进 M1 参考实现；公共边界变化先记录总纲版本。


## Session 4: 清理过期草稿并校正 Trellis 范围
<!-- trellis-session: v=2 fp=80a37838ce99a174 -->

**Date**: 2026-09-18
**Task**: 清理过期草稿并校正 Trellis 范围
**Branch**: `codex/vault-controller-maintenance`

### Summary

保存检查点后清理25个过期文件；旧TS与当前演化总纲保留；后续核心任务暂停且不含旧接口重建；文档与链接检查通过，未运行模型或推送。

### Git Commits

| Hash | Message |
|------|---------|
| `db20db8` | chore: checkpoint evolution design and paused implementation drafts |
| `d2ad776` | chore: clean obsolete drafts and correct Trellis scope |

### Status

[OK] **Completed**


## Session 5: 完成 Python 记忆演化核心参考实现
<!-- trellis-session: v=2 fp=8ae9caeff71e208d -->

**Date**: 2026-09-18
**Task**: 完成 Python 记忆演化核心参考实现
**Branch**: `codex/vault-controller-maintenance`

### Summary

完成M1–M3：事实与经历、长轨迹与反馈、经验及Skill演化、比较选择和发布回退；126测试通过并修复独立审查问题。SDK可用，真实模型生成的候选未改善而拒绝，保留全部取证。旧TS保留，未接native/CLI/MCP，未做benchmark或推送。

### Git Commits

| Hash | Message |
|------|---------|
| `1d1ee99` | docs: activate Python memory core implementation |
| `907eca0` | feat: add Python memory storage and scoped context selection |
| `1b1a869` | feat: implement memory learning, evaluation and version release |

### Status

[OK] **Completed**


## Session 6: 记忆演化共享边界修复与逐项覆盖
<!-- trellis-session: v=2 fp=05dd8eb8769b055a -->

**Date**: 2026-09-18
**Task**: 记忆演化共享边界修复与逐项覆盖
**Branch**: `codex/vault-controller-maintenance`

### Summary

按事实身份/闭合、结构投影、对象与尝试粒度收口，修复审查9项及同因采样报告中断；总纲v1.6逐项保留剩余义务。

### Main Changes

- 统一已知本地来源与学习准入，保留partial事件和评分终态政策。
- 模型接收有界结构证据；唯一快照比较，完整别名发布；报告从已保存事实读取。
- HTML、schema、提示词、Trellis任务与规范同步，旧TS和用户数据保留。

### Git Commits

| Hash | Message |
|------|---------|
| `41d54de` | fix: align memory evidence boundaries and reporting |

### Testing

- [OK] 最终163项Python测试通过，compileall、文档37负例/6视图检查通过。
- [OK] 构造demo完成两轮发布/复用与回退；A/B/C独立交叉复核和官方故障注入通过。
- [OK] 本轮无真实模型、网络、benchmark或原生接入；浏览器视觉验收未完成。

### Status

[OK] **Completed**

### Next Steps

- 依父任务resume与总纲coverage选择后续明确交付；不重做已完成修复，不把当前测试当学习收益。


## Session 7: 完成文档约定的Python记忆演化机制
<!-- trellis-session: v=2 fp=e280046519fe4c01 -->

**Date**: 2026-09-19
**Task**: 完成文档约定的Python记忆演化机制
**Branch**: `codex/vault-controller-maintenance`

### Summary

O01–O16完整实现与消费者验收；268项检查、68项官方故障变体及独立复核通过，真实SDK候选因缺可信材料未发布。

### Main Changes

- 目标关联、磁盘轨迹、反馈聚合、经验维护、必要性、检查计划、脚本与局部关系、初始化/恢复、计量与三臂实验已接通
- 总纲v1.7、HTML、42个Schema/6个提示词与Trellis上下文同步；旧TS保留，原生接入仍暂缓

### Git Commits

| Hash | Message |
|------|---------|
| `9945c31` | feat: complete documented memory evolution mechanisms |

### Testing

- [OK] 268项unittest通过，68/68官方故障变体检出且原hash恢复，Python编译通过
- [OK] Blueprint check/render/verify、37个文档负例、6个生成视图检查通过；未做浏览器视觉QA
- [OK] 真实gpt-5.6-terra：4调用/27747已报tokens，候选验证unknown且0发布；受限网络失败保留

### Status

[OK] **Completed**

### Next Steps

- 正式benchmark、语义准确率与净收益尚未测；需独立冻结数据和协议，当前不自动开始客户端接入或大规模实验


## Session 8: 公开基准小批量上下文诊断与GitHub交付
<!-- trellis-session: v=2 fp=5b5d53ac5fe9a001 -->

**Date**: 2026-09-19
**Task**: 公开基准小批量上下文诊断与GitHub交付
**Branch**: `codex/vault-controller-maintenance`

### Summary

GDPevo group007小批诊断：2任务9执行51SDK调用，修正取证与提示词状态交接，仍未测得收益；302测试/35官方变体通过，0发布且保留probe。用户授权GitHub推送。

### Main Changes

- 按工具调用成组保留返回，修正业务exception误锚及补读目录；Actor每轮看到剩余预算；N07提前收到评价范围
- 保留原始失败与不变评分，记录实体证据链、反馈粒度、泛化Skill、验收语义及不稳定基线等剩余问题

### Git Commits

| Hash | Message |
|------|---------|
| `cee5cc4` | fix: make memory evidence and model context actionable |
| `2204e39` | test: record GDPevo context pilot results and remaining gaps |

### Testing

- [OK] 302项完整检查通过，35项官方故障注入检出且精确恢复
- [OK] 真实SDK51调用，已报409041 tokens另1未知；两轮候选未发布，相同可部署状态令probe明确not_run

### Status

[OK] **Completed**

### Next Steps

- 与用户讨论证据单元/反馈粒度/验收边界；不自动继续烧预算或用保留测试调提示词


## Session 9: Role-aware trajectory learning rewrite
<!-- trellis-session: v=2 fp=a8bd385caecb453f -->

**Date**: 2026-09-19
**Task**: Role-aware trajectory learning rewrite
**Branch**: `codex/vault-controller-maintenance`

### Summary

Unified role-aware trajectory input; grounded local summaries, original excerpts, shared token quotas and actual dependency lookup. 366 full tests, 42 checks after user-approved higher budgets, 66 final mutation obligations. No new live model or benchmark claims.

### Git Commits

| Hash | Message |
|------|---------|
| `a91d7c2` | docs: define bounded role-aware trajectory rewrite |
| `26ab29f` | feat: enforce finite teacher token budgets and local summary contracts |
| `6eacbf7` | feat: rewrite role-aware trajectory learning with bounded summaries |

### Status

[OK] **Completed**
