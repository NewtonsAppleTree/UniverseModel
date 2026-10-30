# 验证归属

本目录按 contracts、configuration、costmodel、chipmodel、systemmodel、clustermodel、workloads、runtime、simulator、artifacts、evaluation、ui 与 integration 划分。compiler 的阶段验证保留在 compiler/tests。

当前目录是后续测试归属，并非已实现测试套件。已有结构检查使用 `python tools/check_structure.py`。功能与时序实现后，优先增加独立参考、容量/端口/因果反例、可手算争用与完整复现案例，避免仅重复代码行为。

完整验收标准见[验证规范](../docs/architecture/validation.md)。
