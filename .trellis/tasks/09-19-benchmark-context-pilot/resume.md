# 小批量诊断恢复点

- 用户当前要讨论剩余问题并授权发布GitHub；实验与修复到此冻结，不再自行消耗模型预算或新增演化设计。
- 完成：GDPevo固定56d60ae4ae5e067d1ec0ee1f850622e69f422179、group007的2个开发任务，9次执行、51SDK调用（1次usage未知），2个候选对照、0发布。
- 修复前：学习train001 5/17；target base耗尽预算unknown/candidate5/17，regression15/17→12/17。
- 修复后：target5/17=5/17，regression5/17→2/17，rejected。未证明memory收益；不能把Actor与模型随机变化归因单独memory因素。
- test001 probe实际入口返回not_run/identical_deployable_memory，输入/答案未交模型或用于修复；原计划停止理由已追加task.md，不计作通过。
- 已修：action/result成组和分时选择、可读目录、失败关键词误锚、Actor单条动态预算状态、N07提前披露评价范围与必需检查后果。原始actor源码和messages保留。
- 全套302 GREEN（73.788秒）/35官方mutation检出且精确恢复；源提交cee5cc4。全量/各原始失败/变体/代码hash在research。
- 剩余：同订单/SKU/仓库决策链不完整、8组反馈不够定位、Skill仍泛化、过程研究与验收混合、Actor基线不稳定。详见docs/experiments/gdpevo-context-pilot.md及revised-teacher-audit.md。
- 全部worker与live进程已结束。剩余收尾：证据提交、当前task归档/journal、普通快进push到origin/codex/vault-controller-maintenance并验证远端SHA。
- GitHub为现有PUBLIC zhkzly/memory-orchestrator；origin分支984ce57是本地祖先，不force、不改main/仓库可见性；当前文件和633个待推送历史blob扫描未发现凭据。
