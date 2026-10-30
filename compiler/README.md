# 编译与映射

任何资源映射和优化都必须保持工作负载语义并满足硬件约束。

当前状态：已建立目录和设计契约；执行模型尚未实现。

## 阅读入口

- [模块设计](docs/design.md)
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
