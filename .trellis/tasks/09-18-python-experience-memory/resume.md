# 产品实施检查点

- contract_version：1.4.1；status：in_progress；implementation_allowed=true。
- 用户在实现就绪说明后明确“继续吧”，从 ffb1709 开始实施；不再沿用旧暂停条件。
- 当前阶段：开工状态同步与 M1；M2 证据/模型边界和 M3 比较/发布按独立文件并行准备，整体验收仍按 M1→M2→M3。
- 核心保留：事实/经历、长轨迹、反馈、提取/归集/归因、Skill 关系、多候选/批次、比较/选择、发布/回退和复用。
- 职责：系统组织流程；普通 execute/evaluate 函数承担实际执行/评分；已有经历可直接导入，未知不伪造。
- 暂缓：Codex/Claude 具体适配、CLI/MCP/插件、原生日志/Hook、项目目录同步；旧 TS 与用户数据保留。
- 当前所有权：根代理负责阶段同步、召回/采样/学习编排与示例；store 负责存储/Schema；learning 负责证据与模型边界；evaluation 负责比較/发布/报告；不复活旧草稿。
- 最近检查：原暂停总纲的开工请求确实被拒；修改后合法 true/false 均通过，33 个负例与 6 个视图检查通过。文档工具取得官方 mutation 执照；产品验收尚在实施。
- 下一步：完成 M1 行为检查后提交，逐段记录真实文件、测试分母、失败和边界；总纲例子及构造用例不作为学习效果。

- M1 检查点：Store 18 + Context 6 = 24 个构造测试通过；官方Store/Schema mutation20项、Context3项通过。editable安装后从 /tmp 可导入；独立复核正在进行。
- SDK接线：research/sdk-smoke.json，1次 gpt-5.6-terra 调用、329tokens，JSON/stop；只证明本地配置可用。
