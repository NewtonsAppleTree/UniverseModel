# CH6：计算能力与瓶颈解释

2026-11-23。本包按[项目使命](../../PROJECT_MISSION.md)与[开发计划](development_plan.md)，研究给定操作语义、资源预算、任务工作量后，为什么增加某项计算资源仍可能没有收益。CPU、GPU、NPU各自保持专业语义；这些分析不能形成不加条件的跨架构性能排名。

## 研究什么与独立入口

| 对象 | 研究问题 | 独立调用 | 可检验结果 |
| --- | --- | --- | --- |
| CPU | 同类μop为何受前端、发射、执行或提交限制？ | `analyze_cpu(CpuCore, CpuWork)` | 各阶段速率、全部并列瓶颈、有限批次发起跨度下界 |
| GPU | 哪项资源限制block驻留？启动限制是否完整？尾warp占用了多少槽？ | `derive_occupancy(GpuSmParams, GpuBlock)` | 每项容量、启动违反项、已知/未知可行性、尾槽与有效线程比例 |
| NPU | 哪种操作/格式受支持？实际工作、额外MAC和尾批如何影响孤立服务？ | `MacArray.analyze(MacWork)` | 完整签名检查、逻辑/实际工作、发起槽、L/II服务与未知成本 |
| 数字Tile | 增加MAC是否能突破已有供数约束？ | `analyze_tile(DigitalTile, TileWork)` | 同一owner/账本上的格式验证与计算/存储/搬运下界；不重复计费 |

工作量由调用方显式提供，不从CPU/GPU/NPU名称、峰值或占用率推导任务执行。组件可独立调用，不依赖完整Die/Package、compiler或事件引擎；Linear任务适配仍在evaluation，硬件层不导入compiler。

## CPU：稳态与有限工作分开

`CpuCoreParams`的取指、解码、发射、提交宽度已经归一为所选μop/cycle；instruction→μop展开比例由上层负责。执行端口是可执行同一种μop的P条等价lane，发起间隔II。`CpuCore.uop_class`必须与`CpuWork.uop_class`一致，且不能为`unspecified`；历史无任务峰值查询仍允许未指定操作身份。

每个阶段表示为 `(P,II)`，前端和提交的II为1。稳态上界为 `min(P/II)`，速率和并列瓶颈在Fraction域比较后才输出binary64；即使两个大整数速率显示成相同浮点数，也不把非并列项误判成并列。

对于W项工作，假设每个独立阶段在cycle0可用P个槽，其最后一次发起跨度至少为 `max(ceil(W/P)-1,0)*II`。各阶段取max后换算为秒。这是乐观的必要条件：省略阶段延迟、数据依赖、端口混合、分支和存储。W=0或W=1可以得到0跨度，**不代表执行零耗时**。`execution_time_s=None`保留缺口；不得用W/峰值冒充有限任务完成时间。有限跨度的限制项可能与稳态最窄阶段不同。

默认25μop的fetch/decode/issue/execute/retire跨度是6/4/8/6/12 cycles；稳态为2 μop/cycle、retire限制。只把执行端口8→16时仍是2 μop/cycle、12 ns跨度下界；提交宽度2→8后变为3 μop/cycle、issue限制、8 ns跨度下界。不是实机IPC或加速比。

## GPU：容量、启动与尾warp分开

当前唯一规则为 `padded-warp-block-quantum/v1`：`warps=ceil(threads/warp_size)`；寄存器先按完整warp线程槽计数，再按block分配粒度向上对齐；shared bytes单独按block对齐。按warp、partition或scheduler子分区分配的硬件需要其他明确模型，不得只改profile名称套用本规则。

每SM的block、warp、register、shared-memory和thread-slot限额分别给出可容纳block数。零寄存器/shared需求对应的`block_limits`为None，表示这项需求不形成约束；`thread_slots=None`表示该限额未提供，其原因同时列在`unknown_limits`。容量最小项全部报告。线程槽按完整warp占用；`resident_threads`只统计有效线程，`thread_slot_efficiency=threads/padded_threads`不等于动态利用率。

还检查单block线程数、每线程寄存器数、分配后的每block寄存器/shared上限。违反任一已知限制时，`resident_blocks=0`、`launch_feasible=False`且列出`launch_violations`；SM容量不足也返回False。全部本模型限额已知且容纳至少一个block时返回True；有缺失限额但已知预算可容纳时返回None，保留条件驻留数。True仅表示本模型静态可行，不能代替实际设备启动/指令兼容/物理验证。`limiting_resources`解释SM容量，`launch_violations`单独解释启动拒绝。

默认256线程、64 register/thread、16 KiB shared/block时，寄存器和shared共同限制为4 blocks/32 warps，occupancy=0.5。单独翻倍其中一种资源仍为4 blocks。33和64线程的两个block需求可具有相同0.5 occupancy，但前者占用64槽、尾部31槽无效，有效线程比例为33/64，后者为1；该反例说明occupancy不足以确定有效工作或吞吐，不宣称已测得不同GPU性能。Warp调度、SIMT分歧、访存合并、bank冲突和kernel执行时间仍未建模。

