# 配置文件

本目录存配置，解析逻辑在 configuration。当前只建立存放位置，尚无可执行 schema 或实验配置。

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

配置应引用模板、实例及成本版本，避免复制互相矛盾的参数。覆盖顺序、派生量和约束见 [configuration 设计](../configuration/docs/design.md)。示意结构放在 example/specs，不能把它当成已可执行配置。
