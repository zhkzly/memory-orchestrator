# C 执行记录：O06 / O07 / O08 及比较恢复

范围：candidates、verification、assets、relations、evaluation、release、engine及对应测试。Schema/报告/事实选择由根代理负责；feedback/recovery_lock由A负责；学习诊断由B负责。无真实模型、网络、benchmark调用或提交。

## 已接的消费者

- `evolve(..., verification=None, execute_view=None, asset_runner=None)` 在学习前生成公开目录，在比较时强制走同一验证链。`compare_candidates` 直接调用也不能跳过。
- `verification_catalog(case_set, verification)` 投影为公开`case:<id>`或调用方check目录；已知TaskSpec `criteria/private`从公开任务剥离，不向模型/执行器泄露。
- `apply_candidate(..., diagnosis_ref=None, diagnosis_hash=None)` 校验诊断内容和project/base；生成candidate保存`skill_aliases`，新学习路径保留诊断义务来源。
- 同snapshot的所有proposal/diagnosis检查取并集。明确check_ref改变实际cases/requests；无材料unknown，不按split猜自由文本已覆盖。验证计划固定完整材料hash、提案hash、资产job和局部组合。
- Python脚本从完整候选编译并在独立临时目录执行固定功能fixture；stdout/输出文件由宿主对照caller材料。超时、输出超限、缺能力/独立材料unknown；语法或功能失败fail。进程隔离不声明为OS沙箱。
- 组合对照生成独立内容hash的ExecutionView，保留依赖与资产，执行器实际只接该视图。相同闭包not_identifiable，不伪造0。完整结果才形成按case均值的有方向conditional_marginal_gain，冻结修订/背景/场景并交root selector消费。
- 新Comparison的逐标准FeedbackPlan在execute前冻结；A的assess/verify_assessment聚合真实criterion记录，原未知分母不缩小。发布重读原始执行、反馈、完整资产及组合结果再计算检查覆盖。
- `resume_comparison(store, comparison_id, execute, evaluate, *, execute_view=None, asset_runner=None, resolutions=None)` 复用原计划/返回/结果/检查/验证身份。共享A的started/return/recovery_lock；只有started无return时blocked，不能把存储中断写成永久unknown占用槽位，也不能免费重复外部调用。
- 每次比较段写comparison_segments start/end，整批墙钟单独计量。本地验证/编译/publish/recover用stage_measurements；外部调用只计唯一usage。恢复额外criterion尝试仍占冻结预算；缺报价不变成0。

## 已观察的RED与GREEN（最终矩阵继续追加）

1. 新`test_memory_verification`最初实测2个FAIL：未绑定诊断和无功能fixture的脚本被旧实现accepted；5个接口/模块不存在ERROR。这些拒绝路径对应O06/O08，而不是单纯检查函数是否存在。
2. 首轮5项真实CSV/脚本/组合检查GREEN。后续`test_memory_verification test_memory_evaluation test_memory_release` 35项GREEN（16.791秒）。
3. 比较恢复4项GREEN：缺Validation、Feedback/Assessment/结果中断、started无return显式attach、旧无marker拒绝。真实callback计数在恢复后不增加，保留原usage和同一验证ID。
4. 加入真实CSV对照→selector、unknown组合与恢复预算后，42项聚焦GREEN（25.984秒）。它们均为构造机制检查，不是学习/泛化效果。
5. 根代理发现公开TaskSpec投影缺陷后，`test_reused_full_task_specs_do_not_leak_private_fields`实测RED：目录含`task.criteria/private`哨兵；统一公开投影后等待共享ComparisonSegment schema同步再GREEN。
6. `test_memory_candidates`和新资产/组合中断用例通过；4个旧flow例因旧demo teacher尚未适配新prompt而失败（learning error / 0 proposals），已交root同步示例，未修改或削弱检查门掩盖问题。

## 证据边界

调用方提供实际执行/评分/固定功能材料并负责语义正确性；系统保证冻结、隔离输入、覆盖、身份、预算和可追查结果，JSON Schema与代码门不能证明自然语言归因真实。`check_ref`的自然语言对应关系仍是待验证假设。模型生成gold不能成为此独立材料来源。局部组合只证明已测条件下的观测增量，重复不伪装独立任务；未知、负效应和不可辨识均保留。

