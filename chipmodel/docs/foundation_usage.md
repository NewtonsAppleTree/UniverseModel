# chipmodel CH1–CH4 基础实现与研究用法

2026-11-23。依据[项目使命](../../PROJECT_MISSION.md)与[开发计划](development_plan.md)，本包支持固定任务/预算下的布局、端口共享和 C 驻留策略比较。交付是功能、容量、工作量与条件下界证据；不提供事件完成时间或物理校准。CH5–CH9后续基础及CH10统一验收均已完成，跨包覆盖见[完成报告](completion.md)。

## 研究什么

主对照固定 5×7 与 7×4 的 INT8 矩阵，INT64 累加/输出，输入生成版本 `sha256-index-v1`、seed=7。硬件为 64 B SRAM、4 bank×4 word×4 B、各 bank 1R1W、L=II=1、1 GHz；4 MAC lanes、L=II=1、1 GHz；单个 8 B/cycle DMA、500 MHz、每请求启动 1 cycle。两个方向的 NoC 分别有资源 ID，8 B flit、4 B header、单 hop 2 cycles、II=1、1 GHz。全部是分析夹具假设，未做器件校准。

| 同预算方案 | scratch 预留 | 外部有效字节 | 逐 bank 读事务 | 必要服务下界 | 功能 |
| --- | --- | --- | --- | --- | --- |
| 2×2×3，output_stationary | 44 B | 314 B | 138 / 122 / 110 / 30 | 348 ns，DMA | 精确整数参考通过 |
| 2×2×3，reload_partials | 44 B | 954 B | 158 / 142 / 130 / 50 | 588 ns，DMA | 同一输出 |
| 1×2×3，output_stationary | 25 B | 370 B | 220 / 120 / 80 / 30 | 460 ns，DMA | 同一输出 |
| 完整 5×4×7 tile | 需 223 B | 不给不完整结果 | 不给不完整结果 | 容量失败，保留记录 | 未执行 |

三个成功方案均执行 140 MAC。差异来自映射后的行请求与部分和搬运，没有删除必要计算。下界比值不能解释为实机加速比。

以第一个方案为基线的单因素敏感性（与主对照分组）：

| 改变项 | 保持条件 | 下界与解释 |
| --- | --- | --- |
| MAC lanes 4→8 | 数据、时钟、SRAM、DMA、路径不变 | 348 ns，DMA 未变，增加 MAC 无收益 |
| MAC 时钟 ÷100 | 请求、lane 数与其他资源不变 | 3500 ns，MAC 成为约束 |
| DMA 时钟 ÷4 | 其余资源不变 | 1392 ns，DMA 成为更强约束 |
| SRAM 时钟 ÷10 | 地址与容量不变 | 1380 ns，scratch bank 0 成为约束 |
| SRAM 4 bank→1 bank | 总 word 数/容量仍为 64 B，其他 profile 不变 | 400 ns，集中到一个 bank；总端口预算随 bank 数改变，属于资源消融 |

## 怎样建模

1. **契约与精度。** `bounds.py` 用 Fraction 累加需求、扣除初始额度并求资源界/关键路径，最后输出 binary64。整数输入在直接调用和 JSON 配置中都保留计数；浮点数按实际 binary64 值进入运算。超出输出范围或正数下溢显式报错。字符串不能充当序列；身份、重复、缺失、单位和环分别校验。输出是浮点近似值，不是向外舍入的区间证明。
2. **SRAM。** `SramAccess` 的地址为 backing 本地字节地址；非空区间触及 `floor((a+D−1)/w)−floor(a/w)+1` 个 word。每请求独立计量，不自动合并相同 word 的访问。非对齐读占全部触及 word；只有 `supports_byte_write=True` 才允许部分字写，掩码写仍占一次 word 服务，不隐含 read-modify-write。独立 R/W 和共享 RW 二选一，混合专用/共享端口暂不接受。服务计数按连续范围对 bank 取模，开销 O(请求数×bank 数)，不按每字节展开。
3. **隔离服务。** 独立端口每 bank 分别取 `ceil(R/Pr)`、`ceil(W/Pw)` 的最大值；共享端口取 `ceil((R+W)/P)`。完成周期 `L+(G−1)II`，空工作为零。假设全部请求就绪、word 可独立发起；无读写相关性、排队或存储内容。用于完整任务时，它是忽略依赖的必要服务条件。
4. **容量与所有权。** `BufferReservation` 引用 backing 的半开地址区间，按共同清单检查重叠/越界。两个 buffer 不创造两份物理 SRAM。首包不支持预留别名或动态生命周期。`TransferResources.nodes` 给出唯一 owner，模型选择拒绝同时计入祖先摘要与后代。派生 bank 端口 ID 不得与实例 ID 冲突。Tile 的计算、DMA、SRAM、链路均引用该清单。
5. **搬运边界。** `TransferRequest` 给出源/目标 backing、本地地址、字节数、DMA 和有向 link 序列。省略路径须由 DMA 的 `direct_memory_ids` 明确允许。每请求产生源读、通道、每条链路、目标写的明细；DMA 参数仅覆盖通道占用，所有请求在该通道串行服务。SRAM 消耗 word，DMA 消耗 cycle，NoC 消耗 flit，D2D 消耗 wire bit。不同单位只经明确模型转换。
6. **互连粒度。** 当前支持同构同钟 NoC 路径、单条 D2D 或显式直达；异构链路、多种协议串接需要后续 bridge 模型，现阶段拒绝。NoC 单包 `F=ceil((D+header)/flit_bytes)`，时间 `H(Lr+Ll)+(F−1)II`，不会把每 hop 的整包序列化相加。D2D 保留独立分包、编码和 lane padding。源/DMA/路径/目标之间缺少流式交付约定时，取已知隔离时间的最大值作为弱下界；只有声明的请求完成依赖才相加。
7. **Tile。** `DigitalTile` 与 `TileWork` 可独立调用；后者分别给出 MAC 数、本地计算访问、DMA 请求和预留区。Tile 检查 scratch 访问受预留区覆盖，并把 DMA 与本地请求合到同一 bank 账本。资源包络、依赖界、MAC 批次服务和逐 bank 服务分别输出，最大约束列为瓶颈。没有自动推断的计算/搬运重叠或数据就绪事件。
8. **Linear 适配。** `evaluation/experiments/runner/tile_mapping.py` 把 compiler 的计划转为源/目标地址和本地访问，芯片层不依赖 compiler。`scalar-ab-register-c/v1` 明确每 MAC 各读 A/B 一次；每个 K slice 中 C 在 MAC 累加寄存器驻留，slice 结束写回 scratch，后续 slice 先读回 C。output_stationary 仅避免 C 外部搬运，不表示 C 永久留在寄存器。三个 packed arena 无隐式补齐，byte-enable 能力因此必须匹配。训练入口尚无Tile地址适配，配置该后端会显式失败。已有 functional interpreter 验证算术/计划语义；地址轨迹由独立枚举/手算测试验证，没有声称执行了 SRAM 字节内容模拟。

