# CH5：完整 CIM 局部台架

2026-11-23。本包按[项目使命](../../PROJECT_MISSION.md)和[开发计划](development_plan.md)支持以下研究问题：在固定向量、权重和已声明资源预算下，ADC 前/后求差、转换器共享与精度怎样改变结果、实际动作、保持可行性和服务瓶颈？参数来源为显式分析假设；未做器件或电路校准。

## 已实现范围与接口

| 入口 | 输入与输出 | 独立边界 |
| --- | --- | --- |
| [encode_conductances](../compute/cim/matvec.py) | 编码/电气参数、整数矩阵→有身份顺序的已编程电导矩阵 | 无目标编程时间；slice-major、positive/negative 顺序 |
| [evaluate_cim](../compute/cim/matvec.py) | CimNumericParams、CimInput→DAC/阵列/TIA/ADC/移位累加完整数值轨迹 | 不需要资源图、时序台架、compiler 或实验runner |
| [analyze_cim](../composition/tile/cim.py) | CimTile、CimInput→数值结果、动作账本、资源界、串行策略时间、每样本保持检查 | 独立局部台架，权重和输入码已驻留 |
| [CIM runner](../../evaluation/experiments/runner/cim.py) | 固定输入/基线、有限候选→独立整数参考、指标、成功/质量失败/执行失败记录 | 沿用配置、RunRecord、artifacts，不把硬件层绑定某种任务或框架 |

实际数组采用完整 R×C 稠密 MatVec，输入无符号，权重为幅度编码加可选差分支路。可独立采用无差分非负权重。所有 bit/slice/列执行，不跳过零。行/列分块、有符号输入、噪声/线阻/漂移和稀疏机制未加入本包。ADC lane 的尾批、权重尾 slice 的空闲编码位已覆盖。

## 怎样建模数值

对权重幅度的第 s 个 slice：`digit=(max(sign*w,0) >> (s*Bcell)) & (2^Bcell−1)`，编程状态 `G=Gmin+digit*ΔG`。非零 Gmin 显式保留，所有可编码状态须在阵列电导范围内。每份独立切片/正负阵列都有唯一资源 ID；程序矩阵按同一顺序返回，资源数量不能由名称重复增加。

输入第 b 个 bit 送入 1-bit DAC，电压为 0 或 Vread。列电流为 `I_j=ΣG_ij V_i`，TIA 为 `V=Voffset+I*Rtia`。模拟差分先算 `I+−I−` 再经 TIA/ADC；数字差分分别转换两支路后再减。两者都读取两份物理阵列，但转换数不同。跨阻可为负，恢复符号时使用同一增益。

ADC 采用现有 offset-binary 模型：码宽 N、`ΔV=(Vmax−Vmin)/2^N`。重建值是 `Vhat=Vmin+(q+1/2)ΔV`；再移除已知偏置/基线，除以 `Vread*ΔG*Rtia`，按 ties-to-even 得到整数部分和。数字差分先相减两个重建值，共模 Gmin 和 TIA 偏置在理想条件下取消；无差分时显式扣除 `Gmin*ΣV*Rtia`。不是把 ADC 码直接当作整数点积，也不把 ADC 与 DAC 当作互逆函数。

每个部分和按 `shift=b+s*Bcell` 移位，最终应用 error/saturate/wrap 有符号输出策略。中间数值累加采用 Python 无限精度整数，**不代表已实现无限位宽硬件累加器**；有限中间位宽、逐次溢出与电路面积需要后续模型。CimNumericResult 分别保留量化后的无限精度结果、最终结果、输出溢出标志与 ADC 严格越量程次数。没有发生限幅也可能量化失真。

编码、原始权重与实际输入内容哈希进入结果。每个样本采用 `work/bit/slice/branch/column` 身份，与电流、电压、码值、捕获/接收时间一一对应。软件构造电导初态不是目标硬件已经完成编程的证据。

## 资源、保持与局部时序

