# 初始化 Memory Orchestrator 开发规范

## Goal
根据当前 CLI/MCP 原型建立真实可用的 Trellis 规范，替换初始化误识别出的前端模板。

## Scope
- 规范：.trellis/spec/backend/ 与 .trellis/spec/guides/。
- 证据：src/、package.json、tsconfig.json、scripts/harness.mjs、README、evaluation/README。
- 不改产品源码，不安装项目依赖，不运行模型或 benchmark。
- 未来经验学习系统的设计归独立 planning 任务管理。

## Acceptance
- [x] 规范描述真实模块及源码依据，列出现有摘要/验证/上下文/维护行为的限制。
- [x] 类型、Zod、Markdown 序列化与 CLI/MCP 消费者的同步边界明确。
- [x] 已删除不适用前端模板；index 指向实际规范文件。
- [x] 真实源码及样例引用已加入；不包含模板占位内容。
- [x] Trellis 与产品 Skill 的不同所有权明确。
- [x] 产品编译/harness 未运行的事实已记录，未把文件创建当作学习收益。

## Verification
后续命令与逐项结果记录于 docs/planning/2026-09-18-trellis-architecture/verification.md。
