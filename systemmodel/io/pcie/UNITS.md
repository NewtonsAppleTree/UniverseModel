# pcie：conventional posted-write流量与线路容量

用于研究给定数据量/地址/帧格式的PCIe搬运开销及共享线路压力。只实现非FLIT、NRZ、posted memory write的静态计量。profile所有参数显式来源，不宣称完整PCI-SIG协议一致性，不把某一代的固定开销应用于其他模式。

| Unit / 实现 | 专业接口与行为 |
| --- | --- |
| PcieProfile / [model.py](model.py) | profile_id、protocol、MPS、每TLP总协议开销、编码比例、source_ref/coverage；验证不可变输入 |
| PcieService / model.py | 唯一resource_id、所服务的有向link_ids、lane数与每lane NRZ速率；派生frame容量 |
| packetize_write / model.py | profile、address、payload_bytes → PcieTraffic，独立调用无需节点或DMA |

## 参数、公式与单位

| 参数/结果 | 类别、单位、范围、关系 |
| --- | --- |
| max_payload_bytes | 输入MPS [B]，128/256/512/1024/2048/4096；约束含DWORD对齐的TLP数据字段 |
| tlp_overhead_bytes | 输入 [B/TLP]，完整header/sequence/CRC/framing合计假设，必须给来源；不自动补未知DLLP |
| coding_data_bits / coding_wire_bits | 输入 [bit/block]，例如128/130；wire≥data>0，计算流式平均容量上限 |
| lane_count / lane_rate_transfers_s | 输入lane数、每lane NRZ transfer/s；1 transfer=1 raw bit，不适用于PAM4 |
| frame_capacity_Bps(profile) | 派生 `lanes × rate × coding_data_bits / coding_wire_bits / 8` [frame B/s]；有限正数 |
| address / payload_bytes | 输入目标字节地址、正有效数据长度 [B]；半开区间不能超过64 bit地址空间 |
| packet_count | 派生TLP数；每包不跨4 KiB，且DWORD数据字段≤MPS |
| padded_payload_bytes | 派生每包DWORD数据字段合计 [B]；首尾byte enable造成的无效字节仍占线路 |
| padding_bytes / protocol_bytes | 派生 `padded_payload - useful` 与 `packet_count × overhead` [B] |
| frame_bytes | 派生 `useful + padding + protocol` [B]，物理编码前 |

单包有效大小=min(剩余有效B, MPS−address%4, 4096−address%4096)，数据字段为`ceil((address%4+size)/4)×4` B。对完整4 KiB页一次乘法累计，最多逐包处理首尾两页；不枚举大载荷的每字节或每包。帧工作为精确整数；派生速率/秒采用binary64。

编码只计入容量，TLP overhead只计入frame demand，避免重复折扣。流式编码上限忽略最后不足一个编码块的补齐，不把每条copy的整编码块尾部重复加成必要工作。每条有向wire引用一份service；多wire共享同一service时每次实际经过都计量，容量只定义一次。全双工可分别定义两个service，共用一个则是显式共享预算，不从协议标签推断双倍带宽。

## 来源、敏感性与验证

本包示例`manual:pcie-dma-fixture/v1`假设MPS=256 B、每TLP开销24 B、128/130编码、4 lanes×8e9 transfer/s。它是可检验手工台架，未做设备或协议详细标定。512 B对齐载荷为2包、560 frame B；address%4=3的513 B为3包、516数据字段B、588 frame B。测试另含4 KiB和64 bit末端、160组独立DWORD包参考与16 TiB输入。

敏感量：小块时header/padding比例、边界导致的额外TLP、MPS、lane/rate、共享引用。DLLP/ACK、flow-control credit、重放、传播、调度、SKP等额外物理流量、FLIT、PAM4、MRRS/read completion不覆盖；实际服务可能更慢。声明的source_ref/coverage随system identity保存。使用与比较范围见[S3指南](../../docs/transfer_usage.md)。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `PcieProfile` | `profile_id` | `str` | 1（标识/枚举） | Framing/coding identity used by frame-basis shared constraints. |
| `PcieProfile` | `protocol` | `str` | 1（标识/枚举） | Exact SystemPortSpec protocol; labels alone grant no permissions. |
| `PcieProfile` | `max_payload_bytes` | `int` | B | Negotiated MPS [B]: 128/256/512/1024/2048/4096, including DWORD payload padding. |
| `PcieProfile` | `tlp_overhead_bytes` | `int` | B | Assumed complete header/sequence/CRC/framing bytes per TLP [B], positive. |
| `PcieProfile` | `coding_data_bits` | `int` | bit | Useful bits per coding block [bit], e.g. 128; stream-average ceiling only. |
| `PcieProfile` | `coding_wire_bits` | `int` | bit | Encoded bits per block [bit], e.g. 130; at least coding_data_bits. |
| `PcieProfile` | `source_ref` | `str` | 1（标识/枚举） | Source for protocol assumptions, not an implicit PCI-SIG compliance assertion. |
| `PcieProfile` | `coverage` | `tuple[str, ...]` | 1（标识/枚举） | Declared accounting scope and omitted control/physical traffic. |
| `PcieService` | `resource_id` | `str` | 1（标识/枚举） | Unique modeled service resource in the topology ownership tree. |
| `PcieService` | `link_ids` | `tuple[str, ...]` | 1（标识/枚举） | Directed wires consuming this same capacity; references do not create more lanes. |
| `PcieService` | `lane_count` | `int` | lane | Positive NRZ lane count [lane] in the explicitly modeled service direction/group. |
| `PcieService` | `lane_rate_transfers_s` | `float` | transfer/s | Raw NRZ transfer rate per lane [transfer/s]; one raw bit per transfer. |
| `PcieService` | `source_ref` | `str` | 1（标识/枚举） | Lane/rate/shared-direction assumption or device profile provenance. |
| `PcieTraffic` | `payload_bytes` | `int` | B | Useful copied bytes [B], positive. |
| `PcieTraffic` | `packet_count` | `int` | packet | Conventional memory-write TLP count [packet]. |
| `PcieTraffic` | `padded_payload_bytes` | `int` | B | Sum of DWORD-rounded TLP payload fields [B]. |
| `PcieTraffic` | `padding_bytes` | `int` | B | padded_payload_bytes - payload_bytes [B]. |
| `PcieTraffic` | `protocol_bytes` | `int` | B | packet_count * tlp_overhead_bytes [B]. |
| `PcieTraffic` | `frame_bytes` | `int` | B | padded_payload_bytes + protocol_bytes [B], before physical coding. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `PcieProfile` | One conventional TLP format binds every modeled path; this excludes FLIT mode, PAM4 and read completions. |
| `PcieService` | A unique physical service can constrain several directed links, e.g. an explicitly shared half-duplex resource. |
| `PcieService.frame_capacity_Bps(self, profile: PcieProfile)` | Frame-byte ceiling = lanes * NRZ bit rate * data_bits/wire_bits / 8; packet overhead is counted in demand. |
| `PcieTraffic` | Exact TLP byte accounting separates useful bytes, DWORD padding and fixed per-packet protocol bytes. |
| `packetize_write(profile: PcieProfile, address: int, payload_bytes: int)` | Split writes at MPS and 4 KiB boundaries, respecting first/last DWORD byte enables; bulk full pages in O(1). |

<!-- model-fields:end -->
