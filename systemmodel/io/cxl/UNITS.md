# cxl：显式能力、地址窗口与内存行访问

本目录服务“扩展内存是否可访问、需要多少数据搬运”的研究问题。引用同一 MemorySystem 的物理容量和节点端口；设备类型、启用模式、地址映射与路径分别校验。当前为静态分析，不拥有真实内存内容、缓存状态或执行事件。

| Unit / 实现 | 输入、行为与输出 |
| --- | --- |
| CxlMemProfile / [model.py](model.py) | 声明精确协议标签、内存行大小、平坦 decoder 粒度与来源/覆盖 |
| CxlAttachment / model.py | type1/type2/type3 约束可声明模式，enabled_protocols 明确实际启用项；类型不自动授权访问 |
| CxlWindow / model.py | 一段主机窗口对应一段现有 backing；不增加容量、不隐式互连/交错/池化 |
| CxlMemorySystem / model.py | 校验端口/所有权、容量/地址宽度、对齐与窗口冲突；生成含来源的 identity |
| CxlAccessRequest / model.py | 选定窗口及 S2 MemoryAccessRequest；io/cache 请求不能当作 mem 请求 |
| analyze_cxl_access / model.py | 检查模式、生命周期/权限/请求路径、decoder 与物理区间，输出 CxlAccessAnalysis |
| validate_cxl_access / model.py | 使用已保存 SystemPath 重分析；不搜索新路径、不执行访问 |

## 参数、单位与关系

字段以代码行尾为维护定义。line_bytes 为正的 2 次幂 [B]；decoder_granule_bytes 为 line_bytes 的正整数倍 [B]，窗口 base_address/backing_offset_bytes/length_bytes 均按该粒度对齐。backing 的分配粒度须含完整内存行，decoder 不能超出实际容量。主机与设备端口必须是匹配 mem_protocol 的地址 terminal。

平坦映射为 `physical_offset = backing_offset_bytes + address - base_address` [B]，必须与 S2 视图解出的 backing、端口和偏移一致。主机窗口按 host domain 检查互斥，物理 decoder 区间按 backing 检查互斥；不同 device domain 不能绕过同一 host domain 的地址冲突。选定窗口与当前 phase 的主机本地视图冲突也拒绝。

读取允许非对齐部分数据：`line_count = ceil((address % line_bytes + length_bytes) / line_bytes)`，`data_bytes = line_count × line_bytes`，`extra_data_bytes = data_bytes - length_bytes`。这仅计量完整内存行的数据量，不能当作完整 CXL 链路字节。写入仅支持行对齐且长度为整行的请求；masked write / read-modify-write 尚未建模。

type1 可声明 io/cache，type2 可声明 io/cache/mem，type3 可声明 io/mem；io 必须启用，mem 访问另需显式启用 mem。cache 声明不实现一致性；type1 不允许内存 decoder 窗口。关闭 mem 后可保留窗口声明，但访问失败。

## 调用、敏感性与证据

顺序：MemorySystem + CxlMemProfile + attachments/windows → CxlMemorySystem → MemoryPlan + CxlAccessRequest → analyze_cxl_access。可独立使用，无需 workload、实验框架或 DMA。分层迁移通过 [memory](../../memory/UNITS.md) 组合。

关键敏感量为模式、窗口容量/偏移、对齐、请求大小/行边界、权限和有向路径。测试含 100 组独立 byte-to-line-set 参考、类型/模式反例、窗口和地址冲突、返回记录篡改。示例采用 `manual:tier-cxl-fixture/v1`：64 B 行、**64 B 人工平坦 decoder 粒度**，用于小规模正确性台架，不代表真实 HDM 寄存器的合法粒度。

