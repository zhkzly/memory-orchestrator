# 验证与效果证据

## 已有检查入口

[package.json](../../../package.json) 声明：
- `npm run build`：TypeScript 编译到 dist。
- `npm run harness`：运行 `scripts/harness.mjs`。
- 未声明独立的 npm test 或 lint 命令；不要在报告中虚构这两项已通过。

[harness](../../../scripts/harness.mjs) 创建临时 vault/home/wiki/workdir，使用 mock Agent 检查 CLI 与 wrapper 行为，并运行内部 rubric。它可以支持集成行为判断，不能证明真实 Codex/Claude 的学习收益。

本轮未安装项目依赖，node_modules 中的 TypeScript/tsx 不存在；本轮不宣称 build/harness 通过。后续产品实现任务按 package.json 准备依赖并记录版本后再运行。

## 证据层级

Python 核心使用 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_memory_*.py' -v` 和 `python3 -m compileall -q src/memory_orchestrator`。调用示例 `examples/memory_evolution/demo.py` 默认使用 scripted teacher 与真实本地 CSV 回调；这仍是构造集成检查。真实 SDK/学习调用另存配置、预算、源码 hash 和结果；NOOP、失败及未发布均保留。

模型/回调的 tokens 只允许非负整数或 null；非法测量保存原文与诊断后记为缺失。报告按唯一 usage_id、阶段和币种统计，输入/输出/total token 分开，不重复求和；不完整计划不能宣称成本完整。final/validation 轨迹和共用统计不能流入学习。

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
- target评价在Selection完成后若被明确转为下一轮adaptation Episode，该target从此不再作为未见验证证据；regression/transfer/final及其详细轨迹不写回学习。交接只返回Episode ID，不在同一验证周期自动重试模型或改门槛。

## Trellis 接入验证

本轮使用 Trellis 自身的版本、platforms、packages、task validate 和 update dry-run 检查配置/导航。直接运行 hook 脚本只证明脚本可执行；原生会话中的实际触发及用户批准状态需要另外验证。
