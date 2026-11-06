"""根目录运行 python -m example.chipmodel_demo；独立查询与局部系统时间界。"""

from dataclasses import asdict
import json

from chipmodel.common import ClockDomain, PipelineParams
from chipmodel.compute.npu.mac import GemmWorkload, MacArray
from chipmodel.control.data_movement import DmaParams, estimate_dma
from chipmodel.memory.buffer import BufferParams
from chipmodel.memory.dram.organization import DramOrganization
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, estimate_time_bounds
from chipmodel.composition.graph import ResourceNode, validate_model_selection


# 将一项 GEMM 的装载/计算/写回组织为操作 DAG，输出显式覆盖范围内的必要时间界。
def main() -> None:
    clock = ClockDomain(domain_id="tile", frequency_hz=1e9)  # 示例时钟 [Hz]，未作电路校准。
    work = GemmWorkload(m=2, n=3, k=4, operand_bits=8, output_bits=32)
    mac = MacArray(params=PipelineParams(lane_count=4, latency_cycles=3,
                                        initiation_interval_cycles=1), clock=clock)
    dma = DmaParams(bytes_per_cycle=8, max_burst_bytes=16, startup_cycles=1, burst_overhead_cycles=0)
    buffer = BufferParams(slot_count=2, slot_bytes=work.input_bytes + work.output_bytes)
    buffer.validate_payload(work.input_bytes + work.output_bytes)
    load = estimate_dma(dma, clock, work.input_bytes)
    compute = mac.estimate(work.mac_count)
    store = estimate_dma(dma, clock, work.output_bytes)

    # 一个 tile 容器引用两个计时资源；缓冲是容量约束，不另收费一份 SRAM。
    nodes = (ResourceNode(instance_id="tile", parent_id=None, model_id=None),
             ResourceNode(instance_id="dma", parent_id="tile", model_id="isolated-dma/v1"),
             ResourceNode(instance_id="mac", parent_id="tile", model_id="mac-pipeline/v1"))
    validate_model_selection(nodes, ("dma", "mac"))
    budgets = (
        ResourceBudget(resource_id="dma", work_unit="B", rate_per_s=8e9, initial_credit=8),
        ResourceBudget(resource_id="mac", work_unit="MAC", rate_per_s=4e9, initial_credit=4),
    )
    actions = (
        ActionEstimate(action_id="load", latency_s=load.completion_time_s, dependencies=(), demands=(
            ResourceDemand(resource_id="dma", work_unit="B", amount=work.input_bytes),)),
        ActionEstimate(action_id="compute", latency_s=compute.completion_time_s,
                       dependencies=("load",), demands=(
                           ResourceDemand(resource_id="mac", work_unit="MAC", amount=work.mac_count),)),
        ActionEstimate(action_id="store", latency_s=store.completion_time_s,
                       dependencies=("compute",), demands=(
                           ResourceDemand(resource_id="dma", work_unit="B", amount=work.output_bytes),)),
    )

    # DDR 也可以单独查询；本段没有接入上述台架，不能把带宽结果当作供数已满足。
    dram = DramOrganization(technology="assumed-ddr-5600", channel_count=1, ranks_per_channel=1,
                            banks_per_rank=16, rows_per_bank=32768, columns_per_row=1024,
                            payload_width_bits=64, data_rate_mt_s=5600)
    report = {
        "coverage": "analytical; isolated services and partial system lower bound",
        "unmodeled": ["SRAM/DRAM access timing", "backpressure", "data layout transforms", "physical costs"],
        "configuration": {"clock": asdict(clock), "work": asdict(work),
                          "mac": asdict(mac.params), "dma": asdict(dma), "buffer": asdict(buffer)},
        "logical_macs": work.mac_count,
        "logical_input_bytes": work.input_bytes,
        "logical_output_bytes": work.output_bytes,
        "reserved_buffer_bytes": buffer.capacity_bytes,
        "isolated_stage_cycles": [load.completion_cycles, compute.completion_cycles, store.completion_cycles],
        "actions": [asdict(action) for action in actions],
        "resource_budgets": [asdict(budget) for budget in budgets],
        "time_bounds": asdict(estimate_time_bounds(actions, budgets)),
        "standalone_dram": {"params": asdict(dram), "capacity_bytes": dram.capacity_bytes,
                            "peak_bandwidth_bytes_per_s": dram.peak_bandwidth_bytes_per_s},
    }
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
