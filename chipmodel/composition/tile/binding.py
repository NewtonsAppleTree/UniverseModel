"""数字Tile只引用共享清单中的资源；多个Tile不复制backing或通道预算。"""

from dataclasses import dataclass

from chipmodel.common import identifier
from chipmodel.composition.tile.digital import DigitalTile
from chipmodel.composition.transfer import TransferResources
from chipmodel.compute.npu.mac import MacArray


# 一个Tile的计算资源配置与scratch引用；物理归属由组合清单统一校验。
@dataclass(frozen=True, slots=True, kw_only=True)
class TileBinding:
    tile_id: str  # Tile容器节点身份；不是额外服务资源。
    scratch_id: str  # 唯一SRAM backing引用，可被同die其他Tile共享。
    mac_resource_id: str  # 本Tile独占MAC叶子资源身份。
    mac: MacArray  # 操作/格式、P/L/II、时钟及来源；不另增一份MAC。

    # 固定引用和配置；bind时检查清单中的实际资源存在性与计量互斥。
    def __post_init__(self) -> None:
        for name in ("tile_id", "scratch_id", "mac_resource_id"):
            identifier(name, getattr(self, name))
        if not isinstance(self.mac, MacArray):
            raise TypeError("mac must be MacArray")

    # 同一清单可构造独立Tile视图；调用方不能把多个视图的共享预算相加。
    def bind(self, resources: TransferResources) -> DigitalTile:
        return DigitalTile(resources=resources, scratch_id=self.scratch_id, mac_resource_id=self.mac_resource_id,
                           mac=self.mac.params, compute_clock=self.mac.clock, mac_arithmetic=self.mac.arithmetic,
                           mac_profile_source=self.mac.profile_source)
