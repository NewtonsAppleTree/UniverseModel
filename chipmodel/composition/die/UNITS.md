# die：物理裸片与共享 uncore

Die 使用 [ResourceNode](../UNITS.md) 表达身份和归属，引用 tile、cache、NoC、memory controller、PHY 等资源。Chiplet 是 die 的角色，不能再复制同一裸片的容量。

关键参数仍是实例/父节点/模型/端口身份；几何尺寸 [mm]、面积 [mm²]、功率 [W]、温度 [K] 由 packaging 或特征化结果提供，不在节点里重复保存一套可独立修改的数值。

最关心片内共享路径、外部 I/O 边界和热/功率约束。总容量只汇总唯一存储实例；总硅面积不等于各资源可能重叠的摘要面积之和。固定时钟域引用不能被当作同一电源域。

使用时先定义 die 及子资源，再接上外部端口/几何条件，检查模型选择范围。Die 容器没有额外服务时间，实际 uncore 工作归控制、存储和互连。

## CH8实际拓扑验证

[topology.py](topology.py)实现DomainPlacement、ancestry、die_owners、validate_placement和clock_inventory。每个使用中的memory/route域必须恰好映射到一个声明Die，或None表示本scope中的外部边界；memory域与backing归属一致，声明Die不互相嵌套。单Die可直接作为scope根，无额外Die成本。

先构造ResourceNode/TransferResources，再声明domain/Die范围并验证。NoC资源及两端在同一Die，完整有向跨界串行link归scope层；Die内DMA不能声明远程memory直接附加。clock_inventory将MAC/SRAM/DMA/NoC/DRAM时钟去重，同名不同频拒绝；不同域服务换成second但不推导CDC开销。

关键量为唯一实例、domain→Die位置、方向与clock身份，它们决定可允许的路径及共享范围。映射变化不会自动搬移数据、增加容量或证明物理布线可行。独立反例及两Die流量参考见[CH8指南](../../docs/assembly.md)和[芯片测试](../../../tests/chipmodel/test_assembly.py)。

<!-- model-fields:start -->

### [topology.py](topology.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DomainPlacement` | `domain_id` | `str` | 1（标识/枚举） | Memory或PathLink引用的地址/路由域身份。 |
| `DomainPlacement` | `die_id` | `str \| None` | 1（标识/枚举） | 已声明Die；None表示Die集合外、scope内的外部边界。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DomainPlacement` | 每个地址/路由域落在一个明确Die或组合的外部边界，域名不决定物理放置。 |
| `ancestry(nodes: tuple[ResourceNode, ...])` | 返回每个节点从自身到根的祖先路径；资源图必须完整且无包含环。 |
| `die_owners(nodes: tuple[ResourceNode, ...], scope_id: str, die_ids: tuple[str, ...])` | 所有节点属于本scope；Die不互相嵌套，最近的声明Die是唯一物理归属。 |
| `validate_placement(resources: TransferResources, scope_id: str, die_ids: tuple[str, ...], domains: tuple[DomainPlacement, ...])` | 地址域声明与backing归属一致；NoC留在Die内，跨界串行路径由Die集合之外的scope资源承担。 |
| `clock_inventory(resources: TransferResources, compute_clocks: tuple[ClockDomain, ...])` | 跨域服务先换成second，但相同clock domain身份的频率必须全局一致。 |

<!-- model-fields:end -->
