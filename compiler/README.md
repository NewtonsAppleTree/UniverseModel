# 编译与映射

任何资源映射和优化都必须保持工作负载语义并满足硬件约束。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

## 阅读入口

- [模块设计](docs/design.md)
- [分析职责与参数入口](UNITS.md)
- [张量区域、切块与规约](docs/tiling_and_reduction.md)：需求传播、尾块、split-K、GQA/attention 状态和输出投影走查
- [外部 layout_roi 手册审阅](../docs/reference/layout_roi_review.md)：内容统计、逐项修正与实现核查边界
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
src/ir
src/globalsplit
src/globalsolver
src/tiling
src/memplan
src/sched
src/lowering
src/interpret
src/export
src/pipeline
src/lba
include
python
tests
tools
scripts
3rdparty
temp
```

依赖约束：contracts、costmodel。依赖指公开接口；具体状态归属和运行时调用见模块设计。
