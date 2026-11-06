# cim：驻留权重与外围成本的共同边界

第一性问题是减少权重移动的收益，能否覆盖编码、驱动、采样、转换、累加和编程的代价。阵列 cell 数不等同于有效吞吐；同一宏不能同时收取摘要和全部外围费用。

| 子模块 | Unit | 量纲与最关键的关系 |
| --- | --- | --- |
| [arrays](arrays/UNITS.md) | ConductanceArray、显式跨阻 | G [S]×V [V]→I [A]，再由 TIA 转回 V |
| [encoding](encoding/UNITS.md) | 位串行/差分动作量、位权累加 | logical MAC、cell-evaluation、conversion 与物理 bit 分开 |
| [periphery](periphery/UNITS.md) | ADC、DAC、SampleHoldLimits | 编码范围、LSB、L/II、lane 数、保持有效期 |

可独立运行任一段。完整数值链为 code→DAC→array→显式 TIA→ADC→累加。模拟差分发生在 ADC 前还是后，会改变转换数和误差；两种结果不能仅靠 signed 标志互换。

现有等效列和手算夹具采用无量纲整数模型，本电导/电压参考有不同数值边界。当前未覆盖编程寿命、INL/DNL、噪声、线阻、MUX 负载、共享外围背压与器件能量。最关心实际任务精度、转换次数、样本保持和输出容量；按结论敏感性再扩展。

<!-- model-fields:start -->



<!-- model-fields:end -->
