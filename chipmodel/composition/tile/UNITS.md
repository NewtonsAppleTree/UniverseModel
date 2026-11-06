# tile：共享资源的局部组合边界

Tile/Core/SM/Macro 的组合复用父目录的 [ResourceNode](../UNITS.md)，不为名字另造一份空类。参数是 instance_id、parent_id、model_id 和 ports；前三者无物理单位，端口声明 payload 单位/协议。

容器 model_id=None；其子节点引用 MAC/CIM、SRAM/buffer、控制和网络端口。若选择一个完整 tile 摘要成本，则不能同时选择被它覆盖的内部模型作为同一指标的计量方。

最关心共享 SRAM/端口、局部复用、发射边界与 ADC/累加共享。Tile 容量或吞吐必须来自唯一叶子资源和具体使用路径，不能由 tile 名称增加常数。计算需要的数据传输由显式操作承担。

先定义局部资源和端口，再检查归属/连接。独立台架中 tile 可以直接成为根节点，parent_id=None，不要求先构造 Die/Package。没有独立的 tile latency 公式。

<!-- model-fields:start -->



<!-- model-fields:end -->
