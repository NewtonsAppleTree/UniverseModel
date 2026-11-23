# composition：集群装配与逻辑组

C3基础已实现，见 [STATUS](../../docs/STATUS.md)。组合层引用节点/端点/网络实例，保持唯一资源所有权，不产生额外NIC能力。

| 子目录 | 行为 | 关系 |
| --- | --- | --- |
| [groups](groups/UNITS.md) | rank放置与有序组校验 | 成员→节点/端点，组间可重叠 |
| [cluster](cluster/UNITS.md) | 装配、逐路径账本和下界 | 固定消息→服务需求→唯一资源聚合 |

顺序：资源图→placement/group→消息/路由→按基准累计工作→资源/延迟/指定割界。身份无物理单位，消息B、容量B/s、时间s。参数/输入与派生输出分开，账本为局部变量，无队列/时钟。

敏感量为放置、消息矩阵和共享端点，group数量不能倍增带宽。无collective展开或节点内部路径摘要，空通信不表示计算免费。验证共享NIC/交换/上行、守恒、重叠组、失败和同预算放置，见[基础验收](../docs/foundation_usage.md)。

逻辑流量总览可在路径分析前独立调用，按rank、node、endpoint和声明组核对同一需求的守恒；本地/不可达工作保留，不能与可行性结论混用。详见[cluster](cluster/UNITS.md)及[覆盖矩阵](../docs/coverage.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->
