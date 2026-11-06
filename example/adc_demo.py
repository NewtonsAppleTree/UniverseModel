"""仓库根目录运行：python -m example.adc_demo；只使用 ADC，无全系统前置依赖。"""

from dataclasses import asdict, replace
import json

from chipmodel.compute.cim.periphery.adc import AdcParams, IdealAdc


def main() -> None:
    # 示例假设；L/II 与 1 GHz 未经电路校准，不代表某工艺下的 ADC 指标。
    params = AdcParams(
        resolution_bits=10,  # Nominal resolution [bit]。
        lane_count=4,  # 并行 ADC 数 [lane]。
        conversion_cycles=2,  # 单次转换延迟 [cycle]。
        initiation_interval_cycles=2,  # 每 lane 发起间隔 [cycle]。
        input_min_v=0.0,  # 输入下限 [V]。
        input_max_v=1.0,  # 输入上限 [V]。
    )
    adc = IdealAdc(params=params, frequency_hz=1.0e9)
    samples_v = (-0.1, 0.0, 0.25, 0.5, 0.999, 1.0, 1.1)  # 已采样电压 [V]。
    results = adc.convert_many(samples_v)
    wider = IdealAdc(params=replace(params, lane_count=8), frequency_hz=adc.frequency_hz)
    report = {
        "model_id": adc.model_id,
        "coverage": "ideal quantization + uncontended fixed-clock estimate",
        "params": asdict(adc.params),
        "frequency_hz": adc.frequency_hz,
        "derived": asdict(adc.derived),
        "input_voltages_v": samples_v,
        "samples": [asdict(result) for result in results],
        "batch_16_samples_4_lanes": asdict(adc.estimate_batch(16)),
        "batch_16_samples_8_lanes": asdict(wider.estimate_batch(16)),
    }
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
