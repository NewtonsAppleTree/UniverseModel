# packaging：几何与能量平衡的物理约束

本模块保存/分析物理条件，不重复创建或执行计算/存储单元。当前提供 [geometry](geometry/UNITS.md) 的矩形 floorplan 校验和 [thermal](thermal/UNITS.md) 的一阶热 RC。

最关心面积范围、同层重叠、功率来源、热路径及温度适用域。面积从几何 A=W*H 得到；温度从热能量平衡得到，不能由芯片模块数量直接推断。

供电 PDN、IR drop、PVT、制造良率、KGD、bonding/TSV、老化尚未实现；相应关键量是电压/电阻/电流、热/机械条件、条件概率和校准来源。未知能量/面积/可靠性不能填零进入总成本。

使用顺序：关联实例的几何/工作条件 → 校验物理边界 → 输入有来源的功率/特征值 → 查询结果。动态功率反馈到 DVFS 或 ADC 误差需要后续显式耦合，不在纯静态参数公式里造环。

<!-- model-fields:start -->



<!-- model-fields:end -->
