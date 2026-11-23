# CH9：物理条件与成本证据

按[项目使命](../../PROJECT_MISSION.md)，本包把“成本有数值”进一步约束为“什么结构、什么条件、来自哪里、覆盖哪些成本”。完成范围及本地验收记录见[STATUS](../../docs/STATUS.md)。CH9提供基础查询、物理账本和证据入口；完整器件校准、布线/时序签核、多Die热网仍需具体课题证据。

## 研究什么

| 研究问题 | 固定/改变因素 | 可以检验的结果 |
| --- | --- | --- |
| 公开特征化能否用于当前资源？ | 精确结构、PVT、成本项、动作及单位 | 匹配点与来源随结果返回；越域/缺项为未知 |
| 共享与摘要是否造成面积/能耗重复计量？ | 同一物理清单，改变静态计量粒度 | area/leakage完整覆盖且互斥；动态按真实叶子动作累计 |
| 一个方案是否容纳得下？ | 几何边界、层、实例位置及已知面积 | 同层包含/不重叠，成本面积与分配面积的必要条件 |
| 观测时长怎样影响能量？ | 固定动态工作和背景W，改变显式窗口 | E_background=P*T；没有窗口则背景J和总J未知 |
| 散热条件和功率如何影响温度？ | 固定单节点RC/总功率轨迹，单参数变化 | 峰值温度、供能积分、情景阈值违反；不宣称空间热点或真实可行 |

本包不执行新的AI数值任务，也不从CH8服务下界计算任务能效。工作量、任务质量、实际执行时间与物理证据仍分开提供。真实来源示例与合成公式实验分组保存，不混成统一器件排名。

## 怎样建模

### 查询与来源

[costmodel接口](../../costmodel/interfaces/UNITS.md)使用冻结CostSource、OperatingPoint、CostKey和CostPoint。查询键包括完整结构身份、工艺/库/角、VDD[V]、温度[K]、成本项、动作和粒度。当前只精确查表，不插值、外推或按工艺/电压自动缩放。更改条件后缺少匹配点就返回None及原因。

CostSource保留characterization、measurement、analytical或assumption类别，原工件哈希、版本、引用、单位提取方法和限制。relative_uncertainty=None表示误差范围未知。一个表项只能按声明范围解释；数字、来源标签或来源点再现都不构成校准证据。

成本项为area[mm²/instance]、leakage[W/instance]、dynamic[J/明确动作单位]。dynamic契约排除另外积分的背景功率。word、byte、wire bit、MAC、controller active cycle不互换，宏摘要不能与其内部成本同时加入同一静态指标。

### 资源、几何与能量

[PhysicalModel](../packaging/evidence.py)引用一份ResourceNode图和实际资源清单。每个叶子及可选摘要具有结构/PVT身份；static_selection恰好覆盖所有物理叶子且无祖先/后代重叠。单PVT摘要必须与其覆盖的叶子工作点一致。动态活动仅引用实际叶子，并以唯一activity_id防止重复提交同一行；多个真实动作允许分别计量。

Placement把一个实例或子树放到明确layer和Rectangle。几何视图与成本视图分别完整覆盖，允许粒度不同。几何校验在分析时执行，非法布局形成failed实验。不同层允许投影重叠，但不会自动获得层间连线或热耦合模型。

`footprint_mm2`是外边界投影；`placed_area_by_layer_mm2`保存每层布局面积；`characterized_area_mm2`是所选实体的表面积和。它们不相加。当表面积能映射到对应几何边界时，检查其是否不超过分配面积；摘要无法分摊到叶子几何时返回None。即使面积约束通过，也未证明可布通或时序收敛。边界判断按binary64表示，未加物理容差。

动态能量按Σn_a*E_a计算。背景能量只接受ObservationWindow：measured、simulated或assumed；measured必须有measurement来源。服务下界和宿主wall time不是窗口类型。缺少窗口时，即使背景功率已知，背景能量与modeled_energy_j也保持None。

任何成本点或动作覆盖缺失，完整类别总量为None，已知子集另存known_area_mm2/known_dynamic_energy_j。modeled_energy_j只在动态与背景两者完整时求和，且仅覆盖声明的模型范围；不含未声明的系统基础设施。非零活动拒绝零窗口；乘加使用Fraction中间量，正值下溢或溢出失败。

### CH8接入与热分析

[CH8适配](../packaging/assembly.py)将既有资源参数生成结构哈希，复用实际工作计数；同配置MAC不因实例名称不同变成不同结构。SRAM读取memory_services的逐bank读/写次数，共享RW端口仍分开能量动作。DMA使用已计量的占用cycle，D2D使用实际编码wire bit，NoC使用flit，DRAM使用burst read byte并显式标记ACT/PRE/refresh/write缺口。没有将bank供给约束和存储动作重复收费。外存profile哈希仍包含其显式时钟/来源描述，属于保守匹配。

适配记录原CH8分析的内容哈希，保留全部叶子；不会把通用MAC/SRAM绑定到标准单元数据。它返回的PhysicalWork.observation恒为None。补一个假设窗口仍不能填补缺少的成本profile。

[ThermalTrace](../packaging/thermal/trace.py)是独立的外部总功率分段输入：每段P_i≥0、duration_i>0，分别保留功率/时长来源和RC参数来源。复用`C*dT/dt=P−(T−Ta)/R`及现有解析解，τ=RC；每段响应单调，初态和段末包含该单节点峰值。记录ΣP_i*T_i为supplied_energy_j，表示外部给定输入，不与成本账本再相加。实验中热scope必须匹配物理scope。

