# 重写后真实小批实验

冻结产品提交46bf5f0、总纲v1.8.0、extract revision4、summary revision2。官方GDPevo固定56d60ae4ae5e067d1ec0ee1f850622e69f422179，group007：一条train001空记忆执行产生新学习材料，执行一次learn/evolve；若产生候选，按原协议比较train001 target和train004 regression的空库/候选两条件各一次。最多5执行，只有2个不同开发任务。

## 验收

记录全部真实messages/tools、response/usage、局部包与摘要/短引文、经验、诊断、Skill、比较与发布决定。检查模型是否实际使用分层输入，拒绝/缺证/超时来自何处；报告逐题分数与成本、未执行阶段和未知项。单次每条件只作诊断，不宣称稳定因果改善。未产候选或验证不通过是有效结果，不临时改门。

## 预算与范围

Teacher沿run.py放宽设置（12次/实例、阶段上限）；Actor沿当前6模型轮/128工具/8192输出。整个study物理SDK上限42次/300万输入字符/单次8192输出；timeout120秒，max_retries0。价格未提供则未知。test001不运行，不读其内容用于分析。
