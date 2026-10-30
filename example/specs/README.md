# 结构示例

[heterogeneous_topology.json](heterogeneous_topology.json) 是可检查的**结构关系示例**，不是可执行 HardwareSpec，也不代表已验证的产品架构。字段为示例格式 `illustrative-topology/v1`，不提前锁定后续公共 schema。

示例表达 CPU、GPU、NPU 与 CIM；NPU 逻辑 Die 和 CIM Die 在同一封装堆叠，对外暴露一个双 Die 设备视图；HBF 独立放在板级，NIC 由节点持有。rank/group 引用逻辑视图，视图引用物理实例，不复制资源。

未知容量、性能、阵列层数和介质粒度保持 null，热模式关闭。连接只表达示意邻接，尚不具备完整路由、协议、端口容量或一致性语义。`dies_bottom_to_top` 描述两个物理 Die；CIM 的 `array_layers` 是另一维参数，不能由它推定。

根目录执行 `python tools/check_structure.py`，检查实例唯一、父子无环、端口/设备/通信组引用有效以及堆叠 Die 属于对应封装。此检查不能证明硬件、电气、热或性能可行性。
