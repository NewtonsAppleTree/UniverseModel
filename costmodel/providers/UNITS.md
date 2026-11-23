# providers：成本数据提供方

当前仅[tabulated](tabulated/UNITS.md)有Python实现，拥有不可变条件点集，不拥有硬件状态。输入是专业查询键，输出是带原始点/来源或明确未知原因的CostEstimate。

条件匹配采用结构/PVT/动作单位完全相等，不作公式解释、动态导入、最近点回退或自动外推。最敏感的量为PVT与动作覆盖；缺少符合条件的数据就是未知成本。

使用顺序为读取专业CostTable → 查询 → 独立参考比较；解析公式、外部工具适配和校准拟合仍是[设计](../docs/design.md)中的候选能力。

<!-- model-fields:start -->



<!-- model-fields:end -->
