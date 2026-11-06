# d2d：串行 lane、packet 与线路编码

SerialLinkParams/estimate_link 描述一条单方向链路。lane_rate_bps 是已经定义的线路 bit rate，coding_data_bits/coding_wire_bits 是编码效率，例如 128/130；packet overhead 先加入，再做编码。

按 max_payload 分包，每包独立补齐码字；编码位数=Σceil((payload_i+overhead)*8/data_bits)*wire_bits_per_codeword。本模型按 bit 在 lanes 间条带化，末尾再补齐一个并行 bit beat，得到 wire_bits。T=fixed_latency+wire_bits/(lane_count*lane_rate)。空 payload 不发包，没有固定开销。跨 packet 连续编码或按字/码字分配 lane 的协议需修改补齐规则。

最关心有效数据率、分包尾部、物理 lane 共享与端点固定延迟。无训练、重传、FEC 纠错、credit、功率/BER 模型，不声称 UCIe/PCIe 等协议兼容。2.5D/3D 的几何和热条件由 packaging 提供；连接距离不会自动改变本参数。

<!-- model-fields:start -->

### [link.py](link.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `SerialLinkParams` | `lane_count` | `int` | lane | 本方向物理 lane 数 [lane]。 |
| `SerialLinkParams` | `lane_rate_bps` | `float` | bit/s/lane | 单 lane 线路速率 [bit/s/lane]。 |
| `SerialLinkParams` | `coding_data_bits` | `int` | bit/codeword | 每个码字承载的数据位数 [bit/codeword]。 |
| `SerialLinkParams` | `coding_wire_bits` | `int` | bit/codeword | 每个码字在线路上的位数 [bit/codeword]。 |
| `SerialLinkParams` | `max_payload_bytes` | `int` | B/packet | 单 packet 最大有效载荷 [B/packet]。 |
| `SerialLinkParams` | `packet_overhead_bytes` | `int` | B/packet | 头/尾/校验等编码前开销 [B/packet]。 |
| `SerialLinkParams` | `fixed_latency_s` | `float` | s | 不随字节数增长的端点/传播时延 [s]。 |
| `LinkEstimate` | `packet_count` | `int` | packet | ceil(payload/max_payload) [packet]。 |
| `LinkEstimate` | `protocol_bytes` | `int` | B | packet_count*packet_overhead_bytes [B]。 |
| `LinkEstimate` | `wire_bits` | `int` | bit | 逐包编码位数再对齐 lane_count [bit]；含末次并行 bit beat 的填充。 |
| `LinkEstimate` | `completion_time_s` | `float` | s | fixed_latency+wire_bits/(lanes*lane_rate) [s]；无工作时为零。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `SerialLinkParams` | D2D/SerDes 分析参数；lane_rate 已是每 lane 线路 bit rate，不再乘 DDR 系数。 |
| `LinkEstimate` | 链路计量守恒：payload+protocol bytes 经编码形成 wire bits，时间按物理速率计算。 |
| `estimate_link(p: SerialLinkParams, payload_bytes: int)` | 分包尾部独立取整；只估算一条空闲链路，不模拟 replay、FEC 纠错或 credit 停顿。 |

<!-- model-fields:end -->
