# 项目总纲的文档契约

## 1. Scope / Trigger

修改经验学习的目标、节点输入输出、写入权限、不变量或发布条件时使用。唯一结构化来源是 `docs/blueprint/project-contract.json`；HTML 与 Agent 摘要是生成视图。当前代码事实仍由 `architecture-current.md` 及源码说明。

## 2. Signatures

```bash
node docs/blueprint/build.mjs check
node docs/blueprint/build.mjs render
node docs/blueprint/build.mjs verify
node docs/blueprint/build.mjs node N08
node docs/blueprint/build.mjs self-test
```

`check [path]` 可检查一份候选 JSON；其他命令使用项目中的权威源。命令不调用模型、网络或产品运行时。

## 3. Contracts

总纲包含稳定的 K 需求、N 节点、I 不变量、类型记录、边、受限操作、发布状态及中断恢复规则。节点具有输入、输出、写入对象、前后置条件和未知处理。需要退役原需求时显式记录 ID 与理由，不能静默丢失。

v1.1 加入 Q01–Q28 问题对照、逐节点 implementation、runtime、prompts、schemas、examples、paper_sources。模型 Draft 与宿主记录分别命名；示例标记 illustrative_not_measured。JSON Schema 在此是设计产物，不等于产品已执行该校验。

v1.4 要求 current_delivery 及 implementation_allowed 显示在 HTML、context 和 compact node 输出；节点职责、调整清单和评价政策同步生成。演化能力与具体客户端适配分开，参考配置 normative=false，不决定实际运行协议。多候选发布须匹配 SelectionRecord。

v1.6 在每个 Q/N 上分别记录已实现机制、剩余义务、外部职责、行为检查引用和效果证据。节点与 implementation.state 必须一致；仍有待实现项不能标 implemented；旧任务暂停文案不能替代当前机制覆盖。HTML 与简短摘要直接展示这份清单，不用 implemented 数量推导项目完成率。检查器验证声明自洽，不能自动证明其语义真实。

`render` 写 `index.html` 和 `context.md`；两者包含源 SHA-256，不能分别手改。`node Nxx` 默认输出节点、提示词和相关结构索引，供任务按需读取；`node Nxx --full` 才包含完整 schema/示例。避免每次恢复都灌入大量重复结构。

## 4. Validation & Error Matrix

- 空结构或重复 ID → 非零退出，列出字段位置。
- 原需求遗漏、节点/类型引用不存在 → 非零退出。
- active 写入者不唯一、候选绕过检查直达发布、active 迁移缺少条件 → 非零退出。
- 未实现节点被标为已实现但无证据引用 → 非零退出。
- 逐项问题遗漏、模型提示词/输出 schema/论文引用断开、精确候选发布门缺失 → 非零退出。
- 当前范围/暂停状态未定义、职责归属缺失、评价政策与模型模板输入断开、选中候选发布门缺失 → 非零退出。
- 生成 HTML/摘要与当前源或模板不一致 → `verify` 非零退出。

这些检查只约束文档结构和自洽性，不证明节点代码正确或学习有效。

## 5. Good / Base / Bad Cases

- Good：修改明确影响的节点，保留 K 映射和发布条件，重新生成视图。
- Base：无语义变更时 render 可重复，verify 应通过。
- Bad：只改 HTML；删除 K10；让 N08 写 active；增加 N08→N10 的直接边。

## 6. Tests Required

检查真实总纲与其派生错误样本，包括上述遗漏、写入越界、绕过发布检查、无依据实现声明；浏览器另检查实际内嵌数据、节点导航和窄屏布局。数据检查与视觉检查分开记录。

示例另用 Draft 2020-12 校验器检查，结构有效不代表事实有证据。当前浏览器 URL 策略阻止页面，不能通过其它浏览器/服务绕过；仅记录静态检查已完成。

验证导入缺失信息、教学协议/案例/快照的 hash、评价请求覆盖、必需门及选择/发布绑定。正例必须标为假设教学数据；文档演算不能报告为实际任务执行。

## 7. Wrong vs Correct

错误：任务直接读取全部旧研究记录，凭最后一条讨论改写宏观边界。

正确：先读生成摘要与恢复检查点，再按 node 命令读取涉及节点；用户明确改变公共边界时记录来源、影响节点和版本修订，随后再实施。
