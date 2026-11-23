"""局部Die/Package的归属、地址域边界和时钟一致性；没有额外容器成本。"""

from dataclasses import dataclass

from chipmodel.common import ClockDomain, identifier, typed_tuple
from chipmodel.composition.graph import ResourceNode, validate_graph
from chipmodel.composition.transfer import TransferResources
from chipmodel.interconnect.noc.path import NoCPathParams


# 每个地址/路由域落在一个明确Die或组合的外部边界，域名不决定物理放置。
@dataclass(frozen=True, slots=True, kw_only=True)
class DomainPlacement:
    domain_id: str  # Memory或PathLink引用的地址/路由域身份。
    die_id: str | None  # 已声明Die；None表示Die集合外、scope内的外部边界。

    # 只校验身份；真实归属与domain清单的完整性在装配时检查。
    def __post_init__(self) -> None:
        identifier("domain_id", self.domain_id)
        if self.die_id is not None:
            identifier("die_id", self.die_id)


# 返回每个节点从自身到根的祖先路径；资源图必须完整且无包含环。
def ancestry(nodes: tuple[ResourceNode, ...]) -> dict[str, tuple[str, ...]]:
    validate_graph(nodes, ())
    parents = {n.instance_id: n.parent_id for n in nodes}
    paths = {}
    for key in parents:
        path, current = [], key
        while current is not None:
            path.append(current)
            current = parents[current]
        paths[key] = tuple(path)
    return paths


# 所有节点属于本scope；Die不互相嵌套，最近的声明Die是唯一物理归属。
def die_owners(nodes: tuple[ResourceNode, ...], scope_id: str, die_ids: tuple[str, ...]) -> dict[str, str | None]:
    identifier("scope_id", scope_id)
    die_ids = typed_tuple("die_ids", die_ids, str)
    paths = ancestry(nodes)
    if not die_ids or len(set(die_ids)) != len(die_ids) or not set(die_ids) <= paths.keys():
        raise ValueError("scope requires unique existing die IDs")
    if scope_id not in paths or any(scope_id not in path for path in paths.values()):
        raise ValueError("all resource nodes must belong to the selected local scope")
    if any(len(set(paths[die]) & set(die_ids)) != 1 for die in die_ids):
        raise ValueError("declared dies cannot contain one another")
    return {key: next((p for p in path if p in die_ids), None) for key, path in paths.items()}


# 地址域声明与backing归属一致；NoC留在Die内，跨界串行路径由Die集合之外的scope资源承担。
def validate_placement(resources: TransferResources, scope_id: str, die_ids: tuple[str, ...],
                       domains: tuple[DomainPlacement, ...]) -> dict[str, str | None]:
    if not isinstance(resources, TransferResources):
        raise TypeError("resources must be TransferResources")
    domains = typed_tuple("domains", domains, DomainPlacement)
    owners = die_owners(resources.nodes, scope_id, die_ids)
    placement = {d.domain_id: d.die_id for d in domains}
    used = {m.domain_id for m in resources.memories} | {d for link in resources.links for d in (link.source_domain, link.target_domain)}
    if len(placement) != len(domains) or set(placement) != used:
        raise ValueError("domain placements must cover every used domain exactly once")
    if any(die is not None and die not in die_ids for die in placement.values()):
        raise ValueError("domain references undeclared die")
    for memory in resources.memories:
        if owners[memory.resource_id] != placement[memory.domain_id]:
            raise ValueError("memory address domain disagrees with backing die owner")
    for channel in resources.channels:
        owner = owners[channel.resource_id]
        if owner is not None and any(owners[key] != owner for key in channel.direct_memory_ids):
            raise ValueError("die-local DMA cannot declare a remote memory directly attached")
    for link in resources.links:
        source, target = placement[link.source_domain], placement[link.target_domain]
        if isinstance(link.params, NoCPathParams):
            if source is None or source != target or owners[link.resource_id] != source:
                raise ValueError("NoC path and endpoints must belong to the same die")
        elif source == target or owners[link.resource_id] is not None:
            raise ValueError("cross-boundary serial link requires distinct endpoint owners and a scope-level resource")
    return owners


# 跨域服务先换成second，但相同clock domain身份的频率必须全局一致。
def clock_inventory(resources: TransferResources, compute_clocks: tuple[ClockDomain, ...]) -> tuple[ClockDomain, ...]:
    clocks = list(typed_tuple("compute_clocks", compute_clocks, ClockDomain))
    clocks.extend(m.clock for m in resources.memories if m.clock is not None)
    clocks.extend(c for m in resources.memories if m.dram_read is not None for c in (m.dram_read.ck, m.dram_read.data_clock))
    clocks.extend(c.clock for c in resources.channels)
    clocks.extend(link.clock for link in resources.links if link.clock is not None)
    index = {}
    for clock in clocks:
        if clock.domain_id in index and index[clock.domain_id] != clock:
            raise ValueError("same clock domain identity has inconsistent frequency")
        index[clock.domain_id] = clock
    return tuple(index[key] for key in sorted(index))