热模型不更新查询PVT、漏电或频率，无DVFS闭环、空间热点、Die间热耦合、PDN或制造成本。PVT数据与热轨迹不一致时需另行研究，不能将各自通过解释为联合物理可行。

## 如何证明

### 已核对的真实来源

从OpenROAD-flow-scripts固定提交`82ac25be57125cc724388ef89f01ce65f9ba3dcc`取得两个原文件：

- [NangateOpenCellLibrary_typical.lib](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/82ac25be57125cc724388ef89f01ce65f9ba3dcc/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib)，SHA256 `8d540a4d4cf6d09d27c87ad067857a9c0c2eeb023ab7a56e058cd3113db4e9b1`。
- [NangateOpenCellLibrary.macro.mod.lef](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/82ac25be57125cc724388ef89f01ce65f9ba3dcc/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.mod.lef)，SHA256 `a43aea339f12a57a63497783e508ba16f3da2dc056d3247dec7d99707c2dedef`。

Liberty明确typical/TypTyp、1.1 V、25 °C，leakage_power_unit=1nW。下表为直接提取事实：

| 单元 | LEF宽×高 [μm] | 单元面积 [μm²] | cell_leakage_power [nW] |
| --- | --- | --- | --- |
| INV_X1 | 0.38×1.4 | 0.532 | 14.353185 |
| NAND2_X1 | 0.57×1.4 | 0.798 | 17.393360 |

[离线提取工具](../../tools/extract_nangate_evidence.py)验证文件哈希、单位和PVT，以Decimal确认LEF尺寸乘积等于Liberty面积，再转成mm²和W，生成[4个条件点](../../config/costs/nangate45_typical.json)。此工具只支持已核对的两个文件和单元，不是通用解析器。

面积交叉格式一致只是来源再现。漏电是库的标量属性，未按实际输入状态加权；未解析internal_power，不提供动态能量、整MAC/SRAM面积或芯片功耗。原表的误差范围未知，尚无独立器件留出实测。check_reference可报告绝对/相对误差，参考为零时相对误差未定义；holdout禁止相同工件或假设参考，但方法独立性仍需研究证据。

### 对照、反例与验证

[默认配置](../../config/experiments/physical_evidence.json)包含四组20案例：17次分析成功，3个预期失败（同层重叠、越界、热scope不匹配）。成功项仍包含未知成本、面积不满足和热阈值违反，均保留。

| 对照 | 结果与解释 |
| --- | --- |
| 两标准单元、显式无开关活动、假设1 s窗口 | 面积1.33 μm²，库标量漏电31.746545 nW，模型范围内能量31.746545 nJ |
| 同条件窗口1→2 s | 背景积分63.49309 nJ；没有推断真实任务时长 |
| 移除窗口/加入10次无profile的INV输入切换 | 总能量未知；漏电W仍已知 |
| INV的VDD改成1.0 V / 选无表项的双单元摘要 | 相关成本未知，不缩放或偷偷展开回退 |
| 分配边界缩为1 μm² | 1.33 μm²表面积不满足必要几何条件，分析仍成功 |
| CH8共享两Tile案例 | 保留64 MAC和16次word读；标准单元表无法给出这些结构成本，补窗口后仍未知 |
| 合成代数对照 | 6×0.25+3×0.5=3 J动态，0.375 W×2 s=0.75 J背景；叶子/摘要均3.75 J，数值仅测试公式 |
| R=2 K/W、C=5 J/K、Ta=T0=300 K；10 W加热10 s再0 W冷却10 s | 峰值312.642411 K、末温304.650883 K、供能100 J |
| 上述R翻倍 / C翻倍 / 加热功率翻倍 | 峰值315.738774 / 307.869387 / 325.284822 K；R和功率翻倍违反315 K情景阈值 |

[成本测试](../../tests/costmodel/test_costs.py)验证真实点换算、精确域、未知/已知零、来源/量纲和伪留出反例。[物理测试](../../tests/chipmodel/test_physical.py)覆盖唯一计费、PVT摘要、面积/层边界、时长语义、数值范围、半时间常数和分段热响应；50组随机参数使用80位Decimal指数作独立数值参考。[集成测试](../../tests/integration/test_physical_experiment.py)验证完整协议、来源/输入身份、只回读不执行、CLI、CH8共享读写和D2D线路量守恒。完整回归与安装包验证以STATUS实际记录为准。

## 独立调用与复现

无需CH8或完整系统即可查询一个成本点：

```python
from configuration.resolution.dataclass_config import load_config
from costmodel.providers.tabulated.lookup import CostTable, query_cost

table = load_config(CostTable, "config/costs/nangate45_typical.json")
result = query_cost(table, table.points[0].key)
assert result.value == 0.532e-6
```

```text
python -m example.physical_demo --source-revision <源码身份> --output .build/physical-study
python -m example.physical_demo --read .build/physical-study
python -m unittest discover -s tests/costmodel -p "test_*.py" -v
python -m unittest discover -s tests/chipmodel -p "test_physical.py" -v
python -m unittest discover -s tests/integration -p "test_physical_experiment.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

保存目录须为新路径。默认运行只读取本地参数，不联网、不执行SPICE/STA。需要重新提取真实表时，按上面固定链接获取原文件，然后运行`python tools/extract_nangate_evidence.py --lib <原lib> --lef <原lef> --output <新JSON>`并与已保存表比较。模型/输入/来源/失败均进入RunRecord，宿主时间独立于目标指标。
