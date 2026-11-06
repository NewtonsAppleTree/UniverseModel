# geometry：同层面积与布局可行性

Rectangle 描述位置 [mm] 和尺寸 [mm]，面积为 width*height [mm²]。validate_floorplan 检查所有 block 在给定 boundary 内、同一层内部不重叠；边界接触合法。旋转后的矩形由调用方交换尺寸，不引入隐藏变换。

最关心实际包含边界、keep-out、层身份和面积计量范围。当前没有 keep-out margin、布线拥塞、重叠投影的层标签、TSV/凸点密度；多层需分别调用，不把不同层的重叠投影当作冲突。

输入坐标/尺寸来自布局或假设，校验通过只证明这些矩形约束。不会从面积推导门数、频率、功率或制造成本。使用顺序为边界 → block 矩形 → 同层校验 → 在 composition 中保留实例关联。

<!-- model-fields:start -->

### [floorplan.py](floorplan.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `Rectangle` | `x_mm` | `float` | mm | 左下角 x 坐标 [mm]。 |
| `Rectangle` | `y_mm` | `float` | mm | 左下角 y 坐标 [mm]。 |
| `Rectangle` | `width_mm` | `float` | mm | x 方向尺寸 W [mm]。 |
| `Rectangle` | `height_mm` | `float` | mm | y 方向尺寸 H [mm]。 |
| `Rectangle` | `area_mm2` | `float` | mm² | 只读派生属性；投影面积 A=W*H [mm²]，不等同于多层 stack 的总硅面积。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `Rectangle` | 几何矩形仅描述 footprint；不是芯片计算资源或额外面积收费项。 |
| `Rectangle.area_mm2` | 投影面积 A=W*H [mm²]，不等同于多层 stack 的总硅面积。 |
| `validate_floorplan(boundary: Rectangle, blocks: tuple[Rectangle, ...])` | 同一层的所有 block 必须包含在 boundary 内，且任意两个 block 的内部不重叠。 |

<!-- model-fields:end -->
