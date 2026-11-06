# interconnect：通信必须经过真实路径

输入是带大小/格式的消息，输出是协议/线路工作量与无争用时间。物理 lane、逻辑连接、总线协议和拓扑是不同维度，连接多一条不自动增加共享 PHY 的容量。

| 子模块 | Unit | 最关键的量 |
| --- | --- | --- |
| [NoC](noc/UNITS.md) | 专用 wormhole 路径分析 | flit 宽度、头部、hop 数、路由器/链路延迟与 II |
| [D2D](d2d/UNITS.md) | 串行链路分包和线路编码 | lane rate、lane count、编码比、packet overhead |

总线、crossbar、AXI/CHI/TileLink、VC/credit、CDC、重传与 UCIe 等专用状态机尚未实现。以后需端口数、仲裁、ID/顺序、buffer/credit、时钟域和协议版本；不能把本次链路公式解释成协议合规模型。

最关心 payload bytes、协议 bytes、wire bits 的差别和真实共享瓶颈。单方向速率与双向汇总分开。局部连接可成环；拓扑合法性不等于路由无死锁。使用时先确定协议/路径，再取服务估算，最后接入任务依赖与资源约束。

<!-- model-fields:start -->



<!-- model-fields:end -->
