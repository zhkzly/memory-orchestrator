# 验证与效果证据

## 已有检查入口

[package.json](../../../package.json) 声明：
- `npm run build`：TypeScript 编译到 dist。
- `npm run harness`：运行 `scripts/harness.mjs`。
- 未声明独立的 npm test 或 lint 命令；不要在报告中虚构这两项已通过。

[harness](../../../scripts/harness.mjs) 创建临时 vault/home/wiki/workdir，使用 mock Agent 检查 CLI 与 wrapper 行为，并运行内部 rubric。它可以支持集成行为判断，不能证明真实 Codex/Claude 的学习收益。

本轮未安装项目依赖，node_modules 中的 TypeScript/tsx 不存在；本轮不宣称 build/harness 通过。后续产品实现任务按 package.json 准备依赖并记录版本后再运行。

## 证据层级

1. 形状/类型：字段、路径、协议是否匹配。
2. 确定性执行：编译、脚本、测试和产物是否满足所检查的条件。
3. 原生接入：指定客户端实际接受资产，并有可观测事件。
4. 学习收益：旧版/新版在独立任务上的结果、回归和完整成本。

前一层通过不能代替后一层。多个 reviewer 对同一日志投票不是多次执行；同题重试不算多个独立任务。

## 评分规则

[evaluation/README.md](../../../evaluation/README.md) 要求先定义 rubric，再收集 evidence，再评分，不能同一轮同时改三者。保留这一审计顺序。

未来正式实验必须先固定任务划分、允许的反馈、预算、失败/未知处理及比较对象：
- 在线：先记录当前题成绩，再允许该题反馈影响后题。
- 冻结：测试时不更新记忆。
- 候选选择用的验证集不是最终未见测试集；报告逐题救回和回归。
- 所有执行、提炼、失败候选、验证及补救成本均入账。

## Trellis 接入验证

本轮使用 Trellis 自身的版本、platforms、packages、task validate 和 update dry-run 检查配置/导航。直接运行 hook 脚本只证明脚本可执行；原生会话中的实际触发及用户批准状态需要另外验证。
