# links：单向链路与序列化服务

候选实现 `model.py`；当前未实现，状态见 [STATUS](../../../docs/STATUS.md)。一条 Link 对应一个有向服务通道；全双工用两个方向，共享 PHY/半双工另引用共同带宽约束。NIC 队列属于 systemmodel。

## 参数与角色

| 字段 | 角色/单位 | 关系与范围 |
| --- | --- | --- |
| link_id / src_port_id / dst_port_id | 输入；标识 | 唯一方向与端点；首批物理连接不接受自环 |
| rate_basis | 输入；枚举 | raw_line 或 effective_payload，两分支互斥 |
| line_rate_bps / coding_efficiency | 输入；bit/s、比例 | raw_line 使用：聚合线路速率 R>0；η∈(0,1]，只含未扣除的 PHY 编码/FEC 效率 |
| payload_bandwidth_Bps | 输入；B/s | effective_payload 使用，正有限；按来源的消息大小/协议条件适用，不再扣包开销 |
| max_payload_bytes | 输入；B/packet | raw_line 的单包最大 payload M，正整数 |
| header_bytes / trailer_bytes / alignment_bytes | 输入；B | 每包头/尾 h/t≥0，对齐 a≥1，均为整数 |
| startup_s / propagation_s | 输入；s | 非负有限；独立消息启动与线路传播，来源不能已包含重复覆盖 |
| shared_constraint_ids / source_ref / coverage | 输入；标识与条件 | 共享服务资源、参数来源/版本/边界；无默认“典型值” |
| payload_bytes | 每次输入；B | D≥0 的整数；独立算术查询允许0，但不代表零字节控制包 |
| packet_count / wire_bytes / service_bytes | 派生；packet、B | 按下述分支计算；未知 wire bytes 保持 None |
| isolated_time_s | 结果；s | 单链路、无争用、完整消息服务估计，不是多跳/排队完成时间 |

## 公式与计量口径

raw_line：`n=ceil(D/M)`，各包有效长度 d_j，总帧字节 `W=Σ_j a·ceil((d_j+h+t)/a)`。本模型 `wire_bytes` 指含包头/填充、PHY 编码前的帧字节；容量用同一基准 `C=R·η/8 [B/s]`。`service_bytes=W`，孤立估计 `T=startup_s+propagation_s+W/C`。不再乘 payload/(payload+overhead) 效率。实际 PHY 编码块/线路位数若无具体 profile，不另声称已计数。

effective_payload：`service_bytes=D`，`T=startup_s+propagation_s+D/payload_bandwidth_Bps`；packet_count、wire_bytes 未知，不从有效速率反推。混填 raw_line 开销/速率与有效 payload 字段应拒绝。未知线上流量不妨碍同基准的 payload 服务界，但不得混合两基准求和。

profile 应区分声明容量上限与拟合有效服务率；实测平均吞吐不自动证明硬件上界。基于拟合服务率的Q/C仅为该条件模型的下界，不能不加条件地当作硬件物理下界。

D=0 的纯算术查询返回无数据工作、时间0并标记 empty；这不模拟协议控制消息。实际 TrafficInput 首批拒绝零长度消息，需要控制包语义后再扩展。启动延迟只作用于孤立估计；它是否占用共享发射资源在 C4 显式建模。

## 接口、敏感性与验证

LinkParams 校验 → `estimate_link(params, payload_bytes)` → LinkEstimate；不修改状态，不调用图或集群。D 小时头尾、对齐和启动敏感，D 大时容量敏感；信用窗口不足时本估计不适用。

独立验收：200 Gbit/s 与25 GB/s换算；1025 B 的尾包；D=0/负数/bool；η非有限或越界；重复效率；双工共享。多跳不能机械叠加整消息序列化，C4 再声明流水/存储转发。依据：[参数清单](../../../ARCHITECTURE_PARAMETERS.md)第6节及[手算夹具](../../docs/development_plan.md)。
