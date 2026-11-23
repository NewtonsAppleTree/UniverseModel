# flash：NAND页、缓冲、外部传输与介质时延

NandGeometry/NandTiming描述page/block/plane/die几何与独立read/program/erase特征时间。CH7的NandReadProfile/Request/State及analyze_nand_reads支持单die、单完整页缓冲、无重叠的串行读取路径。NOR/HBF仍需相应技术规则；NAND不是可任意原位覆盖的SRAM。

page_count=pages/block*blocks/plane*planes/die*dies；raw_data_bytes只含数据，raw_total_bytes另含spare/OOB，均未扣坏块、FTL或预留。NandTiming.estimate_serial为N*t，read/program按page、erase按block；plane/die数不能自动乘吞吐。新读profile明确拒绝多die。

新profile的page_read_s只计阵列→页缓冲；外部输出=(data_bytes+spare_bytes)/output_bytes_per_s，command_overhead_s按非空请求独立计量。选择不连续data/OOB列时，命令成本须包含该选择的全部命令/地址，不自动推断ONFI/SPI事务。miss加载完整data+OOB，hit只输出请求列，换页替换唯一缓冲。空请求不发命令、不加载页、不传输。

调用顺序：几何/时间→来源明确的profile→page/data/OOB范围→可选初态→串行分析。初态/终态显式传递并绑定profile，不把暖页缓冲之前的读取当作免费历史。known_service_s累加已知项；实际触及未知接口或命令成本时modeled_time_s为None。已知完整时间也是声明串行策略的分析值，不是实测。

敏感量为页复用、页大小、请求输出量、tR及接口速率。program/erase只有独立特征时间查询；写入位状态、partial-program限制、FTL/GC/ECC、坏块、retry、耐久和控制器尚未实现。手算、恢复、data/OOB与未知成本验证见[测试](../../../tests/chipmodel/test_memory.py)，来源与研究边界见[指南](../../docs/memory_access.md)。

<!-- model-fields:start -->

