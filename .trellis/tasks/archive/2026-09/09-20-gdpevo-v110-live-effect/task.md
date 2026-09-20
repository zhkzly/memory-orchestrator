# v1.10 GDPevo 真实效果实验
目标：得到可用于简历且边界清楚的 v1.10 真实 Teacher/候选对照数据。
不变量：固定产品代码、任务、评分器、门槛和预算；不为追求正分改实现。
不变量：复用归档 train001 Episode，不把旧 Actor 成本计为新调用。
不变量：test split 不读取；只有 candidate 存在才运行 target/regression 对照。
不做：不修改 prompt/schema/评分器，不补造 seed，不将单次结果包装为泛化。
金标：归档 prelearning-store/learning-input、GDPevo commit 56d60ae4、当前 commit 1ad555f。

## 追加
