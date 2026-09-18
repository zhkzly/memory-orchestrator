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
