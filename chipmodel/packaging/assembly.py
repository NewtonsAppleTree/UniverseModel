"""将CH8已计量服务映射到物理动作，不把时间下界当作观测窗口。"""

from chipmodel.composition.package.assembly import AssemblyAnalysis
from chipmodel.composition.transfer import dram_budgets, sram_budgets
from chipmodel.packaging.evidence import CostActivity, PhysicalModel, PhysicalWork, Placement, ResourceStructure
from chipmodel.packaging.geometry.floorplan import Rectangle
from contracts.versions.json_codec import content_hash
from costmodel.interfaces.costs import CostSource, OperatingPoint


# 保留全部物理实例并以完整参数哈希构造结构身份；实际器件profile不能仅凭通用名称替换。
def assembly_physical_model(analysis: AssemblyAnalysis, operating_point: OperatingPoint, *, boundary: Rectangle,
                            placements: tuple[Placement, ...], geometry_source: CostSource) -> PhysicalModel:
    if not isinstance(analysis, AssemblyAnalysis):
        raise TypeError("analysis must be AssemblyAnalysis")
    assembly = analysis.assembly
    resources = [(r.resource_id, {"kind": "memory", "capacity_bytes": r.capacity_bytes, "sram": r.sram,
                  "frequency_hz": r.clock.frequency_hz if r.clock else None, "dram_read": r.dram_read}) for r in assembly.resources.memories]
    resources += [(r.resource_id, {"kind": "dma", "params": r.params, "frequency_hz": r.clock.frequency_hz}) for r in assembly.resources.channels]
    resources += [(r.resource_id, {"kind": "link", "params": r.params, "frequency_hz": r.clock.frequency_hz if r.clock else None}) for r in assembly.resources.links]
    structures = [ResourceStructure(resource_id=key, structure_id="ch8:" + content_hash(params),
                                    operating_point=operating_point) for key, params in resources]
    structures.extend(ResourceStructure(resource_id=t.mac_resource_id, structure_id="ch8:" + content_hash({"kind": "MAC",
                      "params": t.mac.params, "frequency_hz": t.mac.clock.frequency_hz, "arithmetic": t.mac.arithmetic}),
                      operating_point=operating_point) for t in assembly.tiles)
    ids = tuple(s.resource_id for s in structures)
    return PhysicalModel(scope_id=assembly.scope_id, nodes=assembly.resources.nodes, physical_ids=ids,
        structures=tuple(structures), static_selection=ids, boundary=boundary, placements=placements, geometry_source=geometry_source)


# 服务量只提供已声明动作子集；DRAM行命令和无服务模型的存储成本另记未知。
def assembly_physical_work(analysis: AssemblyAnalysis) -> PhysicalWork:
    if not isinstance(analysis, AssemblyAnalysis):
        raise TypeError("analysis must be AssemblyAnalysis")
    resources = analysis.assembly.resources
    mapping, unknown, sram_ids = {}, [], set()
    for memory in resources.memories:
        for budget in sram_budgets(memory):
            sram_ids.add(budget.resource_id)
        for budget in dram_budgets(memory):
            mapping[budget.resource_id] = (memory.resource_id, "dram_read_byte")
        if memory.dram_read is not None:
            unknown.append(f"{memory.resource_id}: burst read bytes omit activation/precharge/refresh and writes")
        elif memory.sram is None:
            unknown.append(f"{memory.resource_id}: capacity-only memory has no physical activity model")
    mapping.update({c.resource_id: (c.resource_id, "dma_cycle") for c in resources.channels})
    mapping.update({link.resource_id: (link.resource_id, "noc_flit" if link.clock is not None else "wire_bit") for link in resources.links})
    mapping.update({t.mac_resource_id: (t.mac_resource_id, "MAC") for t in analysis.assembly.tiles})
    activities = []
    # 共享RW端口是供给约束，不是能量动作；使用原服务计数保留读写差异。
    for resource, service in analysis.memory_services:
        for bank, (reads, writes) in enumerate(zip(service.bank_reads, service.bank_writes)):
            for direction, amount in (("read", reads), ("write", writes)):
                activities.append(CostActivity(activity_id=f"sram/{len(resource)}:{resource}/{bank}/{direction}",
                    resource_id=resource, action=direction + "_word", work_unit="word", amount=amount))
    for contribution in analysis.contributions:
        if contribution.resource_id in sram_ids:
            continue
        resource, action = mapping[contribution.resource_id]
        activities.append(CostActivity(activity_id=f"service/{len(contribution.resource_id)}:{contribution.resource_id}", resource_id=resource, action=action,
                                       work_unit=contribution.work_unit, amount=contribution.amount))
    return PhysicalWork(activities=tuple(activities), activity_source="CH8 analysis SHA256:" + content_hash(analysis),
                        unknown_activity=tuple(unknown), observation=None)
