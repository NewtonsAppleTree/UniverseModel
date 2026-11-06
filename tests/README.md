# 验证归属

本目录按 contracts、configuration、costmodel、chipmodel、systemmodel、clustermodel、workloads、runtime、simulator、artifacts、evaluation、ui 与 integration 划分。compiler 的阶段验证保留在 compiler/tests。

本目录规定测试归属，已完成的验证与可运行命令见[实现状态](../docs/STATUS.md)。功能与时序实现时，优先增加独立参考、容量/端口/因果反例、可手算争用与完整复现案例，避免仅重复代码行为。

完整验收标准见[验证规范](../docs/architecture/validation.md)。
