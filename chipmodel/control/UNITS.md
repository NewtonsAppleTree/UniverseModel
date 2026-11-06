# control：显式搬运与地址生成

DMA 计算本通道的启动/分 burst/数据通路服务；TMA 通过 TensorLayout 表达一般张量地址。不把 CPU/GPU vendor 指令名当作固定语义，TSU 继续保持待具体操作定义的可扩展类别。

DMA 周期=启动+burst 数*控制开销+ceil(payload/bytes_per_cycle)，空请求无工作。单个请求使用一条通道，多通道不能隐式加速同一 copy。此结果不包含外部 DRAM/SRAM/链路等待；若使用整体 copy 的测量摘要，不能再收取内部阶段完整成本。

TMA 地址=base+Σindex*stride。logical_bytes=product(shape)*element_bytes；span_bytes=Σ(extent−1)*stride+element_bytes。跨度包含空洞，不是 unique bytes；stride=0 表示广播或别名。当前只有非负 stride，低 bit packing、swizzle、权限和越界填充尚未实现。

最关心数据来源/目的可见性、边界、对齐、队列与在途量。本轮没有 event/token、barrier、CSR、interrupt、clock/reset/power 状态机；这些候选 Unit 需要实际依赖/状态，不能用一个全局 busy 替代。

使用顺序：确定布局与访问范围 → 将逻辑请求拆成实际搬运字节 → 查询 DMA → 显式连接存储/互连。ClockDomain 表达固定频率，不提供运行中 DVFS 或复位语义。

<!-- model-fields:start -->

### [data_movement.py](data_movement.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DmaParams` | `bytes_per_cycle` | `int` | B/cycle | 本通道数据通路宽度 [B/cycle]。 |
| `DmaParams` | `max_burst_bytes` | `int` | B | 单次 burst 最大 payload [B]。 |
| `DmaParams` | `startup_cycles` | `int` | cycle | 每请求启动开销 [cycle]；可以为零。 |
| `DmaParams` | `burst_overhead_cycles` | `int` | cycle | 每 burst 的串行控制开销 [cycle]；不包含外部存储时延。 |
| `DmaEstimate` | `burst_count` | `int` | burst | ceil(payload_bytes/max_burst_bytes) [burst]。 |
| `DmaEstimate` | `completion_cycles` | `int` | cycle | startup+bursts*overhead+ceil(payload/bytes_per_cycle) [cycle]。 |
| `DmaEstimate` | `completion_time_s` | `float` | s | completion_cycles/f_dma [s]。 |
| `TensorLayout` | `shape` | `tuple[int, ...]` | element | 各维 extent [element]；零维长度表示空张量。 |
| `TensorLayout` | `strides_bytes` | `tuple[int, ...]` | B | 各维地址步长 [B]；零 stride 表示广播/别名。 |
| `TensorLayout` | `element_bytes` | `int` | B/element | 存储元素大小 [B/element]；低比特打包需专门适配。 |
| `TensorLayout` | `base_address_bytes` | `int` | B | 所属地址域中的起始地址 [B]。 |
| `TensorLayout` | `logical_bytes` | `int` | B | 只读派生属性；逻辑元素存储量 product(shape)*element_bytes [B]；不扣广播重复引用。 |
| `TensorLayout` | `span_bytes` | `int` | B | 只读派生属性；从 base 到最后元素末尾的覆盖跨度 [B]，包含 stride 留出的空洞。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DmaParams` | 单个 DMA 通道的隔离 copy；多个通道通过多个实例表达，不自动并行一条请求。 |
| `DmaEstimate` | DMA 结果只描述该通道服务；没有 accepted/source_consumed/destination_visible 事件。 |
| `estimate_dma(p: DmaParams, clock: ClockDomain, payload_bytes: int)` | 空请求不发起；非空请求在供数和接收无限制时按串行 burst 计算服务需求。 |
| `TensorLayout` | TMA 的一般正 stride 地址映射：addr=base+Σ index_i*stride_i；不绑定厂商指令。 |
| `TensorLayout.logical_bytes` | 逻辑元素存储量 product(shape)*element_bytes [B]；不扣广播重复引用。 |
| `TensorLayout.span_bytes` | 从 base 到最后元素末尾的覆盖跨度 [B]，包含 stride 留出的空洞。 |
| `TensorLayout.address(self, indices: tuple[int, ...])` | 验证坐标并求字节地址；地址空间容量与权限由装配方检查。 |

<!-- model-fields:end -->
