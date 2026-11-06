"""资源归属、静态端口连接和计量选择；物理连接可有环，包含关系不允许有环。"""

from dataclasses import dataclass

from chipmodel.common import identifier


# 一个静态端口的边界契约；协议身份必须包含双方约定的编码/shape 语义。
@dataclass(frozen=True, slots=True, kw_only=True)
class Port:
    name: str  # 节点内唯一端口名；无量纲标识。
    direction: str  # input 或 output；双向接口显式拆为两个端口。
    protocol: str  # 协议/数值格式版本标识，不根据单位自动推断。
    unit: str  # Payload 物理量单位，如 V、A、code、B。

    # 只接受明确的方向和非空身份/单位。
    def __post_init__(self) -> None:
        for name in ("name", "protocol", "unit"):
            identifier(name, getattr(self, name))
        if self.direction not in ("input", "output"):
            raise ValueError("direction must be input or output")


# Tile/Die/Package 与叶子资源共用归属节点；容器 model_id=None，不额外计费。
@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceNode:
    instance_id: str  # 整张图唯一的物理实例身份。
    parent_id: str | None  # 归属父节点；局部台架根节点为 None。
    model_id: str | None  # 可选成本/功能模型身份；None 表示纯容器。
    ports: tuple[Port, ...] = ()  # 本节点端口定义；空 tuple 表示没有声明端口。

    # 冻结端口集合并校验节点内名称唯一；跨节点约束在装配时校验。
    def __post_init__(self) -> None:
        identifier("instance_id", self.instance_id)
        for name in ("parent_id", "model_id"):
            if getattr(self, name) is not None:
                identifier(name, getattr(self, name))
        object.__setattr__(self, "ports", tuple(self.ports))
        if len({p.name for p in self.ports}) != len(self.ports):
            raise ValueError("duplicate port name")


# 一条有向连接只引用现存端口；协议转换器必须作为显式节点出现。
@dataclass(frozen=True, slots=True, kw_only=True)
class Connection:
    source_id: str  # 源实例身份。
    source_port: str  # 源 output 端口名。
    target_id: str  # 目标实例身份。
    target_port: str  # 目标 input 端口名。


# 校验唯一身份、无环包含与端口兼容；允许局部多根资源及 ring 等有环连接。
def validate_graph(nodes: tuple[ResourceNode, ...], connections: tuple[Connection, ...]) -> None:
    index = {node.instance_id: node for node in nodes}
    if len(index) != len(nodes):
        raise ValueError("duplicate instance_id")
    for node in nodes:
        seen = {node.instance_id}
        parent = node.parent_id
        while parent is not None:
            if parent not in index or parent in seen:
                raise ValueError("missing parent or containment cycle")
            seen.add(parent)
            parent = index[parent].parent_id
    ports = {(node.instance_id, p.name): p for node in nodes for p in node.ports}
    for edge in connections:
        try:
            source = ports[(edge.source_id, edge.source_port)]
            target = ports[(edge.target_id, edge.target_port)]
        except KeyError as exc:
            raise ValueError("connection references unknown port") from exc
        if source.direction != "output" or target.direction != "input":
            raise ValueError("connection must go from output to input")
        if (source.protocol, source.unit) != (target.protocol, target.unit):
            raise ValueError("protocol/unit mismatch; add an explicit adapter")


# 同一指标口径中选择摘要或内部细模型；祖先和后代不可同时成为收费方。
def validate_model_selection(nodes: tuple[ResourceNode, ...], selected_ids: tuple[str, ...]) -> None:
    validate_graph(nodes, ())
    index = {node.instance_id: node for node in nodes}
    selected = set(selected_ids)
    if len(selected) != len(selected_ids):
        raise ValueError("duplicate selected resource")
    for instance in selected:
        if instance not in index or index[instance].model_id is None:
            raise ValueError("selected resource has no model")
        parent = index[instance].parent_id
        while parent is not None:
            if parent in selected:
                raise ValueError("summary and descendant models overlap in accounting")
            parent = index[parent].parent_id