## NPU：操作/格式与实际服务分开

`MacArithmetic`把operation、operand_format、accumulator_format、output_format作为一个服务签名。区分`integer_mac`、非融合`float_mul_add`和融合`float_fma`；区分同为16 bit的float16/bfloat16。当前A/B同格式、输出格式等于累加格式，输出转换必须另建显式服务。整数能力不表示无限精度累加；浮点签名不证明具体舍入实现。本分析器不执行数值运算，越界、溢出、舍入和任务质量由任务参考/功能模型验证。

一个`MacArray`档位只绑定一种签名与一组P/L/II/ClockDomain/profile_source。请求必须完整相等才进入`analyze`；缺少能力声明或签名不符均失败。改变精度不会自动增加MAC lanes或减少服务时间。历史`estimate(executed_macs)`保留为无格式的原始流水线查询，不能用它声称某种操作受支持。

`MacWork`在本包采用稠密工作契约：`executed_macs>=logical_macs>=0`，padding/重算由映射者显式计入，未加入稀疏跳过。`G=ceil(executed/P)`，服务为0（空工作）或 `L+(G-1)II`；发起槽为GP，尾空槽为GP−executed。分别输出`packing_efficiency=executed/(GP)`和`useful_work_fraction=logical/executed`；空分母时为None。这两项都不是执行利用率。

默认逻辑7 MAC、实际9 MAC，P=4/L=3/II=2：12槽、3尾空槽、2额外MAC、7 cycles孤立服务。P增至8：16槽、7尾空槽、5 cycles，不能简单按峰值翻倍推断批次时间减半。保持P不变而执行12 MAC时，槽填满但额外工作增至5 MAC；逻辑有效比例下降，不能把填槽率提高当作任务收益。服务假设包含输入已就绪、独立MAC足够和在途容量足够；归约反馈、供数/背压、真实计算执行及能耗未知。

## 组合及兼容

`DigitalTile.mac_arithmetic`与`TileWork.mac_arithmetic/logical_macs`共同启用检查；只声明一侧会失败。`TileAnalysis.mac_analysis`复用已经计入的MAC服务，绝不把解释结果再次加到下界上。历史调用两侧都未声明时仍可执行原账本，但`mac_analysis=None`表示未验证格式能力。

[数字Tile配置](../../config/experiments/digital_tile.json)现显式声明INT8操作数、INT64累加/输出。Linear适配从任务语义生成integer_mac或float_mul_add请求，不能从硬件能力反向修改任务。换成binary64任务时必须同时选择支持该签名的能力profile；旧的仅修改上层dtype做法现在会被显式配置拒绝。验证同时保留正确选择binary64 profile的MatVec。

在同一140 MAC、314 B外部流量和实际输入下，P=4→8使孤立MAC服务35→18 ns，但数字Tile下界仍348 ns，受搬运约束；格式解释加入前后地址、bank服务、资源贡献和下界完全一致。已有[CIM台架](cim_bench.md)同样提供ADC增多而数字资源界不变的证据；本包复跑它的数值/资源对照，不重新计入CIM编程或能耗。

## 如何证明与复现

[独立模型测试](../../tests/chipmodel/test_compute_capabilities.py)包含CPU逐cycle槽发放枚举60组、GPU逐block资源消耗枚举80组、大整数速率并列判定、零工作、启动边界、尾warp、FP16/BF16和融合/非融合签名反例。时间与容量参考不调用被测推导函数生成期望值。[集成测试](../../tests/integration/test_compute_experiment.py)检查完整名单、单因素协议、缺失来源/工作混用拒绝、保存回读不执行模型及Tile不重复计费；现有数字Tile测试继续验证同输入数值和供数敏感性。

[计算能力配置](../../config/experiments/compute_capacity.json)有四组16案例，13次分析成功、3次不支持操作/格式的执行失败。成功结果中还分别保留GPU启动不可行与限额未知，不能只看succeeded推断可行。每组一个baseline；资源消融固定工作且只改模型的一个数值参数，工作消融固定模型且只改一项数值需求；语义变更必须标为boundary。所有案例和输入/来源都进入每条记录；回读拒绝遗漏、重复、混研究及非法索引路径。

```text
python -m example.compute_demo
python -m example.compute_demo --source-revision YOUR_SOURCE_ID --output .build/my-compute-study
python -m example.compute_demo --read .build/my-compute-study
python -m example.digital_tile_demo
python -m example.cim_demo
python -m unittest discover -s tests/chipmodel -p "test_compute_capabilities.py" -v
python -m unittest discover -s tests/integration -p "test_compute_experiment.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

CLI常规案例要求分析成功且GPU没有已知启动拒绝；boundary案例的失败仍完整展示。没有任务功能参考的能力实验不生成“数值质量通过”标志。各家族的执行时间指标统一保留None和原因，不以宿主时间替代。默认source_revision为unrecorded；可复现证据应填入真实来源。完整回归、来源清单、保存实验和隔离wheel证据由[STATUS](../../docs/STATUS.md)维护。本包完成后按计划进入CH7外存与缓存接入，按研究需要增加机制。
