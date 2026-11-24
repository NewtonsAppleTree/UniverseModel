# RTL 接口与生命周期规范

**状态：文档草案，无HDL实现。** `rtl-stream/v0-draft`是本仓库拟采用的局部数字接口profile，不是公共Python类或标准总线认证。它细化[组件接口提案](../../docs/interfaces/component_protocols.md)和[资源生命周期](../../docs/interfaces/resource_lifecycle.md)，不改变现有代码语义。未声明支持的模式视为不支持。

## 1 身份、边界与参数

每个Unit规格必须给出：Unit/接口版本、对应resource_id/owner、独立输入和输出、时钟/复位域、合法初态、顺序、容量、数值格式和完成条件。身份是文档/实验字段，不要求每项都成为硬件引脚。

| 字段或术语 | 单位/类型 | 约束 |
| --- | --- | --- |
| unit_id、implementation_revision | 标识 | 区分语义单元与具体实现版本；不从名称推断能力 |
| resource_id、owner_id、hierarchy_path | 标识 | 显式映射已有资源与未来层级；实例别名不增加容量 |
| interface_profile | 版本标识 | 两端格式、顺序、时钟和复位规则须兼容，差异由具名适配处理 |
| clock_domain、frequency_hz | 标识、Hz | 频率有限且正；固定频率草案，目标频率与实际可达频率分开 |
| max_inflight_requests | request，正整数 | 已接纳但尚未取走或取消的请求上限，含被背压的响应 |
| payload_bits、address_bits | bit，正整数 | 具体Unit定义；编码宽度不代表物理容量或全部地址合法 |
| request_id、run_epoch | 标识/非负世代 | 用于对照和取消隔离；按序接口可由验证侧维护，不强制增加tag引脚 |

本profile使用一个时钟域、上升沿采样、同步高有效reset、按序响应、一条请求对应一条终态响应。多输出、乱序、分拍/分段、异步复位、跨时钟或零延迟旁路必须另写明确profile及映射，不能隐式沿用。

## 2 基础端口的逻辑含义

方向相对被测Unit；名称允许映射，但含义不可只靠重命名改变。这里只列文档字段，不声明HDL端口代码。

| 逻辑端口 | 方向 | 含义 |
| --- | --- | --- |
| clk | 输入 | 所声明时钟域的采样时钟 |
| rst | 输入 | 同步高有效复位，采样为1的边沿优先于全部握手 |
| in_valid / in_ready | 输入 / 输出 | 生产方提供完整输入拍 / Unit可接纳该拍 |
| in_payload | 输入 | 具名且完整定义的操作数据及必要sideband；不是任意动态字典 |
| out_valid / out_ready | 输出 / 输入 | Unit呈现完整响应 / 消费方可取走该拍 |
| out_payload、out_status | 输出 | 响应内容与ok/error终态；字段宽度/编码由具体Unit给出；保证无运行时错误的Unit可声明status为隐含常量 |

拍是接口传输单位；request是操作单位。基础profile的一拍就是一条请求/响应。后续命令与操作数采用独立流时，必须分别定义命令数、数据拍数、分片身份和完成条件，不能把一个数据拍自动算作一个完整算子。

## 3 握手、稳定性与有限容量

在边沿e_i，使用沿前稳定值判定：

- `accept_i = (rst_i = 0) 且 in_valid_i 且 in_ready_i`。
- `transfer_i = (rst_i = 0) 且 out_valid_i 且 out_ready_i`。
- 当valid=1、ready=0且没有复位时，生产方保持valid以及整份payload/status/sideband，直到握手或复位；这条规则同时适用于输入驱动器和Unit输出。
- valid不能等待ready才产生；消费者可以持续背压，但这样无法无条件保证最终完成。组合连接不得形成ready/valid环；具体实现要声明组合路径与寄存边界。
- ready只表示当前拍的接纳许可。Unit应预留必需状态/响应容量，或证明可通过后续合法流控保护容量；不能接纳后因输出阻塞丢弃数据。

基础profile不允许刚接纳的请求在同一边沿被取走响应。按序接口的响应与尚未结束请求队列一一对应；允许同一边沿接纳新请求并取走旧响应，但是否支持满队列同时入出需在Unit规格中写明。

计数按握手发生次数更新，valid持续多周期只计一次已接纳拍。示意的FIFO占用关系为`q_next = q + accept − transfer`，且`0 ≤ q ≤ capacity`；仅对每拍一个entry的FIFO适用。空FIFO不能在没有旧entry时取走新输入；零延迟fall-through行为不属于本profile。

## 4 接纳、呈现、取走与可见性

