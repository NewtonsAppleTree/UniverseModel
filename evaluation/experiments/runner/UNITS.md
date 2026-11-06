# runner：一个注入函数的一次调用

`run_experiment(spec, configuration, inputs, execute)` 返回 RunRecord。execute 接收隔离副本，返回 producer payload 与 tuple[Metric]；没有动态 import、插件发现、隐式编译或模拟时钟。

使用顺序：序列化输入快照 → 深拷贝边界 → 调用 → 输出/指标校验 → succeeded/failed。host_elapsed_s 是宿主执行/收集开销 [s]；目标时间必须显式来自模型。闭包/外部状态由调用者负责，状态组件在每次调用中重建或传入初态。

最关心隔离、异常可见、不可变快照、指标口径；执行成功不宣称数值验证通过。结构输入错误发生于调用前；callback/结果错误变成失败记录，无 fabricated output。测试见[工程测试](../../../tests/integration/test_framework.py)。

<!-- model-fields:start -->

### [single.py](single.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `run_experiment(spec: ExperimentSpec, configuration: P, inputs: I, execute: Callable[[P, I], tuple[R, tuple[Metric, ...]]])` | Snapshot explicit inputs, invoke a fresh copied boundary, and record success/failure without hidden stages. |

<!-- model-fields:end -->
