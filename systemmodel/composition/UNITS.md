# composition：板卡与节点组合

组合层引用topology中唯一的ResourceNode库存。ResourceNode沿用chipmodel的归属/模型身份；无环parent树只表达所有权，外部model_id不会自动import或证明模型能力。节点视图不复制芯片内部状态和容量。

| Unit | 职责 |
| --- | --- |
| [BoardSpec](board/UNITS.md) | 一个纯容器下的设备引用，可对独立板卡或整节点拓扑校验 |
| [NodeSpec](node/UNITS.md) | 多板卡加独立设备；板卡子树互斥、设备不重复或包含内部设备 |

参数是board/resource ID、device_ids、source_ref；无独立物理计量。实际端口/域/容量来自[topology](../topology/UNITS.md)，只声明的设备才进入device_ids，不能把所有支持资源自动当计算设备。

调用顺序：先构造已校验拓扑，再构造BoardSpec并调用validate，最后按需建立NodeSpec。归属循环、跨板误引用、重复设备和摘要/内部设备重叠被拒绝；状态保持不可变。验证见[模型测试](../../tests/systemmodel/test_foundation.py)，此处没有调度或物理校准。

<!-- model-fields:start -->



<!-- model-fields:end -->
