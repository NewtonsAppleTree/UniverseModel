# noc：无争用 wormhole 路径

NoCPathParams 接收 flit 宽度、packet header、每 hop 的 router/link latency 与连续 flit II。`estimate_noc_time` 额外接收 payload_bytes [B]、hops [hop]，返回 second。

F=ceil((payload+header)/flit_bytes)，C=H*(Lrouter+Llink)+(F−1)*II。头 flit 承担全部 hop 固定延迟，后续 flit 在已占有路径中流水前进；不能把每个 flit 的全部 hop 延迟串行相加。零 payload 定义为不发包；本函数只支持至少一个 hop 的路径。

最关心路由长度、窄链路、flit 粒度与共享端口。公式要求专用、同构、持续可用路径且无背压；没有 packet 分段、虚通道、credit 回程、仲裁或拥塞。不同链路参数或多时钟域应分段建模，不能直接把不同域 cycles 相加。

<!-- model-fields:start -->

### [path.py](path.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NoCPathParams` | `flit_bytes` | `int` | B/flit | Flit 宽度 [B/flit]。 |
| `NoCPathParams` | `header_bytes` | `int` | B/packet | 每个 packet 的协议头 [B/packet]。 |
| `NoCPathParams` | `router_latency_cycles` | `int` | cycle | 每 hop 的头 flit 路由器延迟 [cycle]。 |
| `NoCPathParams` | `link_latency_cycles` | `int` | cycle | 每 hop 的头 flit 链路延迟 [cycle]。 |
| `NoCPathParams` | `flit_ii_cycles` | `int` | cycle/flit | 每 hop 允许的连续 flit 间隔 [cycle/flit]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NoCPathParams` | 每 hop 的固定头部时延与稳态 flit 发起间隔；buffer/VC 竞争未计入。 |
| `estimate_noc_time(p: NoCPathParams, clock: ClockDomain, *, payload_bytes: int, hops: int)` | 给定 H>0、F=ceil((payload+header)/flit_bytes)，尾 flit 在 H*(Lr+Ll)+(F−1)II 完成。 |

<!-- model-fields:end -->