### [nand.py](nand.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NandGeometry` | `page_data_bytes` | `int` | B/page | 每页可用数据 [B/page]。 |
| `NandGeometry` | `page_spare_bytes` | `int` | B/page | 每页 OOB/spare [B/page]，可能用于 ECC/管理。 |
| `NandGeometry` | `pages_per_block` | `int` | page/block | 擦除块包含的页数 [page/block]。 |
| `NandGeometry` | `blocks_per_plane` | `int` | block/plane | 每 plane 的块数 [block/plane]。 |
| `NandGeometry` | `planes_per_die` | `int` | plane/die | 每 die 的 plane 数 [plane/die]。 |
| `NandGeometry` | `die_count` | `int` | die | NAND die 数 [die]；不自动代表全部可并行。 |
| `NandGeometry` | `page_count` | `int` | page | 只读派生属性；页总数 pages/block*blocks/plane*planes/die*dies [page]。 |
| `NandGeometry` | `raw_data_bytes` | `int` | B | 只读派生属性；原始数据容量 page_count*page_data_bytes [B]；未扣坏块、FTL 预留和 overprovisioning。 |
| `NandGeometry` | `raw_total_bytes` | `int` | B | 只读派生属性；物理保留字节包含 spare：[data+spare]*page_count [B]。 |
| `NandTiming` | `page_read_s` | `float` | s/page | 单次 page read 服务时间 [s/page]。 |
| `NandTiming` | `page_program_s` | `float` | s/page | 单次 page program 服务时间 [s/page]。 |
| `NandTiming` | `block_erase_s` | `float` | s/block | 单次 block erase 服务时间 [s/block]。 |
| `NandReadProfile` | `geometry` | `NandGeometry` | —（结构/对象） | 本路径仅支持一个die，plane不隐含并行。 |
| `NandReadProfile` | `timing` | `NandTiming` | —（结构/对象） | page_read_s只计阵列→页缓冲，program/erase不用于读取。 |
| `NandReadProfile` | `output_bytes_per_s` | `float \| None` | B/s | 外部输出有效字节速率 [B/s]；None表示未知。 |
| `NandReadProfile` | `command_overhead_s` | `float \| None` | s | 每非空请求的命令/地址总开销 [s]；0须为显式理想假设。 |
| `NandReadProfile` | `profile_source` | `str` | 1（标识/枚举） | 器件特征或合成实验来源及适用条件。 |
| `NandReadRequest` | `request_id` | `str` | 1（标识/枚举） | 批内唯一读取身份。 |
| `NandReadRequest` | `page_index` | `int` | page | 物理页号 [page]，范围由profile约束。 |
| `NandReadRequest` | `data_offset_bytes` | `int` | B | 数据区起始列 [B]。 |
| `NandReadRequest` | `data_bytes` | `int` | B | 输出数据区字节数 [B]。 |
| `NandReadRequest` | `spare_offset_bytes` | `int` | B | OOB区起始列 [B]。 |
| `NandReadRequest` | `spare_bytes` | `int` | B | 输出OOB字节数 [B]，不隐含ECC计算。 |
| `NandReadState` | `profile` | `NandReadProfile` | —（结构/对象） | 快照绑定的完整profile；恢复时禁止跨profile复用。 |
| `NandReadState` | `buffered_page` | `int \| None` | page | 有效物理页号 [page]；None为冷缓冲。 |
| `NandReadStep` | `request_id` | `str` | 1（标识/枚举） | 输入读取身份。 |
| `NandReadStep` | `page_buffer_hit` | `bool \| None` | —（结构/对象） | 非空请求的页缓冲命中；空请求为None。 |
| `NandReadStep` | `array_read_pages` | `int` | page | 本步阵列读取次数 [page]，miss为1。 |
| `NandReadStep` | `array_loaded_bytes` | `int` | B | miss*(page_data_bytes+page_spare_bytes) [B]。 |
| `NandReadStep` | `data_output_bytes` | `int` | B | 外部数据区输出 [B]。 |
| `NandReadStep` | `spare_output_bytes` | `int` | B | 外部OOB输出 [B]。 |
| `NandReadStep` | `array_service_s` | `float` | s | array_read_pages*page_read_s [s]。 |
| `NandReadStep` | `output_service_s` | `float \| None` | s | (data+OOB)/output_rate [s]；有工作且速率未知时为None。 |
| `NandReadStep` | `command_service_s` | `float \| None` | s | 非空请求的命令成本 [s]；缺失时为None。 |
| `NandReadAnalysis` | `steps` | `tuple[NandReadStep, ...]` | —（结构/对象） | 请求顺序的逐项服务与命中结果。 |
| `NandReadAnalysis` | `final_state` | `NandReadState` | —（结构/对象） | 最终缓冲page；可显式恢复。 |
| `NandReadAnalysis` | `array_read_pages` | `int` | page | 实际阵列读取总数 [page]。 |
| `NandReadAnalysis` | `data_output_bytes` | `int` | B | 累计外部data输出 [B]。 |
| `NandReadAnalysis` | `spare_output_bytes` | `int` | B | 累计外部OOB输出 [B]。 |
| `NandReadAnalysis` | `known_service_s` | `float` | s | 串行已知分项之和 [s]；缺项时只是条件下界。 |
| `NandReadAnalysis` | `modeled_time_s` | `float \| None` | s | 无重叠串行策略的总分析时间 [s]；缺项时未知。 |
| `NandReadAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | 已触及的缺失接口或命令成本，不以零替代。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NandGeometry` | NAND 介质几何；数据容量与 spare/OOB 字节分开。 |
| `NandGeometry.page_count` | 页总数 pages/block*blocks/plane*planes/die*dies [page]。 |
| `NandGeometry.raw_data_bytes` | 原始数据容量 page_count*page_data_bytes [B]；未扣坏块、FTL 预留和 overprovisioning。 |
| `NandGeometry.raw_total_bytes` | 物理保留字节包含 spare：[data+spare]*page_count [B]。 |
| `NandTiming` | 一条串行介质路径的已特征化时延；读/写/擦除分别对应不同粒度。 |
| `NandTiming.estimate_serial(self, operation: str, operation_count: int)` | T=N*t_operation [s]；N 对 read/program 为 page 数，对 erase 为 block 数。 |
| `NandReadProfile` | 单die、单页缓冲、串行读取路径；阵列page service与外部data/OOB传输分别计量。 |
| `NandReadRequest` | 页号和data/OOB列范围各自独立；不把spare当作可用数据容量。 |
| `NandReadState` | 显式页缓冲快照；只描述哪个page有效，不携带数据值或器件隐藏状态。 |
| `NandReadStep` | 单请求服务分项；空请求不触发page读取、命令或传输。 |
| `NandReadAnalysis` | 同一die串行策略的分析结果；完整时间只在所有分项已知时成立。 |
| `analyze_nand_reads(profile: NandReadProfile, requests: tuple[NandReadRequest, ...], *, initial_state: NandReadState \| None=None)` | miss整页加载，hit只读输出列；前一请求完成后才开始下一条，没有die/plane并行推断。 |

<!-- model-fields:end -->