未覆盖完整 CXL 版本协议、HDM 寄存器、交错/多主机池化、FLIT/credit、返回路径服务、缓存一致性/原子/顺序/可见性。原生 CXL 时间和能耗未知，不套用 PCIe TLP 计量。用法与研究证据见[S4指南](../../docs/tiering_usage.md)。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CxlMemProfile` | `profile_id` | `str` | 1（标识/枚举） | Sourced abstraction identity, independent of PCIe TLP framing. |
| `CxlMemProfile` | `mem_protocol` | `str` | 1（标识/枚举） | Exact protocol label on CXL.mem request ports/wires. |
| `CxlMemProfile` | `line_bytes` | `int` | B | Power-of-two memory transaction quantum [B]; conventional examples use 64 B. |
| `CxlMemProfile` | `decoder_granule_bytes` | `int` | B | Positive flat-window alignment/size granule [B], multiple of line_bytes. |
| `CxlMemProfile` | `source_ref` | `str` | 1（标识/枚举） | Abstraction/parameter provenance, not an implicit CXL revision certification. |
| `CxlMemProfile` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Explicit capabilities and omitted protocol/coherence/timing mechanisms. |
| `CxlAttachment` | `attachment_id` | `str` | 1（标识/枚举） | One explicit host/device attachment identity. |
| `CxlAttachment` | `device_id` | `str` | 1（标识/枚举） | Modeled device owning the memory-side terminal and backing subtree. |
| `CxlAttachment` | `device_type` | `Literal['type1', 'type2', 'type3']` | —（结构/对象） | Type 1: io/cache; type 2: io/cache/mem; type 3: io/mem. |
| `CxlAttachment` | `host_port_id` | `str` | 1（标识/枚举） | Host address-terminal egress for memory requests. |
| `CxlAttachment` | `device_port_id` | `str` | 1（标识/枚举） | Device address-terminal ingress serving the decoded memory view. |
| `CxlAttachment` | `enabled_protocols` | `tuple[Literal['io', 'cache', 'mem'], ...]` | —（结构/对象） | Explicit enabled modes; io is required, type alone grants nothing. |
| `CxlAttachment` | `source_ref` | `str` | 1（标识/枚举） | Capability/negotiation/attachment source or manual assumption. |
| `CxlWindow` | `window_id` | `str` | 1（标识/枚举） | Unique decoder aperture identity. |
| `CxlWindow` | `attachment_id` | `str` | 1（标识/枚举） | Existing host/device attachment; no implicit multi-host sharing. |
| `CxlWindow` | `backing_id` | `str` | 1（标识/枚举） | Existing physical storage under the attached device. |
| `CxlWindow` | `base_address` | `int` | B | Host-visible aperture start in the device terminal address view [B]. |
| `CxlWindow` | `backing_offset_bytes` | `int` | B | First decoded physical backing byte [B]. |
| `CxlWindow` | `length_bytes` | `int` | B | Positive aperture extent [B]; does not create additional capacity. |
| `CxlWindow` | `source_ref` | `str` | 1（标识/枚举） | Mapping source, excluding unmodeled HDM register programming/interleaving. |
| `CxlMemorySystem` | `memory` | `MemorySystem` | —（结构/对象） | Authoritative node/physical capacity and NUMA identity. |
| `CxlMemorySystem` | `profile` | `CxlMemProfile` | —（结构/对象） | Flat decoder and memory transaction abstraction. |
| `CxlMemorySystem` | `attachments` | `tuple[CxlAttachment, ...]` | —（结构/对象） | Explicit endpoint modes, independent of path reachability. |
| `CxlMemorySystem` | `windows` | `tuple[CxlWindow, ...]` | —（结构/对象） | Nonoverlapping host apertures and physical decoder ranges. |
| `CxlMemorySystem` | `source_ref` | `str` | 1（标识/枚举） | Whole CXL assembly provenance. |
| `CxlMemorySystem` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Include all endpoint modes, mapping granules, decoder intervals and source in the immutable CXL identity. |
| `CxlAccessRequest` | `window_id` | `str` | 1（标识/枚举） | Existing flat decoder window. |
| `CxlAccessRequest` | `access` | `MemoryAccessRequest` | —（结构/对象） | Host source, region/address, operation, liveness phase and requested route. |
| `CxlAccessRequest` | `protocol` | `Literal['io', 'cache', 'mem']` | —（结构/对象） | Only mem provides this model's host memory-access behavior. |
| `CxlAccessAnalysis` | `system_identity` | `str` | 1（标识/枚举） | Full CXL capability/decoder/source identity. |
| `CxlAccessAnalysis` | `window_id` | `str` | 1（标识/枚举） | Checked flat decoder identity. |
| `CxlAccessAnalysis` | `access` | `MemoryAccessAnalysis` | —（结构/对象） | Validated placement, physical address, path and NUMA label. |
| `CxlAccessAnalysis` | `line_count` | `int` | line | Number of covered memory-line transactions [line]. |
| `CxlAccessAnalysis` | `data_bytes` | `int` | B | line_count * line_bytes [B]; read response or aligned full-line write data. |
| `CxlAccessAnalysis` | `extra_data_bytes` | `int` | B | data_bytes - useful requested bytes [B], not PCIe padding or header. |
| `CxlAccessAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | Coherence execution, protocol framing/service and physical cost remain unknown. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CxlMemProfile` | A line-granular memory-access abstraction declares its flat decoder granule instead of claiming register-level HDM fidelity. |
| `CxlAttachment` | Enabled protocols are negotiated declarations; device type only restricts which modes can be enabled. |
| `CxlWindow` | A flat decoder maps one noninterleaved host-visible aperture to one contiguous physical backing interval. |
| `CxlMemorySystem` | CXL capability/mapping declarations refer to the same finite backing inventory used by independent memory placement. |
| `CxlMemorySystem.identity_hash` | Include all endpoint modes, mapping granules, decoder intervals and source in the immutable CXL identity. |
| `CxlAccessRequest` | A memory request explicitly selects its decoded window and requested protocol semantics. |
| `CxlAccessAnalysis` | Line traffic is separate from unmodeled CXL packet/credit/coherence costs and complete target service time. |
| `analyze_cxl_access(system: CxlMemorySystem, plan: MemoryPlan, request: CxlAccessRequest)` | Independently query enabled CXL.mem capability, flat address mapping and declared request reachability. |
| `validate_cxl_access(system: CxlMemorySystem, plan: MemoryPlan, request: CxlAccessRequest, saved_path: SystemPath)` | Recheck saved static access/line observations without producer execution or a replacement path search. |

<!-- model-fields:end -->
