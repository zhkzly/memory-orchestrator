# Decisions

feedback-grounded-learning|介入3|返工2|真实坏提取/criterion反馈/资源边/selector/22次mutation/383项回归|红线违反0

- 返工1：首次自动应用 contract diff 将一个 schema hunk 放入错误对象；在任何 check/完成声明前由 `cmp` 发现，精确恢复并按对象路径重做。
- 返工2：旧教学 Episode 没有 call/source/resource 身份，导致新门把它当真实闭环；保持生产门不变，修正 fixture 与 scripted executor。
