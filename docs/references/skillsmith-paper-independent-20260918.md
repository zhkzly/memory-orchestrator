# SkillSmith 独立论文精读笔记

阅读日期：2026-09-18。对象：Yangbo Wei 等，**SkillSmith: Co-Evolving Skills and Tools for Self-Improving Agent Systems**，arXiv:2606.01314 **v1**，PDF 首页日期 2026-05-31，共 25 页。

一手来源：[HTML 全文](https://arxiv.org/html/2606.01314v1)、[固定 v1 PDF](https://arxiv.org/pdf/2606.01314v1)。原文标注 CC BY 4.0。本笔记独立阅读正文、算法、数学附录、实验附录、成本表及全部四个案例；对图 4、5、6 和关键表格进行了 PDF 图像核对。没有运行模型、没有复现实验、没有用既有聊天摘要替代原文，也没有把公开代码示例的结果并入论文实验。

证据标签：**[作者报告]** 指论文中的设置、观测或解释；**[原文核验]** 指可以直接由公式、表格或图文对照确认的事实；**[评估]** 指本笔记对证据能够支持什么的判断；**[工程推断]** 指迁移到现成 coding agent 时的设计建议。

**核心判断：论文最值得借鉴的是“以失败证据驱动、将 Skill 与其依赖的 Tool 放在同一候选变更中验证”的闭环。消融对受约束工具演化的支持，比对某一个生态方程的必要性支持更强。论文确有具体方法和对照结果；但主表分母与测试划分矛盾、部分算法与案例不一致，因此现有原文不足以独立确认其主表对应的严格 held-out 性能。**

**是否值得作为设计参考：值得，优先级高；是否值得把全套公式和 headline 数字直接当验收依据：目前不够。** 这个判断的三个最强正面依据是：

1. **机制对照：**122B 的表 2 中，锁工具层使 WCB 从 41.4 到 34.6，下降 6.8 pp；放开为无约束工具编辑又使异常率从 3.2% 升至 14.7%。它同时支持“要能修工具”和“修改应受契约/验证约束”。
2. **端到端机制案例：**图 7 的合并表头错位从 −54M 修到 +187M，工具接口与三个调用 Skill 同 bundle 迁移；图 9 进一步展示两个连续 bundle 如何把 1/5 checkpoints 提高到 5/5。案例是作者展示的执行说明，尚无完整原始日志供独立重放。
3. **跨设置一致趋势：**表 1 所列的每个规模上 Full 都高于 EvoSkill；397B 的差值是 OfficeQA +8.6 pp、SealQA +8.1 pp。这支持作者报告的一致方向，但必须附带测试分母尚未厘清的限制。

最重要的三项保留分别是：**评测分母冲突影响主结果的 held-out 解读；模块级消融不足以证明某个生态方程必不可少；理论附录的强保证超出实际论证。** 其它案例阈值、初始工具清单与伪码问题主要影响复现精度，不能把它们相加后推成“整篇联合演化思路无效”。正文以下保留完整核对过程，方便逐项查证。

## 1. 精确动机：究竟补了哪个 gap

### 1.1 优化对象不是模型权重

§2 将外部状态定义为：

\[
\Sigma_t=(\mathcal S_t,\mathcal T_t,\mathcal F_t).
\]

- Skill \(s=(m,w,r,u)\)：元数据（名字、触发条件、版本）、工作流、参考资源、utility。它回答一类任务“怎样做”。
- Tool \(\tau=(d,f,\sigma)\)：接口描述、可执行实现、输入输出类型契约。它定义“能执行哪些原子操作”。
- Anti-pattern \(\phi=(p,a,c)\)：失败签名、归因、补救方式。它保留负经验。

模型权重没有在这个优化问题中更新。Skill 中可以有脚本，但论文按职责区分 workflow 与环境操作的实现；不能把所有可执行代码一概称为 Tool，也不能把“外部状态可转移”说成已验证跨模型迁移。[§2，PDF p.3](https://arxiv.org/html/2606.01314v1#S2)

### 1.2 三个 gap 是相互关联的

| 论文指出的缺口 | 直接后果 | SkillSmith 增加什么 |
|---|---|---|
| 固定工具层，只修 Skill | 底层缺能力、接口错误、输出格式坏了时，用长说明反复绕过，多个调用方各补一次 | 一个 atomic bundle 同时修改 Skill 和 Tool，并更新依赖 |
| 孤立评估 Skill | 两项各自有用的流程合用时可能抵消；反过来，单项收益小的流程可能是互补能力 | 从共同激活日志估计 interaction，并影响检索、修改优先级、退休 |
| 消费完失败轨迹就丢弃 | 之后重新提出已失败/已退休的同类方案，重复诊断和验证 | 可检索失败记忆，以及候选提交前的 veto |

这里最有实质性的论点不是“候选可以一次改更多行”。PDF p.5 的解释框把它表述为**有效状态空间的可达性**：若改变 Tool 的参数签名必须同时改变调用 Skill，逐个修改会出现无法通过校验的中间状态；原子 bundle 可以直接从一个依赖一致的状态跳到另一个依赖一致的状态。[§1、§3.1，PDF pp.2、4–5](https://arxiv.org/html/2606.01314v1#S3.SS1)

### 1.3 和 skill-only 基线的精确差别

论文选择的比较对象是：

- Base Agent：初始 Skill 和 Tool 均不演化。
- EvoSkill：失败驱动的 Skill 演化，加 Pareto 候选选择。
- SkillClaw：多用户轨迹驱动的集体 Skill 演化。

因此，**失败反思、版本候选、Pareto 选择本身不是 SkillSmith 独创**。新增点在联合输出空间、工具生命周期约束、交互 utility 和负经验的组合。主表只比较 Base/EvoSkill/SkillSmith；WCB 的六天曲线比较 SkillClaw/SkillSmith。不是三个基线在三个 benchmark、五个模型上做了一个完整笛卡尔积实验。[§4.1、表 1、图 4](https://arxiv.org/html/2606.01314v1#S4.SS1)

**[评估]** “Skill-only 不能修工具”是这些基线配置的边界，不是说所有名为 Skill 的现代代理系统都绝无修改可执行代码的能力。尤其已有通用 shell/code 工具时，理论中的“初始工具表达能力之外”需要具体论证，不能仅凭名称认定。

## 2. 一轮到底长什么样

### 2.1 轨迹与反馈的最小单位

论文的执行轨迹是：

\[
\xi=(a_1,o_1,\ldots,a_L,o_L),\qquad P(x)\in[0,1].
\]

系统记录任务 \(x\)、实际激活 Skill 集合 \(\mathcal S_{\mathrm{act}}(x)\)、动作/观察、任务分数、执行成本。反思还可接收反馈函数 \(\mu_f\) 提取的编译错误、找不到文档的报告、约束违反等。没有 \(\mu_f\) 时退回轨迹诊断。[§2、§3.1–3.2](https://arxiv.org/html/2606.01314v1#S3.SS2)

下列是**依据论文整理的说明性载荷**，不是作者公布的逐字 JSON schema，更不是一条下载到的真实运行记录：

~~~json
{
  "task": "计算 FY2019 Q1 到 Q3 的公众持有联邦债务变化",
  "active_skills": ["Treasury-Table-Lookup@v1"],
  "trajectory": [
    {"action": "table_extractor(row=5,col=3)", "observation": "16,228"},
    {"action": "table_extractor(row=5,col=7)", "observation": "16,174"},
    {"action": "compute difference", "observation": "-54M"}
  ],
  "task_score": "来自 benchmark scorer；案例图未给这一条的数值分数",
  "feedback": "案例说明指出 merged-header 导致单元格错位",
  "cost": "论文要求记录，但案例未公开这一条的实际成本"
}
~~~

不能把反思器写出的“归因”自动当作已验证因果。可观察的错误、反思假设、修复后重跑的结果，证据层次不同。

### 2.2 从输入到未来使用的完整闭环

| 阶段 | 输入及动作 | 产物与下一步 |
|---|---|---|
| 初始化 | \(\Sigma_0,D_{\mathrm{train}},D_{\mathrm{val}},B\)；初始状态在训练实例上逐题评分 | 配置候选集合 \(\mathcal G\) 和实例得分矩阵 |
| 选父候选 | 按实例“胜场”加权抽一个候选；如有足够不同且有共同祖先的分支，可选择 merge | 当前待改进的完整系统状态，非孤立的一篇 Skill |
| 执行 | 在训练 minibatch \(M\) 上运行，检索 Skill、调用 Tool、收集轨迹与 score | 失败集合 \(F=\{x\in M:P(x)<0.8\}\) |
| 取诊断上下文 | 历史相似失败、\(\mu_f(F)\)、utility 趋势 \(\Delta u\)、交互 \(\hat\beta\) | 对“流程问题/工具问题”和“单点/交互问题”的诊断依据 |
| 反思与提案 | proposer \(\mathcal R\) 生成修改计划；涉及工具时调用 Tool-Smith | 一个 Skill+Tool bundle；可以只有 Skill 修改，不要求每轮都改 Tool |
| 负经验 veto | 提案动作与已解决 anti-pattern 匹配；命中则加入约束并修订，最多两次 | 避开已知失败实现；仍命中则丢弃本提案 |
| 候选应用 | 对父候选应用 bundle，依赖变更一起生效 | 候选状态 \(\Sigma'\)，此时尚未证明可投入正式使用 |
| 逐级验证 | 有工具操作才做 Tool 单元测试；再做端到端集成；最后回归 | 均通过才进入候选集合；merge 额外关注两个父分支擅长的任务族 |
| 统计与治理 | 从日志更新 \(\hat u,\hat\beta\)，执行 utility 动态；记录新失败；持续低 utility 则退休并留墓志 | 下一轮的 Skill/Tool/负经验状态 |
| 选择与未来执行 | 预算结束返回 validation 平均分最好的候选；今后的检索使用动态 utility 和交互分 | 新任务使用新 Skill 工作流及兼容 Tool，而不是继续复述旧失败轨迹 |

来源：[§3、Algorithm 1，PDF pp.4–7、14](https://arxiv.org/html/2606.01314v1#alg1)；[Appendix E，PDF pp.22–24](https://arxiv.org/html/2606.01314v1#A5)。

**重要边界：**这是论文定义的工作流。论文没有完整给出实际 reflection prompt、逐步 raw trace、所有验证断言、每轮预算台账或部署接口，不能声称仅凭这张表即可完全复现。

### 2.3 五类 Tool 生命周期操作

Appendix B 规定每项返回修改后的工具库和单元测试套件：

| 操作 | 原文约束与用途 | 依赖处理 |
|---|---|---|
| WRAP(\(\tau,g\)) | 在原实现外加前/后处理；原函数不改；类型签名保留或收窄。可用于输入校验、输出规范化、重试、表头解析 | 调用方式若受影响，需要兼容 Skill |
| EDIT(\(\tau,\Delta\)) | 一次调用只改函数体、输入 schema、输出 schema 三者之一 | 签名变化时，引用该 Tool 的所有 Skill 标记为同 bundle 更新 |
| COMPOSE(\(\tau_1,\tau_2,\pi_c\)) | 把两个工具串行或并行组合成新工具 | 保留原工具以向后兼容，Skill 可使用新旧任一入口 |
| SPLIT(\(\tau,\pi_s\)) | 拆成两个职责更单一的工具，合起来覆盖原能力；替换原 Tool | 所有引用原工具的 Skill 改为相应分量 |
| RETIRE(\(\tau\)) | 被替代，或连续 \(T_{\mathrm{ret}}\) 轮无活跃 Skill 引用时退役 | 保存身份、原因、时间，防止重新生成等价旧工具 |

来源：[Appendix B，PDF p.18](https://arxiv.org/html/2606.01314v1#A2)。

**[评估]** 这些是可操作的变更类型和依赖契约，值得借鉴；它们不自动等价于代码安全证明。新实现仍需执行验证，COMPOSE/SPLIT 是否保持语义也不能靠操作名保证。

### 2.4 Anti-pattern 的具体行为

\(\phi=(p,a,c)\) 中：

- \(p\)：失败 Skill/Tool、错误类别（type_mismatch、off_by_one、timeout、conflict 等）、可观察症状的自然语言描述；嵌入为向量。
- \(a\)：反思器生成的 Skill 层、Tool 层或交互层归因，可由 \(\mu_f\) 丰富。
- \(c\)：补救动作；未解决记为 open；解决后还保存对应 bundle ID。

诊断时取 top-3 相似记录，匹配阈值 0.8。提案 veto 使用更严格的 0.85，且只对非 open 记录触发；最多两次修订后仍触发便丢弃。退休 Skill/Tool 保存 epitaph，不单纯删文件。[Appendix E.1–E.4，式 17–19](https://arxiv.org/html/2606.01314v1#A5)

作者报告：命中率从早期 0% 到末轮约 35%；后半程每次反思的 LLM 调用数减少约 31%；跨三个 benchmark 总计触发 14 次 veto，其中阻止了 11 个近似已退休配置的提案。**论文未给其余 3 次的完整标签、所有应被拦截提案的总数或误拦结果，不能据此算 precision/recall，也不能把 11/14 当作已验证 veto 准确率。**

## 3. Utility、synergy、生态更新、Pareto：各自解决什么

### 3.1 先区分三种不同量

| 量 | 含义 | 不是 |
|---|---|---|
| \(\hat u_i\) | 日志中“激活/未激活该 Skill”的类别中心化分数差，经 EMA 平滑 | 该 Skill 的随机干预因果效应 |
| \(\hat\beta_{ij}\) | 两者共激活时的残差表现，超过“较好的单独激活”多少 | 严格的超加性 interaction、单次任务的确定原因 |
| \(u_i\) | 由历史状态和交互继续更新、并截断的运行期治理分数 | 原始准确率、成功概率或同 \(\hat u_i\) 相等的量 |

这三个量分工不同，不能都口头简化成“技能有效率”。

### 3.2 类别残差与个体 utility：式 4

先按同类任务历史均值去中心：

\[
z(x)=P(x)-b(x),
\]

其中 \(b(x)\) 是该任务类别的历史平均 score。然后：

\[
\hat u_i^{(t)}
=(1-\mu)\hat u_i^{(t-1)}
+\mu\left[
\bar z(i\in\mathcal S_{\mathrm{act}})
-\bar z(i\notin\mathcal S_{\mathrm{act}})
\right].
\]

\(\mu=0.3\)。直觉是避免总在简单类别上出现的 Skill 因原始分高而被高估，同时减少逐轮抖动。[§3.2，式 4](https://arxiv.org/html/2606.01314v1#S3.SS2)

**[评估]** 类别中心化缓解一部分难度混杂，不会消除同类别内任务差异、选择使用某个 Skill 的策略差异、模型/版本变化或其它共激活 Skill 的影响。它是观察性治理信号。论文没有随机分配 Skill、倾向校正或逐项留一干预来识别因果。

### 3.3 Synergy：式 5

\[
\hat\beta_{ij}
=\bar z(i,j\in\mathcal S_{\mathrm{act}})
-\max\left(
\bar z(i\in\mathcal S_{\mathrm{act}},j\notin\mathcal S_{\mathrm{act}}),
\bar z(j\in\mathcal S_{\mathrm{act}},i\notin\mathcal S_{\mathrm{act}})
\right).
\]

只在共现样本数超过 \(n_{\min}\) 后估计，否则设 0；附录取 \(n_{\min}=5\)。

- 正值：历史上两者一起比最好的单独激活组更好。
- 负值：共激活组更差，作为潜在冲突提示。
- 0：可能是无净收益，也可能仅是证据不足的先验；两者不能混为一谈。

例：若类别残差均值分别为“共同 0.20、仅 A 0.10、仅 B 0.05”，则 \(\hat\beta_{AB}=0.10\)。这是本笔记解释公式的数值例，不是实验结果。

该定义没有减去两个单项收益之和，也不是标准二阶差分 \(P_{11}-P_{10}-P_{01}+P_{00}\)。优点是只汇总已有日志，无额外 ablation rollout 成本；代价是没有干预意义。论文也未充分规定单独激活分组为空、版本变化后历史如何作废等操作细节。[§3.2，式 5](https://arxiv.org/html/2606.01314v1#S3.SS2)

### 3.4 Lotka–Volterra 风格动态：式 6

\[
u_i^{(t+1)}
=u_i^{(t)}
+\epsilon\hat u_i^{(t)}u_i^{(t)}
\left(1-\frac{\sum_jw_{ij}u_j^{(t)}}K\right),
\]

其中 \(w_{ii}=1\)，有充分共现证据的 \(w_{ij}=-\hat\beta_{ij}\)，其余交互为 0。之后截断到 \([0.01,1.0]\)。参数 \(\epsilon=0.1,K=20\)。

它把局部观察量转为带惯性的动态 utility：正 \(\beta\) 使对应 \(w\) 为负，互补邻居减小竞争项；负 \(\beta\) 使其为正，冲突邻居增大竞争项。在正观测 utility 等通常条件下，这有利于互补、抑制竞争。utility 变化趋势再用于优先修下降快的 Skill，持续低 utility 的 Skill 才退休。[§3.2–3.3](https://arxiv.org/html/2606.01314v1#S3.SS2)

**两个精度边界：**

1. \(K=20\) 不是“最多 20 个 Skill”的硬限制，也不是 token 上限。式中求和是交互加权 utility；无交互邻居权重为 0。组件数量控制还依赖检索、修改优先级、退休等整体机制。
2. 原文提供的是启发式离散动态和截断，不提供在这些带噪、可变交互估计下的收敛或稳定性证明。不能将图 6 的经验曲线说成方程的数学保证。

### 3.5 运行期检索用什么

\[
\mathrm{score}(s_i,q,\mathcal S_{\mathrm{act}})
=\alpha\,\mathrm{sim}(s_i,q)
+\gamma\,u_i
+\delta\sum_{s_j\in\mathcal S_{\mathrm{act}}}\hat\beta_{ij}
-\eta\,\mathrm{cost}(s_i).
\]

参数 \((\alpha,\gamma,\delta,\eta)=(0.4,0.3,0.2,0.1)\)。不是先挑全局 utility 最高的几个：仍以任务语义相关度为首要权重，并考虑已选 Skill 的兼容性和成本。论文没有完整规定 similarity 模型、成本的归一化单位、选择数量与具体停止规则；不能把四个权重直接移到另一宿主后期待数值等价。[§3.2、Appendix D.3](https://arxiv.org/html/2606.01314v1#A4.SS3)

### 3.6 Pareto 管理的是完整配置，不是 Skill 排名

Algorithm 2 对训练集每个实例找最高得分候选，取这些“逐题优胜者”的并集，再去掉被别的状态支配的候选，以剩余候选的逐题胜场数作抽样权重。

作用是保留有专长的系统分支：一个平均分稍低、却独占某类任务优势的分支仍可能繁衍，不会被单一均分最好的版本立即挤掉。最后返回的是 validation 均分最高的完整状态。[§3.2、Algorithm 1–2](https://arxiv.org/html/2606.01314v1#alg2)

**[原文核验] 有两处要准确转述：**

- 正文说“uniquely best”，Algorithm 2 的集合却包含并列最高的候选，并列也计一次 win；本文按算法说明，保留这一歧义。
- 这不是保留全部数学意义上的 Pareto 状态。先取逐实例最佳并集，会过滤掉“各项都不是第一、但不受任何单一状态支配”的折中状态。例如两题得分分别为 A=(1,0)、B=(0,1)、C=(0.6,0.6)，C 数学上不被支配，却进不了算法的初始候选并集。这是本笔记的说明例。

附录给 front capacity=3，但算法未详细给出超过容量时怎样裁剪；正文/Algorithm 2 使用训练实例，D.1 又称 validation 用于 Pareto selection，需实现细节澄清。

### 3.7 Merge 做什么，又没写清什么

Algorithm 3：

1. 选两个不同且非直接祖先关系的候选。
2. 寻找共同祖先，要求两个子分支平均表现都优于该祖先。
3. 按 Skill slot 三方合并：只有一方改过就取该方；双方改过取 utility 更高的版本。
4. 跨分支新组合若有 \(\hat\beta<-0.15\)，标记扩展回归。

附录 divergence threshold=0.3；正文说分支不够不同则回退 mutation。注意**分支 merge**与“将两个冲突 Skill 重写为一个复合 Skill”不是同一动作。后者可由普通提案实现。[§3.1、Algorithm 3](https://arxiv.org/html/2606.01314v1#alg3)

**[评估]** Algorithm 3 只显式合并 Skill slot；没有同等详细说明不同分支的 Tool 实现、schema、负经验如何合并。把全文概念直接做成工程，需要补齐这个依赖一致性问题。

## 4. 数学附录真正证明了多少

### 4.1 A.2：最优值集合包含关系成立；严格优越的证明更强

论文定义 \(\Omega_{\mathrm{skill}}=\mathcal S\times\{\mathcal T_0\}\)，联合空间 \(\Omega_{\mathrm{joint}}=\mathcal S\times\mathcal T\)。若前者是后者子集，则：

\[
\sup_{\Omega_{\mathrm{skill}}}J
\leq
\sup_{\Omega_{\mathrm{joint}}}J.
\]

这是正确的可行域单调性：保留原配置的更大搜索空间，其**全局最优值**不差。但它不表示有限预算的搜索器一定更快找到更优配置，也不表示新增操作不会产生坏候选。

作者进一步假设正概率的困难任务集合需要初始工具不能表达的能力，推出 skill-only 的困难题 score 被 \(1-\varepsilon\) 限制；然后推导：

\[
J^*_{\mathrm{joint}}-J^*_{\mathrm{skill}}
\geq\varepsilon P_H>0.
\]

**[评估] 证明缺口在式 11–13：**“允许修改工具”本身不保证一定存在获取缺失能力的工具实现；更关键的是，式 13 直接把困难题和其余题在同一个联合配置下都设为满分 1。这比前面 A.1/A.2 的文字假设更强。要得到这条下界，至少需补“存在可达联合配置，在困难集改善且不损害其它任务”等条件，或明确假设全分可实现。结论应读为关于假设中的最优空间的论证，不是 SkillSmith 具体算法的性能保证。[Appendix A.2，PDF pp.13–15，式 8–14](https://arxiv.org/html/2606.01314v1#A1.SS2)

### 4.2 A.3：操作类型少，不等于代码候选空间已多项式有界

作者比较：

\[
b_{\mathrm{free}}=O(|V|^L)
\]

与

\[
b_{\mathrm{SS}}
=5|\mathcal T_{\mathrm{local}}||\Delta\mathcal S_{\mathrm{dependent}}|
\leq5ck|\Delta\mathcal S_{\mathrm{dependent}}|.
\]

合理的工程直觉是：定位局部失败、限定五类操作、联动少数调用方，可以减少盲目修改。

**[评估] 但式 15 的计数没有包含 WRAP 内部函数、EDIT 的具体代码 diff、COMPOSE/SPLIT 的具体 plan 等 payload 选择；“选 EDIT”之后仍有很多代码。它也没有证明自然语言 Skill mutation 空间是多项式大小。** 因而不能把这段当作普遍的代码搜索复杂度证明。若把每类操作定义为一个预设的有限模板库，这样的计数才更有条件成立；论文没有给出这种完整限制。[Appendix A.3，PDF pp.15–17，式 15–16](https://arxiv.org/html/2606.01314v1#A1.SS3)

这两处问题不抹掉方法的工程价值，但应把“启发式减少搜索难度”和“已证明有限预算严格优势”分开。

## 5. 实验设置：分母、模型与评分先于成绩

### 5.1 三套任务与实际覆盖

| Benchmark | 任务性质 | 附录划分/协议 | 论文实际报告模型 |
|---|---|---|---|
| OfficeQA | 约 89k 页美国 Treasury Bulletin；跨文档表定位、数值推理 | 246 题；train=24、val=17、test=205；按 monthly/quarterly/annual 文档类别分层 | 表 1：Qwen3.5 9B、27B、35B、122B、397B |
| SealQA | 有噪声、冲突来源的 web QA | seal-0 共 111 题；train=11、val=8、test=92；按 easy/medium/hard 分层 | 表 1：9B、35B、122B、397B；没有 27B 列 |
| WildClawBench | 长链、多工具、多模态交互；正文称 15–50 步 | 6 次昼夜演化；白天 8 个并发模拟用户，夜间反思/提案/验证/部署；下列四类，每题每天独立测 10 次 | 图 4：9B、35B、397B；表 2 消融与图 6 韧性实验：122B |

WCB 四类：Social Interaction 6 题/60 trials；Search & Retrieval 11/110；Creative Synthesis 11/110；Safety & Alignment 10/100。合计 **38 个不同任务，每天 380 trials**。六天若全部按此协议评测，则每方法/模型为 2,280 task trials；这是由附录做的乘法，**不是 2,280 个独立不同任务，也不是作者给出的训练 rollout 总量**。论文未为 WCB 给出同 OfficeQA/SealQA 一样清楚的训练/验证/未见测试题划分。[Appendix D.1，PDF pp.18–19](https://arxiv.org/html/2606.01314v1#A4.SS1)

“五模型”实际是**同一个 Qwen3.5 家族的五个规模**。正文未提供充分的完整 checkpoint 后缀、所有模型采样配置或跨家族转移实验；不能写成已经在五种不同厂商/架构代理上泛化。

### 5.2 评分函数与 failure score

| Benchmark | 演化 score | 主报告准确率口径 |
|---|---|---|
| OfficeQA | 数值相对误差/文本规范化 edit distance；容差 0%、0.1%、1%、5%、10%，映射到 0–1 离散 score；\(P<0.8\) 进入失败集 | 附录称主文均是 exact match（0% 容差），除非另说 |
| SealQA | 冻结 Qwen3.5-122B judge 看题目、标准答案、响应，三次判定多数票 | 二元正确/错误 |
| WCB | 每题 3–5 个二元 checkpoint，score=通过比例；任一 critical checkpoint 失败，整题 score=0 | 图称 Accuracy；附录描述多指标聚合，未完整给最终二值 accuracy 与平均 rubric score 的对应关系 |

**[原文核验]** OfficeQA 的分级文字称“最高通过容差”映射至六级，又称 \(P<0.8\) 等价于未通过 5% 容差，但没有列出逐容差到 score 的精确映射。因为较严容差通过通常也会通过更宽容差，仅凭“最高”这句话不能实现唯一 scorer。可以准确报告其主表自称 exact match；不要自行补全演化 scorer。[Appendix D.4，PDF pp.20–21](https://arxiv.org/html/2606.01314v1#A4.SS4)

### 5.3 初始状态与超参数

论文声称同一 benchmark 的所有方法共用同一初始状态：

- OfficeQA：3 Skills（Doc-Retrieval-Strategy、Table-Parse-Flow、NumCalc-Protocol）；4 Tools（pdf_parser、table_extractor、formula_calc、unit_converter）。
- SealQA：2 Skills（Search-Plan-Strategy、Source-Credibility-Eval）；3 Tools（web_search、page_fetcher、dedup_ranker）。
- WCB：8 Skills（Slack-Message-Handler、Calendar-Coordinator、Academic-Search、File-Preflight-Check、Creative-Pipeline、Git-Ops、Safety-Audit、Report-Generator）；表 4 列 9 Tools（slack_api、gmail_api、calendar_api、web_search、fs_ops、code_sandbox、img_processor、video_processor、git_cli）。

**表 3 的 WCB Report-Generator 还引用 pdf_parser，但表 4 的 WCB 工具表没有它**；图 9 案例也把它当已有工具。这是“完整初始配置”描述的一个实际不一致。[表 3–4，PDF pp.21–22](https://arxiv.org/html/2606.01314v1#A4.T4)

超参数均据称在 OfficeQA validation 预试后固定到其它 benchmark/规模：

| 参数 | 值 |
|---|---:|
| failure threshold \(\theta\) | 0.8 |
| EMA \(\mu\) / 动态步长 \(\epsilon\) | 0.3 / 0.1 |
| capacity \(K\) | 20 |
| 共现阈值 \(n_{\min}\) | 5 |
| utility clip | [0.01, 1.0] |
| 检索权重 \(\alpha,\gamma,\delta,\eta\) | 0.4, 0.3, 0.2, 0.1 |
| Pareto front capacity | 3 |
| retirement patience \(T_{\mathrm{ret}}\) | 5 轮 |
| merge conflict / divergence threshold | 0.15 / 0.3 |
| anti-pattern retrieve top-k | 3 |
| match / veto similarity threshold | 0.8 / 0.85 |
| veto 后最多修订 | 2 次 |

来源：[Appendix D.3](https://arxiv.org/html/2606.01314v1#A4.SS3)、[Appendix E](https://arxiv.org/html/2606.01314v1#A5)。utility 初值、退休分数阈值 \(u_{\mathrm{retire}}\)、常规 minibatch 大小和总预算 \(B\) 的实例化数值，未在该超参数段完整给出。

## 6. 原始结果及其能支持的主张

### 6.1 表 1：照录数值，并保留分母冲突

**OfficeQA：表头写 246 questions；单元格是 accuracy %（correct count）。**

| 方法 | 9B | 27B | 35B | 122B | 397B |
|---|---:|---:|---:|---:|---:|
| Base Agent | 11.8 (29) | 22.0 (54) | 28.9 (71) | 43.9 (108) | 61.8 (152) |
| EvoSkill | 13.4 (33) | 25.6 (63) | 34.1 (84) | 53.3 (131) | 71.5 (176) |
| SkillSmith | 14.6 (36) | 28.5 (70) | 38.6 (95) | 60.2 (148) | 80.1 (197) |
| 论文所列 vs Base 增益 | +2.8 | +6.5 | +9.7 | +16.3 | +18.3 |

**SealQA：表头写 111 questions；没有 27B 列。**

| 方法 | 9B | 35B | 122B | 397B |
|---|---:|---:|---:|---:|
| Base Agent | 4.5 (5) | 10.8 (12) | 17.1 (19) | 30.6 (34) |
| EvoSkill | 5.4 (6) | 14.4 (16) | 23.4 (26) | 41.4 (46) |
| SkillSmith | 6.3 (7) | 17.1 (19) | 27.9 (31) | 49.5 (55) |
| 论文所列 vs Base 增益 | +1.8 | +6.3 | +10.8 | +18.9 |

来源：[表 1，PDF p.8](https://arxiv.org/html/2606.01314v1#S4.T1)。

这些加法增益是**百分点**，例如 80.1−61.8=18.3 pp，不能写成相对提升 18.3%。更贴近核心主张的比较是 vs EvoSkill：397B 的 OfficeQA 为 **+8.6 pp、+21 个表列 correct count**，SealQA 为 **+8.1 pp、+9 个表列 correct count**。9B 只分别多 3 题和 1 题；没有重复运行误差条/显著性检验，不能仅凭小差值断言统计显著。

**必须保留的冲突：**D.1 写 Table 1 所有最终数字只在从未见过的测试集报告，即 OfficeQA 205 题、SealQA 92 题。但表头以及 count/accuracy 的除法对应完整 246/111：

- \(197/246=80.081\%\)，对应 80.1%；\(197/205=96.098\%\)，不对应 80.1%。
- \(55/111=49.550\%\)，对应 49.5%；\(55/92=59.783\%\)，不对应 49.5%。

所以，**现有 v1 原文不能同时支持“上述 count、上述 accuracy、附录 test 分母、完全 held-out”四项都成立**。这是可核验的报告不一致；它不单独证明实际实验泄漏，也不授权读者自己选择一个分母改表。正确写法是“作者表 1 报告……，但其测试分母与附录不一致，待运行记录/作者澄清”。[表 1](https://arxiv.org/html/2606.01314v1#S4.T1)、[D.1](https://arxiv.org/html/2606.01314v1#A4.SS1)

### 6.2 表 2：122B 消融是最直接的机制证据

| Variant | SealQA | WCB Avg. | Regression rate ↓ | 最终 Skills + Tools | Tool error rate ↓ |
|---|---:|---:|---:|---:|---:|
| Full | 27.9 | 41.4 | 2.1% | 14 + 6 | 3.2% |
| Skill-only | 24.3 | 34.6 | 3.4% | 16 + 9 | 未报告 |
| FreeTool | 26.1 | 37.8 | 8.9% | 14 + 9 | 14.7% |
| −Eco | 26.6 | 39.1 | 2.8% | 21 + 7 | 4.1% |
| −Anti | 25.2 | 38.2 | 7.6% | 15 + 6 | 3.5% |

来源：[表 2、§4.2，PDF p.8](https://arxiv.org/html/2606.01314v1#S4.T2)。Regression rate 被定义为更新后变差的任务比例；Tool error rate 跟踪执行异常。表中没有逐项列出这些比率的原始分母、误差条或每项究竟跨多少轮统计，也没有充分注明最终库大小是哪种聚合口径。

**可以支持：**

- 锁工具层在 WCB 下降 **6.8 pp**，比其它单项消融更大，最直接支持“这套设置下 Tool 演化有贡献”。
- 无约束工具修改的 error rate 为 14.7% vs 3.2%，约 **4.59 倍**；regression 8.9% vs 2.1%。支持“允许工具变化还需要约束/验证”的组合设计。
- 去生态治理：WCB −2.3 pp、Skill 从 14 增到 21，支持该整套治理对库规模和表现有帮助。
- 去负经验：regression 从 2.1% 到 7.6%，约 **3.62 倍**；WCB −3.2 pp。支持负经验模块减少重复退化。

**不能单独支持：**

- −Eco 不是“Lotka–Volterra vs 简单 EMA/阈值清理”的专门比较。不能证明这个方程不可替代。
- −Anti 没有拆“诊断检索”和“提案 veto”的单独作用，也没充分量化误拦。
- 未见对 atomic bundle、merge、utility 各子部件的独立消融；也未见把新增计算量严格配平后的所有方法对比。
- 表 2 的 Skill-only 不是表 1 的 EvoSkill：122B SealQA 分别为 24.3 与 23.4。不能把两个名字视作同一基线数值。

### 6.3 图 4：WCB 六天演化曲线

图 4 只有 9B、35B、397B 三栏，四类任务各一条实线 SkillSmith 和虚线 SkillClaw。原图没有逐点数据标签或数表，因此本笔记不把看图估计值伪装成准确原始点值。

可以直接读出的趋势：

- 同一模型、同一类别，两者通常从相同起点出发，SkillSmith 末端高于 SkillClaw。
- 较大模型中 Search/Creative 等类继续提高；但**并不是每个模型、每个类别都到 Day 6 仍持续增长**。例如 9B Social 实线 Day 3 后就持平，9B Creative Day 4 后持平。
- 正文一处说基线 Day 2–3 平台，一处说 Day 2–4；应理解为汇总性描述，不是精确统一停止日。

图支持在该六轮在线协议中的改善趋势，不直接证明新任务分布上的迁移或长期生产部署稳定性。[图 4，PDF p.7](https://arxiv.org/html/2606.01314v1#S4.F4)

### 6.4 图 5：复杂度相关性，不是因果分解

D.5 明确右侧雷达来自 **WCB、397B**。每个因子按任务分低/中/高三档，画高三分位档中 SkillSmith 对 skill-only 的平均 gain。

| 因子 | 原文定义 | 原图标注 |
|---|---|---:|
| Tool Complexity | 标准解轨迹调用的不同工具数 | +26.5% |
| Interaction Density | 共激活 Skill 对数 / 可能的 Skill 对总数 | +35.5% |
| Context Size | 注入的全部 Skill/Tool 描述 token 数 | +11.4% |
| Action Space | 每步可用行动类型数沿轨迹平均 | +28.8% |
| Skill Synergy | 共激活 Skill 的平均 \(\hat\beta_{ij}\) | +46.7% |

以上数字直接读原图；正文使用 relative gains，**不将它们改写为百分点**。雷达还有 0.2–0.8 的径向刻度与两条方法线，附录没有给出足够原始数表来完全复算绘制口径。

左图把步骤数与多 Skill 共激活率放在坐标轴，颜色表示 gain；正文说简单任务约 5–10%，高复杂度任务超过 20%。虚线在图例中称 Theoretical Trend，未给出相应拟合或理论函数。

**[评估]** 这是按特征分组的关联证据。几个因子会相互相关，Skill Synergy 自身也由运行 outcome 估计；没有正交操纵各因子。故不能说“增加交互密度会因果导致 35.5% 收益”，也不能把雷达解释为五种机制各自贡献的可相加因果分解。[图 5](https://arxiv.org/html/2606.01314v1#S4.F5)、[D.5，PDF p.22](https://arxiv.org/html/2606.01314v1#A4.SS5)

### 6.5 图 6：受控破坏下的 100 轮韧性

设置是 **Qwen3.5-122B、三套 benchmark 的混合任务池**：

- 第 30 轮注入 15 个更长、更复杂依赖的新任务。
- 第 60 轮把当时 3 个 Tool 的函数体随机换成 no-op stub。
- 各方法使用相同扰动时序。
- 库大小统计 \(|\mathcal S|+|\mathcal T|\)。

作者报告：SkillSmith 到 100 轮恢复在约 70%；EvoSkill 约 30%；−Anti 大幅波动约 40–60%；−Eco 超过 80 个组件，之后性能下降；Full 组件数保持低于 28。图没有逐点数表，这些都是作者文字/曲线量级，不能当成精确 final test counts。[§4.3、图 6](https://arxiv.org/html/2606.01314v1#S4.F6)、[D.6](https://arxiv.org/html/2606.01314v1#A4.SS6)

**[评估]** no-op 替换明确测试“能够修改工具的系统是否能修工具被破坏”这一能力，因而有针对性，不应因场景人为就否定；但它天然更有利于可改 Tool 的方法，不能代表现实故障频率下的平均收益。还需要未专门破坏工具的自然漂移任务来验证外推。

**[图文差异]** 正文称两次扰动后所有方法都跌到 25% 以下；图 6 的 Full 蓝线在扰动后最低约 35–40%，并非低于 25%。−Eco 最末附近也约 35% 多，而正文写 below 35%。应引用量级趋势，避免复述明显与曲线不符的强说法。

### 6.6 成本：附录 F 与表 5

单轮分解：

\[
C_{\mathrm{iter}}=
C_{\mathrm{exec}}+C_{\mathrm{reflect}}+
C_{\mathrm{tool}}+C_{\mathrm{validate}}.
\]

作者称约 **35–45%** 的轮次会触发工具操作，其余可只改 Skill；工具活跃轮的 bundle 平均 **1.3** 项工具操作，每项最多 **2 次 LLM 调用**（生成、自检）加一次单测；单测成本通常小于一次 LLM 调用的 0.1 倍。这里的 1.3 是经验均值，不是 bundle 大小硬上界。

**表 5，OfficeQA、Qwen3.5-122B：**

| 方法 | Calls/iter | Iterations | Total calls | Total tokens (M) | Accuracy |
|---|---:|---:|---:|---:|---:|
| EvoSkill | 42.6 | 18 | 766.8 | 18.4 | 53.3% |
| SkillSmith | 51.3 | 13 | 667.1 | 16.0 | 60.2% |

论文给 \(\rho=1.20\)、\(\gamma=1.38\)。以表数计算，calls 少约 13.0%，tokens 少约 13.0%，accuracy 多 6.9 pp。它不是“每轮更省”，是较高每轮成本被较少轮数抵消。作者另称 \(\rho\) 从 9B 的 1.18 到 397B 的 1.22，\(\gamma\) 分别是 9B=1.21、122B=1.38、397B=1.47；后两端缺完整成本分表。

来源：[Appendix F、表 5，PDF pp.24–25](https://arxiv.org/html/2606.01314v1#A6.T5)。

成本证据边界：

- 只一组完整实测成本表；没有美元、真实 wall-clock、环境重置成本或所有模型/benchmark 的完整台账。
- “收敛”停止标准、重复次数和统计方差未充分给出；两方法最终 accuracy 也不同，不能理解为严格固定目标分数下的普适 cost frontier。
- 式 22 的 overhead 化简略去了两方法 reflection 等项可能不同的差额；一般应纳入这些差额，论文后文也说负经验会降低 reflection 成本。
- 成本主张不能自动解决表 1 的测试分母冲突。

## 7. 四个具体案例：从失败到候选，不只讲抽象架构

### 7.1 OfficeQA 表头错位：图 7、§4.3

问题：FY2019 Q1 到 Q3，公众持有联邦债务增加多少，单位百万。

旧流程：

1. Treasury-Table-Lookup 调 table_extractor 的整数行列接口。
2. merged header 导致错位，Q1 取 16,228，Q3 误取 16,174。
3. 算出 \(16,174-16,228=-54\) million，错。

Iteration 4 bundle：

- Tool WRAP：新增合并表头解析。
- Tool EDIT：输入从整数行列改为 row_header/col_header 字符串。
- Skill：改用表头名，加入单位/符号校验。
- 另外两项依赖同工具的 Skill 一并迁移。

修复后 Q3 正确取 16,415，\(16,415-16,228=+187\) million。一个工具能力修复覆盖三个调用方，这正是为什么应联合更新依赖，而不只给每篇 Skill 填 offset 特例。[图 7，PDF p.9](https://arxiv.org/html/2606.01314v1#S4.F7)

**边界：**案例给出了清楚的错误机制和 before/after，但没给这次 candidate 的完整单元测试/回归日志，也没公开三个 Skill 各自所有测试分母。图中旧 Q1 被称为取错格但数值又恰好与正确 Q1 相同，应按图记述，不自行补出原表内容。

### 7.2 SealQA 检索冲突：图 8

问题：ECB 2024 年 6 月会议加息还是降息，多少 bp。

- Search-Breadth-Protocol 发 8 个 query variants，得 23 页。
- Source-Authority-Filter 只留 3 页，其余 20 页被过滤；保留页中有两页是 4 月信息。
- 旧响应错误回答降 50 bp。
- Iteration 6 提案改为一个两阶段 Search-and-Verify-Protocol：先广搜，后对每条 claim 查权威证据；取到 19 个候选页面，对 25/50/不变分别验证，最后答降 25 bp。

图中作者把 \(\hat\beta_{AB}=-0.31\) 解释为冲突提示；**此例没有 Tool 修改**。它说明联合框架不要求凡事修工具，生态诊断也可能导向流程合并。[图 8，PDF p.19](https://arxiv.org/html/2606.01314v1#A3.F8)

**[原文核验]** 图写该交互信号来自 **4 次**共激活，同页 D.3 固定 \(n_{\min}=5\)，§3.2 又说低共现给 0。现有文字不能解释为何此时已有 −0.31。可能是案例简写或参数未同步；不能自行假定这是正常按阈值计算的实际统计。

### 7.3 WCB 学术资料到 Slack：图 9

任务：从用户 Zotero 库找联邦学习引用前三篇论文，做 LaTeX 比较表 PDF，附到 #research 新 Slack thread 并置顶。

Day 1 的九步说明中，web_search 给原始 HTML 杂讯；pdf_parser 表格布局坏；Slack 上传缺正确 MIME 预览；pin 还用了频道名而非 ID。只过 1/5 checkpoints。

Iteration 2 的 \(\mathcal L_2\)：

- WRAP web_search，清 HTML 并统一为 title/authors/year/citation count JSON。
- EDIT pdf_parser，新增 mode="table"，返回行列表结构。
- Report-Generator Skill 接受结构化输入并调用新模式。

Iteration 3 的 \(\mathcal L_3\)：

- 将重复的 channel-name→ID 逻辑提炼为 slack_resolver，作者称 COMPOSE。
- WRAP slack_api 自动设置 PDF MIME。
- Slack-Message-Handler 调用 resolver 后再发布。

Day 4 通过 5/5 checkpoints。作者称提炼删除了两个 Skill 中合计 23 行重复逻辑。[图 9，PDF p.20](https://arxiv.org/html/2606.01314v1#A3.F9)

**有价值的观察：**一次端到端失败有多个互不相同的坏点；先修数据管道，再修交付管道，用两个 bundle 完成，而不是期待一轮万能反思。

**边界：**作者称 \(\beta\) 接近 0 触发冗余识别；但接近 0 本身也可能是独立、样本不足或其它因素，不足以单独证明代码重复。并且 Appendix B 的 COMPOSE 输入是两个已有 Tool，而案例文字说从两个 Skill 中提炼逻辑，缺少具体 Tool-level 映射。它是清晰的设计说明，尚不是完整可重放的 mutation 记录。

### 7.4 WCB Git 鉴权负经验：图 10

任务：克隆库、向 staging 应用 hotfix、运行测试，通过才 push；失败则 revert 并通知 Slack。

Day 2 的独立 Git-Auth-Retry Skill 曾因共享临时目录与 Clone-to-Directory 冲突而失败。图中 SkillClaw 在 Day 5 又提 Git-Push-Auth-Fallback，验证再次因同类路径冲突失败，Day 6 再次浪费一轮。

SkillSmith 的 Day 5 提案相似度 0.91，高于 veto 0.85。注入的历史补救是“把 auth fallback 放入已有 Git-Ops”，反思据此修订，复用其目录管理后成功。

这个案例最有用的细节是：**负经验不否定“需要鉴权 fallback”这个意图，而是否定曾证实有路径冲突的实现方式**。[图 10，PDF p.21](https://arxiv.org/html/2606.01314v1#A3.F10)

## 8. 公平的证据判断与限制

### 8.1 作者自己承认的限制

§5 直接列出：

1. 依赖 backbone LLM 的反思质量。
2. 共现数据稀疏时生态模型有 cold-start noise。
3. 评测范围有限，更广 embodied 或 multi-user agent 场景留待后续。

WCB 虽有八个模拟并发用户，这并不等于真实多用户长期部署。[§5，PDF p.10](https://arxiv.org/html/2606.01314v1#S5)

### 8.2 根据原文可以提出的额外限制

按影响分级：

- **一级：影响核心定量主张。** 表 1 分母冲突妨碍确认未见测试集准确率，以及这些数字可以外推到何种数据划分。它不会仅凭算术矛盾就抹掉表中同口径方法差值，但真实口径仍须澄清。
- **二级：影响机制必要性与理论强度。** 缺乏细粒度/替代机制消融，意味着尚不能断言 LV 方程本身带来不可替代收益；A.2/A.3 的问题影响严格优越和复杂度保证，并不反驳表 2 所报告的实验差异。
- **三级：影响复现和案例解释。** 共现阈值、初始工具列表、伪码状态传递等不一致需要实际配置澄清；它们使照文实现不唯一，尚不足以独立否定“原子迁移依赖可以修复表头错误”这样的具体工程机制。

| 问题 | 精确证据 | 公平的结论 |
|---|---|---|
| 主表分母不一致 | 表 1 count/accuracy 对应 246/111；D.1 称只在 205/92 test 报告 | held-out 主结果目前不能独立确认；不能仅据此断言泄漏或造假 |
| 数据与方法仍有歧义 | 图 8 四次共现 vs 阈值五；初始 WCB Tool 表缺 pdf_parser | 复现者需要实际配置与日志，案例不能替代统计记录 |
| 数学说法强于论证 | A.2 满分假设跳步；A.3 操作 payload 未计入 | 保留工程启发，不接受一般性严格性能/复杂度保证 |
| 观察性 synergy | 只对日志类别均值中心化；无随机干预 | 用于提出冲突假设，不作因果事实 |
| 稳定性证据较窄 | 单家族，指定 no-op 扰动，图文部分不符 | 支持该设置下修复/治理趋势，不直接外推生产可靠性 |
| 消融粒度不足 | −Eco/−Anti 是整模块；无简单治理替代、merge 专门消融 | 能说明组合有贡献，不能证明复杂方程/所有组件都有必要 |
| 不确定性未量化 | 主表无重复 seed/置信区间，小模型仅差少数题 | 差值可报告，不冒充统计显著 |
| 验证器仍是系统的一部分 | SealQA 同家族 122B judge；Tool-Smith 给单测；原文缺详尽验证集与断言 | 需要关注 evaluator 是否独立、是否覆盖真实坏案例，不可把测试绿等同无缺陷 |

算法还存在工程化缺口：Algorithm 1 的 early continue 路径在伪码中跳过尾部 budget 增量；merge 分支后还引用 mutation 分支生成的 \(\mathcal L,M\) 等变量；新 anti-pattern 写入放在验证通过之后，而 E 节又强调保留失败提案。这些提醒读者**伪码不是可直接执行的预算/失败保存规范**，应由实际实现澄清，不能仅据伪码判定作者实现一定错误。[Algorithm 1](https://arxiv.org/html/2606.01314v1#alg1)

### 8.3 哪些质疑没有证据，不应该说

- “没有在现成商业 coding CLI 上测试，所以方法没价值”：不成立。论文评测的核心是可控外部资产演化，宿主集成是额外问题。
- “所有收益只是更长 prompt / 更多调用”：现有 ablation 和成本表给出了反方向线索，不能直接断言；公平问题是预算配平、验证和日志是否充分。
- “因为不更新权重，所以不叫改进”：不成立。外部政策/工具状态改进可以有实际效果。
- “主表矛盾说明结果必定伪造”：不成立。当前证据确认的是报告不自洽，实际原因需要原始记录。
- “生态统计是相关性所以毫无用处”：不成立。相关信号可以有效指导候选优先级，只要最终以独立执行结果选取修改，并不过度解释为因果。

## 9. 给现成 Codex / Claude Code 做工程项目：优先借鉴什么

**以下全部是工程推断。** 本节不声称论文实现了这些宿主适配，也不对当前 Codex/Claude Code 的具体 API、hook 或能力作未核验断言。

### 9.1 第一优先：资产演化与宿主执行分离

把 SkillSmith 视为“维护外部能力资产的控制器”，宿主继续执行任务。控制器需要收集执行证据、提出候选、组织验证、发布或回滚版本；不必先重写一个完整 agent 才能采用这个思路。

必须额外集成的是：怎样拿到宿主真实事件/工具结果，怎样判断 Skill 实际被读取/应用，怎样给一次运行固定 Skill/Tool 版本，怎样让新会话确实加载候选。论文只抽象规定执行器 \(\pi\)，没有替这些宿主完成此层。

### 9.2 第二优先：先建一个可重放的错误类别，再扩大演化

挑一个反复出现且有明确 oracle 的能力缺口，例如某种结构化文件解析/格式生成。保留任务、原始输入、工具 I/O、所用 Skill 版本、输出 artifact、评分和错误证据。

首个验收应同时证明：旧版本确实失败；新 Tool 在对应输入上有效；依赖 Skill 确实调用了它；端到端产物通过；保留的其它任务无退化。还需明确是否允许宿主用通用 shell/LLM 直接补救，否则可能看到任务成功却不知道新增资产是否产生贡献。

### 9.3 第三优先：atomic bundle + 依赖图 + 分层验证

一个候选同时携带：

- Skill workflow 变更；
- Tool 实现/schema 变更；
- 所有调用方迁移；
- 原因、失败证据和预期验证结果；
- 版本标识与可回滚的基线。

这是比先实现生态方程更直接的价值。对于宿主不可修改的内置 Tool，应把可演化边界放在自己拥有的 wrapper/script/tool server 中；能修的是适配层，不应假定可以任意修改宿主内部实现。

验证可分为工具测试、真实宿主端到端重放、旧任务回归，但合格与否应由明确检查器判定。候选应用与正式激活分开，至少以版本固定保证结果可归因。

### 9.4 第四优先：保留可推翻、可追溯的负经验

采用 p/a/c 的精神，但工程记录应分开“观察到了什么”“当前假设是什么”“哪次实验验证了修复”。保留失败 bundle、退出原因、版本、测试输入，避免仅留一句长期禁令。

初期相似度 veto 更适合作为“要求补证据/改实现”的提示。论文没有提供完整误拦率，故不宜一开始就让语义相似度成为跨项目的永久封禁规则。环境或依赖版本变化后，应允许旧 anti-pattern 重验与失效。

### 9.5 第五优先：有足够激活日志后再上生态治理

先用可解释、可复算的统计：成功/失败、使用量、成本、最近回归、候选覆盖任务；证明这些基本计数可靠。随后再加 pairwise interaction，报告样本量与“未知”状态。

是否需要 Lotka–Volterra 应由简单基线对比决定：EMA 排名、版本化停用阈值、依赖重复检测等就可能足够。论文没有证明复杂方程优于这些简单替代。稀疏个人 coding 工作流通常比密集 benchmark 更容易遭遇 cold start。

### 9.6 第六优先：小型多候选选择，而非一开始全局自治

保留在不同真实任务上各有优势的少数候选，有助于避免“平均分升、关键任务坏”。但生产成本在于每个候选都要重跑哪些实例、怎样隔离状态、验证集是否被反复过拟合、分支 Tool 版本如何兼容。

因此初期可以只做“当前稳定版 + 一个候选 + 一个历史回退版”的审计清楚流程；这是工程选择，不是论文已经验证的最优配置。等多任务证据足够，再考虑完整 Pareto/merge。

**优先顺序归纳：可重放执行证据 → 联合变更与依赖迁移 → 独立验证 → 负经验 → 检索/治理统计 → 多分支生态搜索。** 论文给出的主要价值在于前四项已经有清晰闭环，而不是要求工程项目先照搬全部数学术语。

## 10. 快速证据索引

| 要核查的内容 | 原文位置 |
|---|---|
| 外部状态、轨迹、优化目标 | [§2，式 1–3，PDF pp.3–4](https://arxiv.org/html/2606.01314v1#S2) |
| 联合反思与原子 bundle | [§3.1，PDF pp.4–5](https://arxiv.org/html/2606.01314v1#S3.SS1) |
| utility / synergy / 动态 / 检索 / Pareto | [§3.2，式 4–7，PDF p.6](https://arxiv.org/html/2606.01314v1#S3.SS2) |
| 逐级验证与退休 | [§3.3，PDF pp.6–7](https://arxiv.org/html/2606.01314v1#S3.SS3) |
| 主结果与消融 | [表 1–2，PDF p.8](https://arxiv.org/html/2606.01314v1#S4.T1) |
| WCB 六天曲线 | [图 4，PDF p.7](https://arxiv.org/html/2606.01314v1#S4.F4) |
| scaling 因子图及定义 | [图 5，PDF p.8](https://arxiv.org/html/2606.01314v1#S4.F5)、[D.5，p.22](https://arxiv.org/html/2606.01314v1#A4.SS5) |
| 100 轮扰动恢复 | [图 6，PDF p.9](https://arxiv.org/html/2606.01314v1#S4.F6)、[D.6，p.22](https://arxiv.org/html/2606.01314v1#A4.SS6) |
| 主循环、选择、合并算法 | [Algorithms 1–3，PDF pp.14–16](https://arxiv.org/html/2606.01314v1#alg1) |
| 严格优越与复杂度论证 | [Appendix A.2–A.3，PDF pp.13–17](https://arxiv.org/html/2606.01314v1#A1.SS2) |
| 五类工具操作 | [Appendix B，PDF p.18](https://arxiv.org/html/2606.01314v1#A2) |
| 全部四个案例 | [图 7，p.9](https://arxiv.org/html/2606.01314v1#S4.F7)、[图 8，p.19](https://arxiv.org/html/2606.01314v1#A3.F8)、[图 9，p.20](https://arxiv.org/html/2606.01314v1#A3.F9)、[图 10，p.21](https://arxiv.org/html/2606.01314v1#A3.F10) |
| 划分、初始资产、超参、评分 | [Appendix D，PDF pp.18–22](https://arxiv.org/html/2606.01314v1#A4) |
| 负经验与 veto | [Appendix E，PDF pp.22–24](https://arxiv.org/html/2606.01314v1#A5) |
| 成本分解及实测表 | [Appendix F / 表 5，PDF pp.24–25](https://arxiv.org/html/2606.01314v1#A6) |

最终证据边界：本笔记确认了 v1 论文的内容、公式、表中数字与可见不一致；没有确认作者未公开的运行记录，也没有将论文报告当作本项目已经复现的结果。
