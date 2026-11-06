# IdealAdc：独立电压量化与理想转换时间

实现：[adc.py](../compute/cim/periphery/adc.py)；示例：[adc_demo.py](../../example/adc_demo.py)；验证：[test_adc.py](../../tests/chipmodel/test_adc.py)。Python 3.10+，仅依赖标准库。参数与结果字段的含义、单位、公式直接写在代码声明旁；本页解释使用和模型假设。

## 使用顺序与接口

在仓库根目录执行 `python -m example.adc_demo`，即可运行单个 ADC 的转换与参数对比。项目目前采用仓库根目录下的 namespace package 导入，尚未提供 pip 安装包。

1. 用关键字参数创建 `AdcParams`：分辨率、lane 数、L、II、输入电压范围全部显式提供。
2. 只查询规格时，调用 `derive_adc(params, frequency_hz=...)`；它无副作用。
3. 需要转换时，创建 `IdealAdc(params=..., frequency_hz=...)`；构造时自动推导 `derived`，无需先手动调用 derive。
4. 根据需要独立调用 `convert`、`convert_many` 或 `estimate_batch`。
5. 修改配置使用 `dataclasses.replace` 创建新 Params/模型，触发校验与重算；当前实例保持原值。

| 接口 | 输入 | 输出及语义 |
| --- | --- | --- |
| `derive_adc` | 冻结参数、固定转换频率 [Hz] | `AdcDerived`：K、LSB、延迟、II、bank 理想速率及在途槽下界 |
| `convert` | 一个已采样电压 [V] | `AdcSample`：offset-binary 码、低/高越限标志 |
| `convert_many` | 有限电压 iterable [V] | 按原顺序生成不可变结果 tuple；允许空序列；宿主内存开销 O(S) |
| `estimate_batch` | 样本数 S [sample] | `AdcBatchEstimate`：组数、末次码值就绪 cycle/second；S=0 返回全零计量 |

`convert_many` 不表示所有样本同时转换。`estimate_batch` 每次都从空闲 bank、cycle=0 开始；连续两次调用不产生共享资源争用。实例没有运行队列、事件或累计计数，也没有 submit/tick/reset 接口。公共事件模型按[组件协议提案](../../docs/interfaces/component_protocols.md)另行实现。

## 数值与公式

记 N 为 nominal resolution [bit]，P 为 lane 数，L 为转换延迟 [cycle]，II 为每 lane 发起间隔 [cycle]，f 为固定转换时钟 [Hz]，Vmin/Vmax 为电压上下限 [V]。

码阶数 K=2^N。均匀量化把输入跨度分成 K 个区间，因此 ΔV=(Vmax−Vmin)/K [V/code]。码值采用：

```text
q = clamp(floor((V - Vmin) / ΔV), 0, K - 1)
```

第 k 个 bin 左闭右开，阈值恰好命中时进入较高码。Vmin 映射到 0，Vmax 特别归入末码；两端恰好命中都不标记越限。严格小于 Vmin 或大于 Vmax 才分别设置 `clipped_low` / `clipped_high`。负电压范围仍采用 offset-binary，例如 −1..1 V、3 bit 时，0 V 对应 code=4。

输入归一为 Python binary64 float；内部使用 Fraction 精确表示这些输入值及量化边界，避免浮点中间运算使阈值下侧样本误入高一码。它不会恢复调用前丢失的十进制精度。派生的时间、LSB 和速率最后舍入为 float；不能直接用显示值的舍入结果代替精确边界。

支持 N=1..53，这是 binary64 标量接口的首版软件支持域，不表示电路可实现的有效位数。输入量化间隔小于局部 float 间距时，某些码可能没有可表示的输入采样点；高分辨率且具有大共模偏置的模型需要更合适的数值表示。

每周期时间 Tclk=1/f，因此转换延迟为 L/f，发起间隔为 II/f。每 lane 每 II cycles 最多发起一个样本，P 个 lane 的稳态转换上限为 P·f/II [conversion/s]。L 与 II 独立：流水线允许 L>II，恢复时间较长也允许 II>L。

S 个样本分为 G=ceil(S/P) 批，首批在 0 发起，第 g 批在 g·II 发起。对于 S>0，末批在 `(G−1)·II + L` 完成；空批次为 0。维持该发起速率至少需要每 lane `ceil(L/II)` 个在途槽，假设同一时刻先完成再发起，并且输出立即接收。该值是容量需求下界，不会自动创建实际硬件资源。

10 bit、4 lanes、L=II=2、0..1 V、f=1 GHz 的手算结果为：

| 量 | 结果 |
| --- | --- |
| K / ΔV | 1024 codes / 0.9765625 mV per code |
| 单样本延迟 | 2 cycles / 2 ns |
| Bank 稳态上限 | 2×10^9 conversion/s |
| 16 样本末次完成 | 4 groups，8 cycles / 8 ns |
| 改为 8 lanes 后 | 2 groups，4 cycles / 4 ns；单样本延迟仍为 2 ns |

## 校验与覆盖边界

计数字段要求 Python int，排除 bool；电压/频率接受 Python int 或 float 并归一为 float。拒绝非法范围、非正频率、NaN/inf、不可表示的 LSB/时间/速率。错误类型采用 TypeError/ValueError，消息含字段名；NumPy 标量、带单位字符串等由调用方显式适配。空样本序列和零样本时序查询合法。

输入电压代表已经采样的数值；采样建立、保持衰减、MUX、ADC 前端负载、内部流水线容量与有限输出缓冲未建模。L/II 和 f 必须由假设或校准提供，调整这些参数只改变分析配置；不证明电路能达到相应时钟。模型不提供 INL/DNL、噪声、ENOB、能量、面积或 PVT 校准结果。

该实现可作为独立量化器，也可嵌入后续时序 Unit 作为数值函数。若连接 CIM array，需先明确阵列输出是电流、电压还是等效列和，提供必要的跨阻/缩放/编码适配。已有 [CIM 配置夹具](../../example/specs/component_bench.json)使用有符号、无量纲等效列和，不直接导入本电压模型。

扩展其他量化传递函数或时序行为时，为新实现声明对应 `model_id` 和验证用例；再出现多个需要共享的实现时抽取小型协议。参数可配置不意味着模型所有机制都由同一组开关表达。

## 验证依据

在仓库根目录运行 `python -m unittest discover -s tests/chipmodel -p "test_*.py" -v`。测试覆盖手算规格与输出码、10 bit 全部内部阈值及其相邻 float、负电压和极端范围、独立 Decimal 阈值搜索、空批次和尾批、流水线/恢复时间表、配置重算和实例隔离。

示例打印 `model_id`、输入配置、频率、派生量、输入输出和两组 lane 对比；它是可审阅的示例报告，不是完整 RunManifest 或快照。参数来源、提交版本、事件、随机和外部成本模型身份会在后续实验产物层统一记录。更完整的设计问题及参考来源见 [Unit 设计第 10–12 节](unit_model_design.md)。