组合层复用 CH1 的归属/模型选择、供给包络及精确中间时间。计量选中 DAC、每份阵列、TIA、ADC、外部保持和数字处理资源；它们均有 owner，禁止选中同时覆盖后代的摘要。输出 actions/budgets 可与调用方显式的数据准备/搬运动作组合；数据地址、可见性与跨组件格式契约仍由装配方承担。示例本身不隐含 SRAM/DRAM/DMA 流量。

| 阶段 | 策略与工作单位 | 必要约束 |
| --- | --- | --- |
| DAC | 每 phase 更新 R 个行 DAC，向当前差分对理想广播 | 至少 R 条持续驱动 lane；未实现复用 DAC 后的逐行模拟保持 |
| 阵列 | 每物理阵列一次完整读取为一个 item，两差分阵列同时读 | 每份阵列独立 L/II；输出电流理想稳定直到当前 TIA 扫描结束 |
| TIA | 每输出/待转换支路产生一个保持样本 | 每 item 的结束时间就是此样本捕获时刻；模拟求差在此 frontend 服务边界内 |
| 外部 hold | 在全 TIA 排空后开始 ADC；此刻有 S 个样本 | 槽数≥S；每个样本从 TIA 完成到 ADC 接收的年龄≤有效期 |
| MUX/ADC | 首批等待 MUX setup，后续发起间隔 `IIeff=max(IIadc,Lmux)` | ADC 在发起时内部采样，外部hold随即释放；内部在途槽≥min(groups,ceil(Ladc/IIeff)) |
| 数字处理 | 一次码值重建/code；数字差分时再一次减法/列；一次融合 requantize/shift-add/列 | 全 ADC 完成后开始；码值暂存≥S，输出累加槽≥C，按同一逻辑item服务假设计量 |

数字原语按相同 L/II 处理是可替换的服务假设，没有借名称推导真实 ALU 成本。ADC 前模拟差分的额外模拟前端成本目前也未校准；相同资源数量/服务参数不保证相同面积或能耗。

固定策略为：DAC → 当前切片的阵列并行读取 → 全 TIA → 全 ADC → 全数字更新；bit-major/slice-major phases 完全串行。每个资源的首次发起为 `max(依赖就绪,该资源下一次可发起时间)`。一组 P lanes 的末批完成为 `first+(ceil(W/P)−1)II+L`；跨 phase 也保留最后发起后的 II，避免 L<II 时过早复用。跨时钟计算用 Fraction，再在输出边界转 binary64。保持有效性也按参数代表的确切数值检查，不增加隐藏 epsilon。

结果分三种时间：

- `resource_lower_bound_s`：忽略依赖，对每个唯一资源累计实际工作，取全批隔离服务的最大值。给出资源必要条件及瓶颈。
- `policy_bounds`：只对上述串行 phase 策略的完成依赖/供给包络成立。可导出动作后另行组合。
- `serial_policy_time_s`：显式串行策略、有限容量、MUX 与资源 II 下的局部分析结果。不是事件执行、器件实测或全系统预测。

本包没有实现既有提案中的 71-cycle 流水调度。那需要独立的跨 phase 重叠、槽生命周期和完整事件/静态调度验证，不能用本台架的串行结果替代。

## 同输入对照与证据

[默认配置](../../config/experiments/cim_matvec.json)为 `x=(3,5)`、`W=((1,−2,5),(−3,4,−1))`。独立精确整数点积为 `(-12,14,10)`。采用 3-bit 输入、3-bit 幅度、2-bit cell、四个 2×3 差分切片阵列，Gmin=1/4096 S、ΔG=1/1024 S、Vread=1/4 V、Rtia=1024 Ω；这些二进制可精确表示的值用于验证，不是器件推荐档位。

固定预算为两个 DAC、一个 TIA、两个 ADC、一个数字处理 lane、六个保持槽/码值槽、三个累加槽。阶段与时钟参数详见配置，保持有效期20 ns。基线 DAC/array 为2 cycles；TIA/digital为1 cycle；ADC L=3、II=1，MUX=1 cycle，均1 GHz。