默认compile支持Python；明确的asset_runner可以提供其他脚本编译/功能实际能力，缺能力记unknown。默认进程执行不保证禁止系统调用或文件系统访问，不宣称强沙箱。调用成本门明确覆盖call_usage，本地维护的无报价成本由报告独立保持未知。

最终检查/官方mutation与源hash待下节追加；尚未宣称全任务完成。

## C 最终交接

- 最后一次C整组：68项通过，37.804秒，完整命令输出`C-tests.txt`。
- 获根代理独占窗口后执行既定18项官方mutation，18/18发放执照；7个产品源文件每次都按原字节精确恢复。`C-mutation-results.json`保留每条命令、具体注入、exit、stdout/stderr及前后SHA-256，`C-mutant-*-tests.txt`保留GREEN→RED→GREEN完整测试输出。没有幸存变体或未恢复文件。
- 窗口结束时再次逐文件核对SHA-256并AST解析，全部通过；`C-final-source-hashes.json`是交接版本。`git diff --check`通过。不存在C运行中测试或mutation进程，窗口交还根代理进行全量最终验证。
- C未提交、未调用真实模型或benchmark、未添加CLI/MCP/原生Agent适配。C范围内没有已知未关闭的功能项；真实模型的语义质量、泛化和维护净收益仍须实际实验，不由这些构造机制检查代替。

## 独立复核

A（本模块非作者）只读执行`C-independent-review.py`，完整输出已原样保存到`C-independent-review.json`：同base/candidate/material hash，仅诊断check_ref改left/right，实际请求集合分别包含optional-left/optional-right，protected target/regression保留、unused不运行。资产原始stdout篡改被asset_binding拒绝；未经验证的candidate被selection_mismatch拒绝；contrast.value篡改被contrast_result拒绝；原证据能正常发布。包括完整request IDs与受审源码hash；A未改C源码、未做mutation。原始/tmp来源见复制脚本及结果，不将它们当benchmark。

C对A的有界只读复核另保存在`C-review-A.py/json`：混合external/proxy的8个比较槽位不能形成可发布结论，实际StructuredModel proxy接线调用1次且伪改来源拒绝；真实子进程在原返回后exit29、执行中exit31的两种恢复各仅物理调用1次，后者默认blocked且close_unknown仍score=null；丢失墙钟段数1未补0。seed和旧无baseline_ref空库基线均从历史0经实际CSV比较发布到历史1并可重开。无A源码改动/网络调用，结果包含受审hash；未发现该轮指定范围的待修问题。

## 收敛追加

- 61项整组出现一次重复提案发布失败，未归因环境。固定同输入探针12次中8次失败，完整记录在`C-duplicate-probe.json`：`verification_obligations`。根因为prepare按生成顺序汇总义务、publish按排序alias读回；已增加z/a确定性RED，归集按requirement_id规范排序后GREEN，未删任何义务。
- 公开目录fallback的dict字符串也有序列化顺序差异；反向键序的相同TaskSpec实测RED，改用现有canonical JSON字节后GREEN。已知`criteria/private`剥离依然生效。
- 新的64项整组检查通过，原始输出在`C-tests.txt`。之后canonical目录与公开TaskSpec2项通过；缺execute_view时保留8个实际未执行的unknown槽位检查通过，不能将缺能力变成0计划分母。
- 真实CSV局部对照生成value=0.5，并使当前scope内selector第二个选择发生改变；换task_family关系不生效。该固定材料证明消费者链，仍不代表模型学会或泛化。
- 其它语言通过显式asset_runner接编译与功能能力，测试实际调用`/bin/sh -n`与脚本执行。原始返回/attempt/usage绑定到同一资产包和材料，未提供能力仍unknown。
- 最后发现原准入目标被可选检查稀释：真实CSV中原target gain=-1，两个可选check各+1，原实现accepted。`C-quality-probe.py`及before/after JSON保留同材料的实际结果。根确认属K12必须修复：Plan冻结quality_case_refs、round保存原quality集合ref/hash，原质量/迁移/回归/排序只读该范围；额外检查仍完整执行并进义务/稳定性/成本。修复后rejected，原target_gate=false，额外两个case仍各+1；不是取消检查来通过。
