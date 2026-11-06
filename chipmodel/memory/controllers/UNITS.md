# controllers：隔离读路径与未来命令控制

DramReadTiming 是一个可手算的路径模型，不是完整 DDR controller。参数中的 cycles 绑定传入的 DRAM ClockDomain，不能直接使用 CPU 或 controller 的另一个频率。

行命中前缀为 CL，关闭行为 tRCD+CL，冲突行为 tRP+tRCD+CL；之后每个额外 burst 等待 max(tCCD,tBURST)，最后加一个完整 burst 时间。请求字节向 burst 对齐，所有 burst 必须落在同一已选行内。

最关键的前提：起点 PRE/ACT 已合法，没有残余 tRAS/tWR/tRTP 等等待，没有刷新、读写转向或其他请求，所用 tCCD 符合本次 bank-group 关系。改变 row_state 是调用方提供的条件，不会更新隐藏的 open-row 状态。

实际 controller 以后需要地址映射、队列、页策略、命令约束与返回可见性；PHY/通道延迟若已包含在校准参数中，不得再次计费。先用显式轨迹和这些条件做独立查询，再按问题细化状态机。

<!-- model-fields:start -->

### [dram_read.py](dram_read.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DramReadTiming` | `t_rcd_cycles` | `int` | cycle | tRCD：ACT→RD 最小间隔 [cycle]。 |
| `DramReadTiming` | `t_cl_cycles` | `int` | cycle | CL：RD→首个数据传输 [cycle]。 |
| `DramReadTiming` | `t_rp_cycles` | `int` | cycle | tRP：PRE→下次 ACT [cycle]。 |
| `DramReadTiming` | `t_ccd_cycles` | `int` | cycle | 本次适用 bank/group 关系下的 RD→RD 间隔 [cycle]。 |
| `DramReadTiming` | `burst_cycles` | `int` | cycle | 一次 burst 占用数据接口的时间 [cycle]。 |
| `DramReadTiming` | `burst_bytes` | `int` | B | 一次 burst 的 payload 大小 [B]。 |
| `DramReadEstimate` | `transferred_bytes` | `int` | B | ceil(payload_bytes/burst_bytes)*burst_bytes [B]。 |
| `DramReadEstimate` | `completion_cycles` | `int` | cycle | PRE/ACT/RD 前缀+(bursts−1)*max(tCCD,tBURST)+tBURST [cycle]。 |
| `DramReadEstimate` | `completion_time_s` | `float` | s | completion_cycles/f_dram [s]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DramReadTiming` | 同一 DRAM 时钟域下的读路径特征值；由具体器件/profile 提供。 |
| `DramReadEstimate` | 单个隔离请求的尾数据到达时间，访问字节按 burst 向上取整。 |
| `estimate_dram_read(p: DramReadTiming, clock: ClockDomain, *, payload_bytes: int, row_state: str)` | row_state=hit/closed/conflict 分别需要 RD、ACT+RD、PRE+ACT+RD；请求必须处于同一行。 |

<!-- model-fields:end -->
