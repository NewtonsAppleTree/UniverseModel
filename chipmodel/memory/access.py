"""资源本地byte地址访问；没有数据值、虚拟地址转换或隐式服务成本。"""

from dataclasses import dataclass
from typing import Literal

from chipmodel.common import count, identifier


# 实际访问范围与方向；同一结构可送缓存轨迹或选定介质的适配入口。
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryAccess:
    request_id: str  # 本批唯一访问身份。
    address_bytes: int  # 当前backing的本地byte地址 [B]，非负。
    length_bytes: int  # 请求有效数据长度 [B]，允许0。
    direction: Literal["read", "write"]  # 读或写意图；具体介质必须检查支持能力。

    # 拒绝负地址、隐式数值转换与未知操作；不将写操作套入读profile。
    def __post_init__(self) -> None:
        identifier("request_id", self.request_id)
        count("address_bytes", self.address_bytes, 0)
        count("length_bytes", self.length_bytes, 0)
        if self.direction not in ("read", "write"):
            raise ValueError("memory direction must be read or write")
