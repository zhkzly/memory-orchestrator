# 实施计划

1. 从真实归档反馈与候选报告派生最小测试夹具，写回流细项、artifact-feedback 绑定、闭环证据和 selector 红测。
2. 分别对 `evaluation.py`、`sampling.py`、`evidence.py`、`learning.py`、`context.py`、`candidates.py` 领取 mutation 执照；未通过前不改对应实现。
3. 在回流与普通采样最终结果上标注 artifact resource，并在反馈索引中投影同版本 resource。
4. 复用已验证 assessment，将原 criterion feedback 加入 rejected-target adaptation reason；保留无 assessment 兼容路径。
5. 为 extract/diagnose 增加纯语义检查，输出确切缺失角色及允许的补救动作。
6. 扩展 Skill scope schema 与 proposal prompt；新 ADD 强制机器 selector，context 先执行 exclude/require 再沿用依赖、冲突和预算。
7. 更新总纲版本、N02/N04/N06/N07/N08、相关问题、prompt revision、schema/example，生成 packaged contracts 和 HTML/context。
8. 跑定向测试、完整回归、mutation 复验、compileall、contract check/render/verify、diff check；按 checklist 五镜头复核。
9. 记录限制与验证证据，更新 DECISIONS、resume，分批 commit 并归档任务。
