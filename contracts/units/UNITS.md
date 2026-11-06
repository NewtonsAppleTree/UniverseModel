# units：指标单位词汇

METRIC_UNITS 是规范 token 集合，不是表达式求值器。second/byte/joule 等与 cycle、MAC、conversion、cell_evaluation 分开；前缀和 byte/bit 转换由生产模块显式计算。例：`T=C/f [s]`，`B=bit_count/8 [B]`，不能省略 f 或 8。

最关心 scale、工作量口径与 clock domain；不支持的 token 直接失败，新增词汇在代码维护。cycle 的标域检查由[Metric](../results/UNITS.md)执行。使用：producer 换算 → `validate_metric_unit` → 带单位记录。验证见[工程测试](../../tests/integration/test_framework.py)，无动态/物理状态。

<!-- model-fields:start -->

### [metrics.py](metrics.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `validate_metric_unit(unit: str)` | Validate canonical unit identity; reject ns/GB/s aliases so scale factors cannot disappear at a boundary. |

<!-- model-fields:end -->