| 事件 | 何时成立 | 能说明什么 |
| --- | --- | --- |
| accepted_edge | 输入握手的边沿i | Unit已接纳当前拍；若载荷是地址/描述符，不表示指向的数据已读取或源可以释放 |
| first_presented_edge | 对应响应的out_valid首次能在沿前采到1的边沿j | 响应已在接口上呈现；内部计算可能更早完成，不从本事件反推内部时刻 |
| transferred_edge | 响应握手的边沿k | 消费者已取得该响应，基础请求在接口上结束 |
| source_release / destination_visible | 由具体操作定义 | 源数据能否覆盖、目标对哪个端口/域可见；不由任意done标记自动授予 |

基础profile有`j > i`、`k ≥ j`。`presentation_latency_cycles = j − i`；`response_latency_cycles = k − i`；两者按同一clock_domain换算为秒。若实验截止时尚未呈现/取走，相应值保持未知并列为在途，不能填成零。

独立手算约定：请求在e_10接纳，响应在e_12首次呈现，消费者在e_12和e_13不就绪，e_14取走。则呈现延迟2 cycles、响应延迟4 cycles；e_12至e_14期间响应保持不变。这只是接口示例，没有RTL运行证据。

可选done信号必须说明对应哪个事件；若需要输出在背压时保持，就使用持久valid语义，不能以单周期脉冲代替。本profile的响应取走不自动证明远端内存、缓存一致性或整个任务完成。

## 5 复位、取消与守恒

在采样rst=1的边沿不接纳、不取走；沿后清空本Unit的有效队列状态与响应valid。复位不要求清零所有payload位或存储体内容；初始化/存储保留规则需单独定义。开始实验前必须建立合法复位或初态，不能默认上电寄存器与SRAM均为零。

首次进入一次复位区间时，对仍未结束的请求各记一次aborted，并切换run_epoch；rst连续保持多周期不重复取消或重复计数。新epoch不得输出旧epoch响应。基础profile的两端共享该复位域；独立复位或CDC需适配与单独协议。

复位取消不会回滚已发生的存储副作用。例如写已提交而ack尚未取走时复位，该请求在接口上被取消，但已写数据可仍存在。对副作用操作，终止记录还需说明none/committed/partial/unknown及影响范围；unknown不得当作未写入并直接复用数据。

对完整观察区间，每个请求只落入一个终态或在途类别：

`N_accepted = N_ok_transferred + N_error_transferred + N_aborted + N_inflight`

计数器跨epoch由观察者保存；只观察区间中段时要加区间初始在途量。错误响应被取走前仍属inflight；已取走的成功/错误不得被后续复位再次取消。批量请求、数据拍、MAC、byte和cycle分别计数。

## 6 错误、顺序与终止

结构或不支持的格式在驱动请求前校验；输入valid=1且握手后，就不能把该请求悄悄改为“未提交”。对可报告的运行错误，基础profile返回一条按序error响应，携带原因且不伪造成功数据。不能完成响应的致命协议/工具故障使本次实验失败，并保留在途清单；不补发虚构成功。

顺序以接纳顺序为准。请求身份按未结束队列或显式tag配对；tag若启用，宽度、回绕与复用必须保证尚未结束请求不发生歧义。乱序、主动cancel、重试、多消费者广播和原子操作均需额外规则。

排空测试要列出输入停止点及消费者最终就绪的假设。超时是实验诊断，不自动释放硬件资源或证明死锁；截断记录保存仍未结束的请求。安全性质可在任意背压下检查，最终完成性质必须带环境进展条件。

## 7 可选局部存储细化

`rtl-local-memory/v0-draft`在上述请求/响应之上约定单拍、按序、局部读写：数据宽度W为8的正整数倍，beat_bytes=W/8；请求地址按beat_bytes对齐，且完整拍范围位于声明的物理窗口。地址单位为byte；data的第b个低位字节对应address+b。跨拍、非对齐、虚拟地址、权限转换与burst不隐式加入。

请求payload包含read/write、address，写请求另含data及byte_enable；读返回一个完整拍。写掩码是否支持及后端成本须声明；不支持时只接受全字节使能。非法地址或掩码在实际写入前拒绝/返回错误，不能先产生部分写再声称操作无副作用。

写ack首次呈现前，写入必须已在声明的局部顺序域提交；同端口后续读应看到该已提交写。多端口对同地址的裁决、read-first/write-first/no-change行为与原子性由具体存储规格定义，不能由端口数量推断。局部写提交不代表其他设备或缓存域可见；复位后的副作用遵循第5节。

SRAM行为模型、可综合存储封装和实际宏需要分别标注。bank/word映射、读延迟、byte-enable或RMW行为与[模型映射](model_mapping.md)一起校验；本草案不构成AXI/DRAM控制器协议。

## 8 草案演进

改变握手含义、复位取消、排序、位编码或观察时刻时修改profile身份并说明迁移；单纯参数变化也须保留完整有效参数。具体Unit通过[规格模板](unit_spec_template.md)选择profile并填清差异。本轮只维护文档，未冻结实际引脚表、RTL API或适配器实现。
