# die：物理裸片与共享 uncore

Die 使用 [ResourceNode](../UNITS.md) 表达身份和归属，引用 tile、cache、NoC、memory controller、PHY 等资源。Chiplet 是 die 的角色，不能再复制同一裸片的容量。

关键参数仍是实例/父节点/模型/端口身份；几何尺寸 [mm]、面积 [mm²]、功率 [W]、温度 [K] 由 packaging 或特征化结果提供，不在节点里重复保存一套可独立修改的数值。

最关心片内共享路径、外部 I/O 边界和热/功率约束。总容量只汇总唯一存储实例；总硅面积不等于各资源可能重叠的摘要面积之和。固定时钟域引用不能被当作同一电源域。

使用时先定义 die 及子资源，再接上外部端口/几何条件，检查模型选择范围。Die 容器没有额外服务时间，实际 uncore 工作归控制、存储和互连。

<!-- model-fields:start -->



<!-- model-fields:end -->
