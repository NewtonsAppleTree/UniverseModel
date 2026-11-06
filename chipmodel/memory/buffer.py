"""缓冲槽的容量约束；ping-pong 是 slot_count=2 的组织选择。"""

from dataclasses import dataclass

from chipmodel.common import count


# 固定大小槽的保留容量，不复制底层 SRAM，不维护 ready/free 生命周期。
@dataclass(frozen=True, slots=True, kw_only=True)
class BufferParams:
    slot_count: int  # 可保留独立批次的槽数 [slot]。
    slot_bytes: int  # 每槽预留空间 [B/slot]。

    # 槽数与槽大小非零；容量是预留量，不等同于本次 payload。
    def __post_init__(self) -> None:
        count("slot_count", self.slot_count)
        count("slot_bytes", self.slot_bytes)

    # 总保留容量 C=slot_count*slot_bytes [B]。
    @property
    def capacity_bytes(self) -> int:
        return self.slot_count * self.slot_bytes

    # 单槽装载边界：0≤payload_bytes≤slot_bytes；返回不表示实际占有槽位。
    def validate_payload(self, payload_bytes: int) -> None:
        count("payload_bytes", payload_bytes, 0)
        if payload_bytes > self.slot_bytes:
            raise ValueError("payload_bytes exceeds one buffer slot")
