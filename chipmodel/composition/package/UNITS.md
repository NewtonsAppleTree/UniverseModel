# package：多个 Die、存储与封装路径

Package 复用 [ResourceNode](../UNITS.md) 管理唯一实例，引用 Die、HBM 等存储与 D2D 路径。Board/DIMM/Node 继续由 systemmodel 组合，不因代码复用搬入处理器 Die。

关键量包括封装 footprint [mm²]、总硅面积 [mm²]、堆叠层位置、连接带宽 [B/s]、功率 [W] 和热条件 [K/W]；它们分别来自几何、路径和物理模型，不能用一个 layers 倍率统一计算。

最关心跨 Die 必须传输的字节、共享端点、距离与散热。数组内部层、Die stack depth 与 compute die count 是不同概念。3D 投影面积缩小不表示功耗或总硅面积下降。

先建立资源归属和 D2D 端口，再做路径/工作分析；geometry 的每次 floorplan 校验只对应同一层。当前没有 TSV/键合密度、封装供电或多节点热网络的自动可行性判断。

<!-- model-fields:start -->



<!-- model-fields:end -->