`MemoryResource` 可以只提供容量与 `unknown_reason`。被请求触及而缺失的外存服务记录为未知，完整能耗始终为 `None + reason`。外存、同步、仲裁、背压、数据可见性、布局物理成本和未声明机制可能进一步增大时间。双缓冲只验证预留空间，不声称具有实际重叠收益。

## 调用与复现

仅查询 SRAM，无需工作负载或完整芯片：

```python
from chipmodel.common import ClockDomain
from chipmodel.memory.sram.bank import SramParams
from chipmodel.memory.sram.access import SramAccess, analyze_sram

p = SramParams(bank_count=4, words_per_bank=16, word_bits=32,
               read_ports_per_bank=1, write_ports_per_bank=1, access_ii_cycles=1)
request = SramAccess(request_id="tail", address_bytes=3, length_bytes=2, direction="read")
result = analyze_sram(p, ClockDomain(domain_id="sram", frequency_hz=1e9), (request,))
assert result.logical_read_bytes == 2 and result.read_service_bytes == 8
```

完整独立 Tile 装配示例见[模型测试](../../tests/chipmodel/test_foundation.py)的 `DigitalTileTests`；无需 Linear 或 compiler。跨模块实验使用[配置](../../config/experiments/digital_tile.json)：

```text
python -m example.linear_demo --config config/experiments/digital_tile.json
python -m example.digital_tile_demo --source-revision YOUR_SOURCE_ID --output .build/my-digital-tile
python -m example.digital_tile_demo --read .build/my-digital-tile
python -m unittest discover -s tests/chipmodel -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_digital_tile.py"
python tools/check_model_rules.py
python tools/check_structure.py
```

第二条命令生成六组共 24 条记录（18 成功、6 容量失败），保存有效硬件/访问策略、实际输入、plan/work身份、profile 来源、版本、假设和未知成本。`comparison.json` 是显式候选名单；读回缺任何 bundle 都报错，并检查身份、同输入、候选一致性，不重新执行模型。默认 `unrecorded` 仍代表来源不完整，应传入实际源码身份。`max_macs` 与 `max_local_accesses` 限制宿主展开/验证工作，不进入目标性能指标。

## 如何证明

- G1 的 `2^53+1−2^53=1` 同时验证直接调用与配置；60 组有理数参考验证资源包络和输入乱序不变性。
- 4 bank×16 word×4 B 手算：0/4/8/12 与 0/16/32/48 的 16 B 访问分别需要 1/4 cycles；1R1W 与 1RW 的不同 word 读写分别需要 1/2 cycles。遍历 256 个起址及边界内的小长度，以逐 byte 构造 word 集合独立验证 bank 计数。
- 17 B 拷贝：两端各 5 word，DMA 2 burst/4 cycles；每 hop 6 flit，双 hop 为 9 ns。D2D 16+1 B 分包、每包 4 B 开销、8b/10b 编码共 250 wire bits。共享资源、显式依赖、错误路径、owner、预留、格式与未知成本有反例。
- 1×1×2 Linear 手算本地与 DMA 合计读写各 20 B；跨行外部 stride 与 packed scratch 地址独立核对。原有 INT8/INT64、binary64 功能参考继续复用。新增实现没有 AI 任务级质量或物理可行性结论。
- 全仓库回归、规则/结构检查、wheel 源码一致性及隔离导入结果由 [STATUS](../../docs/STATUS.md)维护。本地证据目录 `.build/chipmodel-foundation-20261123`；CI 已增加数字 Tile 保存/回读命令，本地通过不表示远端 CI 已执行。
