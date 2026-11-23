"""CIM 的串行 phase 台架：有限样本/码值容量、资源账本与局部分析时间。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import ClockDomain, PipelineParams, ceil_div, count, estimate_pipeline, finite_fraction, identifier, typed_tuple
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, TimeBounds, estimate_time_bounds
from chipmodel.composition.graph import ResourceNode, validate_model_selection
from chipmodel.composition.transfer import ResourceContribution, resource_contributions
from chipmodel.compute.cim.matvec import CimInput, CimNumericParams, CimNumericResult, evaluate_cim
from chipmodel.compute.cim.periphery.dac import SampleHoldLimits


# 一个物理阶段的服务参数及资源身份；时序是假设或特征化输入，不由数值公式推导。
@dataclass(frozen=True, slots=True, kw_only=True)
class CimStage:
    resource_id: str  # DAC、TIA 或数字处理流水线的唯一物理 ID。
    pipeline: PipelineParams  # P/L/II [lane, cycle]；item 由阶段的工作单位定义。
    clock: ClockDomain  # 本阶段时钟 [Hz]，不同域先换成 second。

    # 服务身份、流水线和时钟均显式且冻结。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        if not isinstance(self.pipeline, PipelineParams) or not isinstance(self.clock, ClockDomain):
            raise TypeError("CIM stage requires PipelineParams and ClockDomain")


# 输入/权重已驻留，bit/slice phases 串行；DAC广播到当前切片的差分两阵列。
@dataclass(frozen=True, slots=True, kw_only=True)
class CimTile:
    numeric: CimNumericParams  # 编码、电导与 DAC/TIA/ADC 数值参数。
    nodes: tuple[ResourceNode, ...]  # 无环归属图；摘要/内部资源互斥。
    array_resource_ids: tuple[str, ...]  # slice-major、positive/negative 的独立阵列身份。
    array_pipeline: PipelineParams  # 每个阵列一次完整读取的 L/II [cycle]；lane_count 必须为1。
    array_clock: ClockDomain  # 各切片阵列共用的固定时钟 [Hz]。
    dac: CimStage  # 每行一个持续驱动DAC，lane_count≥R；向当前差分对理想广播。
    tia: CimStage  # 每 item 形成一个可保持的标量电压，模拟差分含在此阶段。
    adc_resource_id: str  # 所有列/支路/切片共享的 ADC bank ID。
    adc_clock: ClockDomain  # ADC 与 MUX 控制的时钟 [Hz]。
    mux_settle_cycles: int  # 每 phase 首批 setup；相邻发起至少此间隔 [cycle]。
    adc_inflight_per_lane: int  # 每 lane 内部独立采样/转换槽 [sample/lane]。
    hold_resource_id: str  # TIA后标量sample/hold的唯一资源身份。
    hold: SampleHoldLimits  # 外部样本槽数与从TIA完成到ADC接收的有效期。
    digital: CimStage  # 每 item 完成一次重建、差分或融合requantize/shift-add。
    code_buffer_slots: int  # 数字阶段所属的ADC码值暂存容量 [code]；每phase需容纳全部转换码。
    accumulator_slots: int  # 数字阶段所属的持久输出累加槽 [integer]；至少C个。
    profile_source: str  # L/II、MUX、保持及数字原语假设的来源/版本。

    # 明确静态容量和唯一所有权；不由ADC lane数推断sample/hold或数字寄存器容量。
    def __post_init__(self) -> None:
        for name, kind in (("numeric", CimNumericParams), ("array_pipeline", PipelineParams),
                           ("array_clock", ClockDomain), ("dac", CimStage), ("tia", CimStage),
                           ("adc_clock", ClockDomain), ("hold", SampleHoldLimits), ("digital", CimStage)):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")
        for name in ("adc_resource_id", "hold_resource_id", "profile_source"):
            identifier(name, getattr(self, name))
        for name in ("adc_inflight_per_lane", "code_buffer_slots", "accumulator_slots"):
            count(name, getattr(self, name))
        count("mux_settle_cycles", self.mux_settle_cycles, 0)
        object.__setattr__(self, "nodes", typed_tuple("nodes", self.nodes, ResourceNode))
        object.__setattr__(self, "array_resource_ids", typed_tuple("array_resource_ids", self.array_resource_ids, str))
        e = self.numeric.encoding
        arrays = ceil_div(e.magnitude_bits, e.cell_bits) * (2 if e.differential else 1)
        if len(self.array_resource_ids) != arrays or self.array_pipeline.lane_count != 1:
            raise ValueError("CIM needs one single-lane service resource per physical encoded array")
        if self.dac.pipeline.lane_count < self.numeric.array.rows:
            raise ValueError("CIM requires one persistent DAC lane per row; multiplexed row holds are not modeled")
        selected = (*self.array_resource_ids, self.dac.resource_id, self.tia.resource_id,
                    self.adc_resource_id, self.hold_resource_id, self.digital.resource_id)
        validate_model_selection(self.nodes, selected)
        index = {n.instance_id: n for n in self.nodes}
        if any(index[key].parent_id is None for key in selected):
            raise ValueError("each CIM resource requires an explicit owner")


# 结构工作量在模拟/数字求差之间分项，逻辑MAC不等于转换或cell动作。
@dataclass(frozen=True, slots=True)
class CimActionCounts:
    logical_macs: int  # R*C [MAC]，一次稠密逻辑MatVec。
    physical_arrays: int  # ceil(Bw/Bcell)*branches [array]。
    physical_weight_bits: int  # 实际阵列cell数*cell_bits [bit]，含尾slice未用位。
    phases: int  # input_bits*weight_slices [phase]。
    dac_updates: int  # R*phases [DAC update]，当前差分两支路共享行电压。
    array_reads: int  # physical_arrays*input_bits [array read]。
    cell_evaluations: int  # R*C*array_reads [cell evaluation]，包括零输入相位。
    tia_samples: int  # C*phases*converted_branches [sample]。
    adc_conversions: int  # 与实际readout数相等 [conversion]。
    digital_reconstructions: int  # 每ADC码重建一次电压 [operation]。
    digital_subtractions: int  # 仅ADC后差分为C*phases [operation]。
    shift_adds: int  # 每列/phase一次融合requantize和移位累加 [operation]。
    digital_operations: int  # reconstructions+subtractions+shift_adds [operation]。


# 指定串行策略下的分析窗口；没有事件回调或器件可见性主张。
@dataclass(frozen=True, slots=True)
class CimStageWindow:
    action_id: str  # 与可组合ActionEstimate一致的身份。
    resource_id: str  # 该阶段物理资源。
    work_items: int  # 本窗口实际工作量 [item]。
    first_issue_s: float  # 满足依赖和资源II后第一次发起 [s]。
    completion_s: float  # 本窗口最后一项完成 [s]。


# 每个样本的捕获、接收与转换完成，外部hold在ADC接收时释放。
@dataclass(frozen=True, slots=True)
class CimSampleTiming:
    sample_id: str  # 指向数值链中相同的CimReadout。
    adc_lane: int  # 确定性按sample_index mod lanes分派的lane索引。
    captured_s: float  # TIA对应item完成并进入外部hold的时刻 [s]。
    adc_start_s: float  # ADC内部采样接收、外部hold释放时刻 [s]。
    adc_complete_s: float  # ADC码值就绪时刻 [s]。
    hold_age_s: float  # adc_start_s-captured_s [s]；与保持上限比较。


# 本地台架输出将功能、资源下界与显式策略估算分开；编程和物理成本保持未知。
@dataclass(frozen=True, slots=True)
class CimAnalysis:
    numeric: CimNumericResult  # 完整数值轨迹、程序初态及功能输出。
    counts: CimActionCounts  # 编码与外围的实际动作账本。
    actions: tuple[ActionEstimate, ...]  # 串行phase策略的依赖/工作，可与外部显式动作组合。
    budgets: tuple[ResourceBudget, ...]  # 唯一资源供给包络；hold仅作容量/年龄约束。
    contributions: tuple[ResourceContribution, ...]  # 各资源累计工作与包络贡献。
    resource_service_bounds: tuple[tuple[str, float], ...]  # 忽略依赖的各资源全批隔离服务 [s]。
    resource_lower_bound_s: float  # max(resource_service_bounds) [s]；不等于端到端运行时间。
    bottlenecks: tuple[str, ...]  # 达到最大资源服务下界的物理资源ID。
    policy_bounds: TimeBounds  # 只对所声明串行phase策略的依赖/资源界。
    serial_policy_time_s: float  # 串行phase、阶段barrier、II与MUX下的分析完成时间 [s]。
    windows: tuple[CimStageWindow, ...]  # 本地策略的阶段服务窗口。
    samples: tuple[CimSampleTiming, ...]  # 全部样本的身份、时间与保持年龄。
    peak_hold_samples: int  # 全TIA完成后、ADC开始前的样本峰值 [sample]。
    peak_code_slots: int  # ADC全部完成后、数字阶段前的码值峰值 [code]。
    required_adc_inflight_per_lane: int  # min(groups,ceil(L/II_effective)) [sample/lane]。
    energy_j: None  # 读取/外围/漏电总能耗 [J]，未特征化。
    programming_time_s: None  # 权重编程耗时 [s]，已驻留边界不等于免费编程。
    programming_energy_j: None  # 权重编程能耗 [J]，未知。
    unknown_reasons: tuple[str, ...]  # 来源缺口与未覆盖服务，不能填为零。


# 同步lane在first+g*II发起；用精确时间计算跨phase资源可用性，避免L<II时过早重用。
def _serve(resource_id: str, pipeline: PipelineParams, clock: ClockDomain, items: int,
           ready: Fraction, available: dict[str, Fraction]) -> tuple[Fraction, Fraction]:
    groups = ceil_div(items, pipeline.lane_count)
    first = max(ready, available.get(resource_id, Fraction(0)))
    period = 1 / Fraction(clock.frequency_hz)
    finish = first + ((groups - 1) * pipeline.initiation_interval_cycles + pipeline.latency_cycles) * period
    available[resource_id] = first + groups * pipeline.initiation_interval_cycles * period
    return first, finish


# 建立有限phase台架：DAC→两支阵列并行→TIA全批→ADC全批→数字更新；phase之间全排空。
def analyze_cim(tile: CimTile, inputs: CimInput, *, max_cell_evaluations: int = 1_000_000) -> CimAnalysis:
    if not isinstance(tile, CimTile) or not isinstance(inputs, CimInput):
        raise TypeError("analyze_cim needs CimTile and CimInput")
    p, encoding = tile.numeric, tile.numeric.encoding
    branches = 2 if encoding.differential else 1
    digital_difference = encoding.differential and not encoding.subtract_before_adc
    converted = 2 if digital_difference else 1
    samples_per_phase = p.array.columns * converted
    if samples_per_phase > tile.code_buffer_slots or p.array.columns > tile.accumulator_slots:
        raise ValueError("CIM code buffer or output accumulator capacity exceeded")
    tile.hold.validate(sample_count=samples_per_phase, age_s=0)
    adc_pipeline = PipelineParams(lane_count=p.adc.lane_count, latency_cycles=p.adc.conversion_cycles,
                                  initiation_interval_cycles=max(p.adc.initiation_interval_cycles, tile.mux_settle_cycles))
    inflight = min(ceil_div(samples_per_phase, p.adc.lane_count),
                   ceil_div(p.adc.conversion_cycles, adc_pipeline.initiation_interval_cycles))
    if inflight > tile.adc_inflight_per_lane:
        raise ValueError("ADC internal inflight sample capacity exceeded")
    numeric = evaluate_cim(p, inputs, adc_frequency_hz=tile.adc_clock.frequency_hz,
                           max_cell_evaluations=max_cell_evaluations)
    phase_count = len(numeric.phases)
    shift_adds = p.array.columns * phase_count
    adc_work = sum(len(phase.readouts) for phase in numeric.phases)
    subtracts = shift_adds if digital_difference else 0
    counts = CimActionCounts(numeric.work.logical_macs, numeric.work.physical_arrays, numeric.work.physical_weight_bits,
                             phase_count, p.array.rows * phase_count, len(tile.array_resource_ids) * encoding.input_bits,
                             numeric.work.cell_evaluations, adc_work, adc_work, adc_work, subtracts, shift_adds,
                             adc_work + subtracts + shift_adds)
    specs = [(tile.dac.resource_id, tile.dac.pipeline, tile.dac.clock, "DAC-update", counts.dac_updates),
             *((key, tile.array_pipeline, tile.array_clock, "array-read", encoding.input_bits) for key in tile.array_resource_ids),
             (tile.tia.resource_id, tile.tia.pipeline, tile.tia.clock, "sample", adc_work),
             (tile.adc_resource_id, adc_pipeline, tile.adc_clock, "conversion", adc_work),
             (tile.digital.resource_id, tile.digital.pipeline, tile.digital.clock, "operation", counts.digital_operations)]
    budgets = tuple(ResourceBudget(resource_id=key, work_unit=unit, initial_credit=pipe.lane_count,
                                   rate_per_s=finite_fraction("CIM resource rate", Fraction(pipe.lane_count)
                                                              * Fraction(clock.frequency_hz) / pipe.initiation_interval_cycles))
                    for key, pipe, clock, unit, _ in specs)
    actions, windows, sample_times = [], [], []
    available = {}
    previous, ready = (), Fraction(0)
    for phase in numeric.phases:
        first, finish = _serve(tile.dac.resource_id, tile.dac.pipeline, tile.dac.clock, p.array.rows, ready, available)
        dac_id = phase.phase_id + "/dac"
        actions.append(ActionEstimate(action_id=dac_id, latency_s=estimate_pipeline(tile.dac.pipeline, tile.dac.clock, p.array.rows).completion_time_s,
                                      dependencies=previous, demands=(ResourceDemand(resource_id=tile.dac.resource_id,
                                      work_unit="DAC-update", amount=p.array.rows),)))
        windows.append(CimStageWindow(dac_id, tile.dac.resource_id, p.array.rows,
                                      finite_fraction("DAC first", first), finite_fraction("DAC finish", finish)))
        array_ids, array_finishes = [], []
        for resource_id in tile.array_resource_ids[phase.weight_slice * branches:(phase.weight_slice + 1) * branches]:
            action_id = phase.phase_id + "/array/" + resource_id
            start, end = _serve(resource_id, tile.array_pipeline, tile.array_clock, 1, finish, available)
            array_ids.append(action_id)
            array_finishes.append(end)
            actions.append(ActionEstimate(action_id=action_id, latency_s=tile.array_clock.seconds(tile.array_pipeline.latency_cycles),
                                          dependencies=(dac_id,), demands=(ResourceDemand(resource_id=resource_id,
                                          work_unit="array-read", amount=1),)))
            windows.append(CimStageWindow(action_id, resource_id, 1, finite_fraction("array first", start), finite_fraction("array finish", end)))
        s = len(phase.readouts)
        tia_first, tia_end = _serve(tile.tia.resource_id, tile.tia.pipeline, tile.tia.clock, s, max(array_finishes), available)
        tia_id = phase.phase_id + "/tia"
        actions.append(ActionEstimate(action_id=tia_id, latency_s=estimate_pipeline(tile.tia.pipeline, tile.tia.clock, s).completion_time_s,
                                      dependencies=tuple(array_ids), demands=(ResourceDemand(resource_id=tile.tia.resource_id, work_unit="sample", amount=s),)))
        windows.append(CimStageWindow(tia_id, tile.tia.resource_id, s, finite_fraction("TIA first", tia_first), finite_fraction("TIA finish", tia_end)))
        mux_s = Fraction(tile.mux_settle_cycles) / Fraction(tile.adc_clock.frequency_hz)
        adc_first, adc_end = _serve(tile.adc_resource_id, adc_pipeline, tile.adc_clock, s, tia_end + mux_s, available)
        adc_id = phase.phase_id + "/adc"
        adc_latency = estimate_pipeline(adc_pipeline, tile.adc_clock, s).completion_time_s
        actions.append(ActionEstimate(action_id=adc_id, latency_s=finite_fraction("ADC+MUX latency", Fraction(adc_latency) + mux_s),
                                      dependencies=(tia_id,), demands=(ResourceDemand(resource_id=tile.adc_resource_id, work_unit="conversion", amount=s),)))
        windows.append(CimStageWindow(adc_id, tile.adc_resource_id, s, finite_fraction("ADC first", adc_first), finite_fraction("ADC finish", adc_end)))
        for index, readout in enumerate(phase.readouts):
            capture = tia_first + Fraction(tile.tia.pipeline.latency_cycles + (index // tile.tia.pipeline.lane_count)
                                           * tile.tia.pipeline.initiation_interval_cycles) / Fraction(tile.tia.clock.frequency_hz)
            start = adc_first + Fraction((index // adc_pipeline.lane_count) * adc_pipeline.initiation_interval_cycles) / Fraction(tile.adc_clock.frequency_hz)
            end = start + Fraction(adc_pipeline.latency_cycles) / Fraction(tile.adc_clock.frequency_hz)
            age = start - capture
            if age > Fraction(tile.hold.valid_duration_s):
                raise ValueError(f"sample/hold age exceeds valid duration: {readout.sample_id}")
            sample_times.append(CimSampleTiming(readout.sample_id, index % adc_pipeline.lane_count,
                finite_fraction("capture", capture), finite_fraction("ADC start", start), finite_fraction("ADC completion", end),
                finite_fraction("hold age", age)))
        operations = s + p.array.columns * (1 + digital_difference)
        start, ready = _serve(tile.digital.resource_id, tile.digital.pipeline, tile.digital.clock, operations, adc_end, available)
        digital_id = phase.phase_id + "/digital"
        actions.append(ActionEstimate(action_id=digital_id, latency_s=estimate_pipeline(tile.digital.pipeline, tile.digital.clock, operations).completion_time_s,
                                      dependencies=(adc_id,), demands=(ResourceDemand(resource_id=tile.digital.resource_id, work_unit="operation", amount=operations),)))
        windows.append(CimStageWindow(digital_id, tile.digital.resource_id, operations, finite_fraction("digital first", start), finite_fraction("digital finish", ready)))
        previous = (digital_id,)
    actions = tuple(actions)
    bounds = estimate_time_bounds(actions, budgets)
    service_bounds = tuple((key, estimate_pipeline(pipe, clock, items).completion_time_s) for key, pipe, clock, _, items in specs)
    lower = max(value for _, value in service_bounds)
    if adc_work != numeric.work.adc_conversions:
        raise ValueError("numeric readouts and declared encoding work disagree")
    return CimAnalysis(numeric, counts, actions, budgets, resource_contributions(actions, budgets), service_bounds, lower,
                       tuple(key for key, value in service_bounds if value == lower), bounds, finite_fraction("serial policy time", ready),
                       tuple(windows), tuple(sample_times), samples_per_phase, samples_per_phase, inflight, None, None, None,
                       ("Weights and digital inputs are preloaded; programming and input/output movement are not modeled",
                        "No calibrated read, DAC/TIA/ADC, digital, leakage or sample/hold energy profile",
                        "Ideal DAC fanout and stable array currents during TIA scan; no wire/load/noise/retention characterization",
                        "Local analytical service policy only; no event engine, device timing or physical feasibility claim"))
