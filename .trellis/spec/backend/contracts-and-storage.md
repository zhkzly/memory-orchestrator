# 契约与存储

## 当前事实

项目启用 TypeScript `strict`、ES2022 和 NodeNext；源码 import 使用 `.js` 后缀。见 [tsconfig](../../../tsconfig.json) 和 [core](../../../src/core.ts)。

`MemoryItem` 的类型在 [types](../../../src/types.ts)，运行时 Zod 形状在 [schemas](../../../src/schemas.ts)。MCP 入口使用这些形状；产品也有 [schema.json](../../../schema.json)、[工具说明](../../../tools.md) 和 `src/tools.ts`。修改字段前先查真实消费者，不假定这些表述天然同步。

[store](../../../src/store.ts) 把 JSON 元数据放在 Markdown 的 `---` 区段中，并保存 Claim/Metadata/Provenance 等正文。解析器要求对应的分隔形状，并优先读取正文 Claim。它不是任意 YAML 解析器。

## 开发规则

- 字段变化应同时核对类型、Zod、序列化、解析、CLI/MCP 以及调用方文档。
- 现有 `scope` 是字符串；不能把它当已实现的目标版本关联。新数据契约需要明确迁移或独立存储方式。
- `confidence` 是记录中的数值，不自动具有校准概率含义。
- evidence 的来源哈希可用于检测内容漂移；不能把文件存在或哈希相符当成事实主张正确。
- `writeMemoryItem`/`saveMemoryItem` 当前是文件写入，不宣称多文件事务。未来库快照与 active pointer 的发布语义须按设计另行实现。
- 原生轨迹缺失、截断、消费情况不明必须显式记录；未知不能默认为成功或未使用。
- 不在归一化中补造不可见的工具返回、隐藏推理或初态。
- 普通模型判断、用户事实确认、测试结果分别保留来源。旧 `verified` 不能自动迁移为新的执行效果认证。

## 例子与验证入口

现有文件形状可参考 [test-fixtures](../../../test-fixtures/README.md) 以及 [harness](../../../scripts/harness.mjs) 中实际写入和读取的样例。新协议需要新增真实来源的样例和相应验证；本轮未创建新运行时 schema。
