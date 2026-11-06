# flash：NAND 的页、擦除块与介质时延

本轮只实现 NandGeometry 和 NandTiming，NOR/HBF 仍需对应技术的规则。Page read/program 与 block erase 是不同操作，不能把 NAND 当成可原位任意覆盖的 SRAM。

page_count=pages/block*blocks/plane*planes/die*dies；raw_data_bytes 只含数据，raw_total_bytes 再含 spare。两个值均未扣坏块、FTL 元数据或 overprovisioning，不能当作主机逻辑容量。

NandTiming 接收显式特征时间，串行服务 T=N*t。read/program 的 N 是页数，erase 的 N 是块数。plane/die 数不自动乘吞吐；plane 命令约束和共享接口必须另建模型。

最关心访问粒度、读/编程/擦除差异、通道共享、写放大、GC、ECC、坏块与耐久。后几项未实现；read/program 时间是否包括接口传输由来源边界说明。使用时先定义几何，再提供特征时间与实际操作计数。

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

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NandGeometry` | NAND 介质几何；数据容量与 spare/OOB 字节分开。 |
| `NandGeometry.page_count` | 页总数 pages/block*blocks/plane*planes/die*dies [page]。 |
| `NandGeometry.raw_data_bytes` | 原始数据容量 page_count*page_data_bytes [B]；未扣坏块、FTL 预留和 overprovisioning。 |
| `NandGeometry.raw_total_bytes` | 物理保留字节包含 spare：[data+spare]*page_count [B]。 |
| `NandTiming` | 一条串行介质路径的已特征化时延；读/写/擦除分别对应不同粒度。 |
| `NandTiming.estimate_serial(self, operation: str, operation_count: int)` | T=N*t_operation [s]；N 对 read/program 为 page 数，对 erase 为 block 数。 |

<!-- model-fields:end -->
