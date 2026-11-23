"""缓冲槽的容量约束；ping-pong 是 slot_count=2 的组织选择。"""

from dataclasses import dataclass

from chipmodel.common import count, identifier, typed_tuple


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


# 一组连续槽仅引用 backing 地址，不新增物理容量或存储时延。
@dataclass(frozen=True, slots=True, kw_only=True)
class BufferReservation:
    reservation_id: str  # 此次装配内唯一预留身份。
    backing_id: str  # 唯一底层存储资源 ID。
    offset_bytes: int  # 第一个槽在 backing 中的地址 [B]。
    buffer: BufferParams  # 连续等长槽；覆盖 slot_count*slot_bytes [B]。

    # 冻结显式 backing 引用；重叠、容量在共同装配中检查。
    def __post_init__(self) -> None:
        identifier("reservation_id", self.reservation_id)
        identifier("backing_id", self.backing_id)
        count("offset_bytes", self.offset_bytes, 0)
        if not isinstance(self.buffer, BufferParams):
            raise TypeError("buffer must be BufferParams")


# 半开区间 [offset,offset+capacity) 不得重叠；此接口不声明别名或动态释放。
def validate_reservations(backing_id: str, capacity_bytes: int,
                          reservations: tuple[BufferReservation, ...]) -> None:
    identifier("backing_id", backing_id)
    count("capacity_bytes", capacity_bytes)
    reservations = typed_tuple("reservations", reservations, BufferReservation)
    if len({r.reservation_id for r in reservations}) != len(reservations):
        raise ValueError("duplicate reservation_id")
    end = 0
    for reservation in sorted(reservations, key=lambda r: r.offset_bytes):
        if reservation.backing_id != backing_id:
            raise ValueError("reservation backing identity mismatch")
        if reservation.offset_bytes < end:
            raise ValueError("overlapping backing reservations")
        end = reservation.offset_bytes + reservation.buffer.capacity_bytes
        if end > capacity_bytes:
            raise ValueError("reservation exceeds backing capacity")
