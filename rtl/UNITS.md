# RTL：候选 Unit 与参数导航

本目录当前只有设计文档，**没有已实现或已验证的RTL Unit**。候选按实际行为划分，不把参数、结果对象或技术型号各算成一个硬件单元；使命与实现状态分别见[项目使命](../PROJECT_MISSION.md)和[STATUS](../docs/STATUS.md)。

## 候选行为及现有模型

| 候选 Unit | 支持的研究问题 | 已有可复用模型/参考 | 将来需要的额外证据 |
| --- | --- | --- | --- |
| 整数MAC／点积 | 位宽、归约依赖与流水线如何影响结果和服务 | [NPU模型](../chipmodel/compute/npu/UNITS.md)、[Linear参考](../workloads/reference/linear.py) | 位精确结果、逐步溢出、接纳/输出周期；MacArray目前只分析服务能力 |
| FIFO／寄存缓冲 | 有限槽与背压如何限制供数 | [buffer预留](../chipmodel/memory/buffer.py)只提供空间依据 | 顺序、容量、同时入出、复位和阻塞稳定性；尚无FIFO状态模型可直接视为黄金参考 |
| SRAM接口／封装 | bank、端口、读写语义和仲裁如何影响供数 | [SRAM](../chipmodel/memory/sram/UNITS.md)的事务/条件服务分析 | 数据值、冲突裁决、同地址读写、实际存储实现及响应时序 |
| 局部搬运控制 | 启动、突发、端口等待产生哪些代价 | [DMA与布局](../chipmodel/control/UNITS.md) | 字节/掩码守恒、请求与数据拍绑定、完成/可见性；不是完整PCIe/AXI实现 |
| 数字Tile | 固定任务/预算下，计算与供数的瓶颈来自哪里 | [数字Tile](../chipmodel/composition/tile/UNITS.md)、workloads/compiler独立参考 | 有限资源下的数值和周期轨迹、所有权及内部/摘要互斥计量 |
| CIM数字外围 | 编码、ADC码重建与有限位宽累加的收益/代价 | [CIM台架](../chipmodel/docs/cim_bench.md) | 逐级定点语义、溢出、控制时序及与模拟行为模型的边界 |

CPU完整核、GPU执行后端、DRAM控制器、模拟ADC/DAC和电导阵列不作为本轮候选必交付项。后续需要时分别声明协议、工具和参考范围。

## 参数、状态和观测的维护源

| 类别 | 术语与单位 | 关系或边界 | 定义位置 |
| --- | --- | --- | --- |
| 设计输入 | operand/accumulator位宽[bit]、K[MAC/点积]、lane数[lane] | 数值域、扩展、舍入和逐步/最终溢出策略分开；位宽不同不能默认只改吞吐 | [模型映射](docs/model_mapping.md) |
| 设计输入 | 时钟域、频率[Hz]、reset profile | 默认草案单时钟、上升沿、同步高有效复位；不同profile需显式适配 | [接口](docs/interfaces.md) |
| 设计输入 | 容量[entry/B]、数据/地址宽度[bit] | entry容量不能与字节容量混算；地址可编码范围不是物理容量 | [接口](docs/interfaces.md) |
| 派生/条件服务 | 延迟L、II[cycle/domain]、批次工作量 | 接口边沿时间与公共流水线服务的item口径需显式映射 | [模型映射](docs/model_mapping.md) |
| 动态状态 | 在途请求[request]、有效/就绪、epoch、FIFO占用[entry] | 本轮只定义语义；状态由未来具体实现拥有 | [接口](docs/interfaces.md) |
| 观测 | 接纳/呈现/取走边沿、成功/错误/取消计数 | 不以valid持续周期数冒充请求数；写入可见性单独定义 | [接口](docs/interfaces.md) |
| 物理与来源 | 面积、频率、功率、能量、工具/库版本 | 仅在适用条件完整时报告；未测量不填零 | [验证](docs/verification.md) |

关键敏感参数是数值格式、累加位宽、归约长度、L/II、有限槽、bank/端口、消费者阻塞条件及目标时钟。依据先查[参数清单](../ARCHITECTURE_PARAMETERS.md)，再由具体Unit规格选取；本表不创建配置schema或Python字段。

调用设计顺序：问题/基线 → [单元规格](docs/unit_spec_template.md) → 参数/初态/参考 → 后续工具执行 → 结果对照/周期解释 → 来源与未知项保存。本轮在文档与接口约定处结束。子目录见[docs/UNITS](docs/UNITS.md)。
