"""轴对齐矩形几何约束；同一层的边界接触允许，内部重叠拒绝。"""

from dataclasses import dataclass

from chipmodel.common import positive, real


# 几何矩形仅描述 footprint；不是芯片计算资源或额外面积收费项。
@dataclass(frozen=True, slots=True, kw_only=True)
class Rectangle:
    x_mm: float  # 左下角 x 坐标 [mm]。
    y_mm: float  # 左下角 y 坐标 [mm]。
    width_mm: float  # x 方向尺寸 W [mm]。
    height_mm: float  # y 方向尺寸 H [mm]。

    # 坐标有限、尺寸严格为正，边界与面积必须可表示。
    def __post_init__(self) -> None:
        real("x_mm", self.x_mm)
        real("y_mm", self.y_mm)
        positive("width_mm", self.width_mm)
        positive("height_mm", self.height_mm)
        real("right_edge_mm", self.x_mm + self.width_mm)
        real("top_edge_mm", self.y_mm + self.height_mm)
        if self.x_mm + self.width_mm <= self.x_mm or self.y_mm + self.height_mm <= self.y_mm:
            raise ValueError("rectangle edges are not distinguishable in binary64")
        positive("area_mm2", self.area_mm2)

    # 投影面积 A=W*H [mm²]，不等同于多层 stack 的总硅面积。
    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.height_mm


# 同一层的所有 block 必须包含在 boundary 内，且任意两个 block 的内部不重叠。
def validate_floorplan(boundary: Rectangle, blocks: tuple[Rectangle, ...]) -> None:
    for i, a in enumerate(blocks):
        if not (boundary.x_mm <= a.x_mm and boundary.y_mm <= a.y_mm
                and a.x_mm + a.width_mm <= boundary.x_mm + boundary.width_mm
                and a.y_mm + a.height_mm <= boundary.y_mm + boundary.height_mm):
            raise ValueError(f"block {i} is outside boundary")
        for b in blocks[:i]:
            if (max(a.x_mm, b.x_mm) < min(a.x_mm + a.width_mm, b.x_mm + b.width_mm)
                    and max(a.y_mm, b.y_mm) < min(a.y_mm + a.height_mm, b.y_mm + b.height_mm)):
                raise ValueError(f"block {i} overlaps another block")
