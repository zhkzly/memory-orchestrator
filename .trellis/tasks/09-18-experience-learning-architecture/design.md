# 架构设计入口

目标架构已收敛到一个结构化总纲，本文件只导航，不再维护第二份设计。

- [离线 HTML 总纲](../../../docs/blueprint/index.html)
- [唯一结构化来源](../../../docs/blueprint/project-contract.json)
- [自动生成的执行摘要](../../../docs/blueprint/context.md)
- [当前实施清单](implement.md)
- [恢复检查点](resume.md)
- [收敛前历史快照](../../../docs/history/2026-09-18-pre-blueprint/README.md)

修改公共边界、节点输入输出、发布条件或不变量时，先修订结构化来源及版本记录，再运行：

```bash
node docs/blueprint/build.mjs check
node docs/blueprint/build.mjs render
node docs/blueprint/build.mjs verify
```

查看当前任务相关节点：`node docs/blueprint/build.mjs node N08`。

形式化文档不是实现正确性的证明。总纲约束目标，源码说明当前能力，行为检查提供实现证据。
