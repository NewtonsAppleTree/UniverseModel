# 配置文件

[attention_mapping.json](experiments/attention_mapping.json)固定任务/资源比较5个映射；[retrieval_quality.json](experiments/retrieval_quality.json)固定3个split×4个数值变体。真实[UCI Iris来源](workloads/iris/README.md)含原始数据、元数据、署名/许可与哈希；详情见[W4/W5指南](../workloads/docs/mapping_and_quality.md)。

[attention_workloads.json](experiments/attention_workloads.json)声明10个有限Attention合成案例及宿主预算；[attention_inputs.json](workloads/attention_inputs.json)为原始SHA256绑定的本地手算输入。来源、用途与形状身份规则见[workloads指南](../workloads/docs/foundation_usage.md)，这些配置不声明真实模型分布。

本目录存配置，解析逻辑在 configuration。可用 schema 与实验配置的完成情况见[实现状态](../docs/STATUS.md)。

[cluster_leaf_spine.json](experiments/cluster_leaf_spine.json)声明六节点、三leaf、双spine与30条1 MiB合成需求，可选outage保存静态停用条件；见[横向指南](../clustermodel/docs/breadth_usage.md)。

[cluster_placement.json](experiments/cluster_placement.json)提供C1–C3四节点ClusterStudy：相同图/组/消息，显式A/B放置，计量与来源进入记录。见[基础指南](../clustermodel/docs/foundation_usage.md)。

[network_link.json](experiments/network_link.json)是C1可运行的NetworkCase，包含只读NIC端点/约束、两个物理方向、所选链路及独立消息输入；字段由contracts/clustermodel的冻结dataclass解释，见[C1指南](../clustermodel/docs/c1_usage.md)。示例参数均为显式手工假设。

| 目录 | 内容 |
| --- | --- |
| hardware/components | 可复用组件模板与能力参数 |
| hardware/chips | Tile/Die/Package 实例组合 |
| hardware/systems | Board/Node、地址与节点路径 |
| hardware/clusters | 节点引用、fabric、资源组 |
| costs/compute、memory、interconnect、packaging | 成本依据、工作条件和版本引用 |
| compiler | 划分、切块、放置和静态策略 |
| runtime | streams、派发、collective 与动态策略 |
| simulation | 时间精度、事件、上限与观测设置 |
| experiments | 负载、基线、搜索空间和比较协议 |
| workloads | 带来源/字节哈希的本地任务数据夹具 |

配置应引用模板、实例及成本版本，避免复制互相矛盾的参数。覆盖顺序、派生量和约束见 [configuration 设计](../configuration/docs/design.md)。示意结构放在 example/specs，不能把它当成已可执行配置。

`experiments/system_connectivity.json`：S0/S1主机/双卡静态路径，3成功与4预期失败。16/8 GB/s为手工payload条件声明，当前不计算节点性能；见[指南](../systemmodel/docs/foundation_usage.md)。