| 候选 | 输出/验证 | ADC转换 / 数字操作 | 资源下界 | 串行策略时间 |
| --- | --- | --- | --- | --- |
| ADC前模拟求差 | (-12,14,10)，通过 | 18 / 36 | 36 ns，数字阶段 | 108 ns |
| ADC后数字求差，同预算 | 同一结果，通过 | 36 / 72 | 72 ns，数字阶段 | 168 ns |
| ADC lanes 2→4，资源消融 | 同一结果，通过 | 18 / 36 | 36 ns，数字阶段未变 | 102 ns |
| ADC降至250 MHz，资源消融 | 同一结果，通过 | 18 / 36 | 44 ns，ADC成为约束 | 198 ns |
| ADC降至2 bit，精度消融 | (50,58,54)，最大误差62，未通过 | 18 / 36 | 36 ns | 108 ns |
| 保持槽6→2，边界反例 | 容量失败，保留记录 | 不报告不完整账本 | 未给出 | 未给出 |
| 保持有效期20→1 ns，边界反例 | 年龄失效，保留样本ID | 不报告不完整账本 | 未给出 | 未给出 |

模拟求差基线共6 MAC、6 phase、12次DAC更新、12次阵列读、72次cell动作、48个物理权重bit。数字求差保持同样阵列和cell工作量；差异来自读出/数字处理。首phase的TIA捕获为5/6/7 ns，ADC接收为8/8/9 ns，外部保持年龄为3/2/2 ns。这组证据解释机制与边界，不构成实机加速比或 AI 任务质量收益。

[模型测试](../../tests/chipmodel/test_cim.py)包含80组随机小矩阵在两种差分位置下对照独立整数点积、不同矩形/单列形状、精确电流/电压/ADC手算、非零Gmin、负TIA、无差分、零工作值仍执行、尾slice/尾列、限幅/溢出、保持期限、内部在途/数字容量、所有权和L<II复用。另有[工作负载参考测试](../../tests/workloads/test_integer_matvec.py)与[集成测试](../../tests/integration/test_cim_experiment.py)，覆盖实际配置、比较口径、失败/质量分离、来源和完整回读。

## 运行与来源

独立数值调用使用 `evaluate_cim(params, inputs)`；局部装配使用 `analyze_cim(tile, inputs)`，不要求完整 Die/Package。两者可从配置生产类型解析，也可以直接构造冻结 dataclass。

```text
python -m example.cim_demo
python -m example.cim_demo --source-revision YOUR_SOURCE_ID --output .build/my-cim-study
python -m example.cim_demo --read .build/my-cim-study
python -m unittest discover -s tests/chipmodel -p "test_cim.py"
python -m unittest discover -s tests/integration -p "test_cim_experiment.py"
python tools/check_model_rules.py
python tools/check_structure.py
```

七个候选共五次执行成功：四个通过数值验证，一个明确质量失败；两个保持反例为执行失败。所有候选留档。CLI要求基线/主对照/资源消融通过质量，精度和边界实验仍完整展示其失败；不得只看退出码推断所有候选正确。回读拒绝缺候选、混来源/输入/预算和索引路径错误，不重跑模型。

profile_source、实际输入、全部候选、有效参数、电导初态、数值/时序轨迹、源码身份、假设和未知原因进入记录。`max_cell_evaluations`限制宿主展开，不属于硬件预算；默认source_revision=`unrecorded`表示来源不完整。本地验证、打包及来源清单由[STATUS](../../docs/STATUS.md)维护，证据目录为 `.build/chipmodel-cim-20261123`。

读取能耗、编程时间/能耗保持 `None + reason`；输入/输出搬运、DAC负载、线阻、漂移、模拟保持误差和器件物理可行性未建模。若未来研究结论依赖这些成本或误差，应按来源补充相应模型与独立证据。
