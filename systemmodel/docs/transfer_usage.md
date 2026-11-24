# S3：PCIe/DMA直传、整缓冲中转与共享工作

本包按[项目使命](../../PROJECT_MISSION.md)为AI权重、激活、KV等搬运方案提供静态研究基础：**研究什么**是相同数据/资源预算下搬运路径和staging的额外工作；**怎样建模**是显式本地源DMA、posted-write TLP、唯一共享资源及整copy依赖；**如何证明**是精确字节账本、手算/独立分包参考、同预算对照和不可变实验回读。未将模型声明或运行成功等同于实际数据传输和任务质量。

## 独立入口与实验

```python
from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.system_transfer import TransferStudy
from systemmodel.io.dma.analysis import analyze_transfers
from systemmodel.io.pcie.model import packetize_write

study = load_config(TransferStudy, 'config/experiments/system_transfer.json')
case = next(c for c in study.cases if c.name == 'direct')
traffic = packetize_write(study.system.profile, 4096, 512)
assert traffic.frame_bytes == 560
result = analyze_transfers(study.system, case.batch)
assert result.legs[0].dma.completion_cycles == 124
```

上述加载只是方便取fixture；PcieProfile/PcieService、DmaSystem和CopyBatch可直接构造，不依赖configuration/evaluation。参数见[PCIe UNITS](../io/pcie/UNITS.md)和[DMA UNITS](../io/dma/UNITS.md)。输入保留S0/S2 schema，system身份同时绑定memory、channel、format、clock与来源。

```powershell
python -m example.system_transfer_demo --source-revision <revision> --output .build/my-system-transfer
python -m example.system_transfer_demo --read .build/my-system-transfer
python -m unittest discover -s tests/systemmodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_system_transfer_experiment.py" -v
```

输出目录须不存在。每例完整保存硬件、候选名单、batch、source_revision、假设、实际结果或失败；CLI对任何意外结果返回非零。回读只用保存的实际路径重新核对解地址、帧/DMA/内存工作、依赖和下界，不调用producer、不新寻路，不重新证明失败诊断或最少跳数。记录完整性是可复现校验，不是外部真实性认证。

## 固定硬件与可比范围

两GPU与host均有独立内存和串行DMA，显式fabric转发及一份1e9 payload B/s root_bus。线路为独立有向4 lane×8e9 NRZ transfer/s，128/130编码；MPS=256 B、TLP合计overhead=24 B。每DMA为1 GHz、32 B/cycle、256 B/burst、100 cycle启动、4 cycle/burst控制。所有参数来源`manual:pcie-dma-fixture/v1`；这是人工可检验台架，不是PCIe设备校准或完整标准实现。

每物理池8192 B、分配粒度64 B；source、两个target和host staging各声明1024 B副本。direct与staged使用**相同MemoryPlan和硬件预算**，都比较gpu0.source→gpu1.target的512有效B；direct预留的host空间未被实际搬运使用。容量节省不是这对固定预算案例的主张。其他大小/方向/多copy案例属于敏感性与边界控制，不能混为同任务性能提升。

| 成功案例 | 独立可检验结果 |
| --- | --- |
| direct / explicit_route | 512有效B、124 DMA cycle、2 TLP/560 frame B；经过两wire合计1120 frame B；已知服务界512 ns |
| staged | source→host→target，两完整leg；host写512 B再读512 B；root_bus累计1024 B；两wire×两leg共2240 frame B；界1024 ns |
| reverse_staged | gpu1→host→gpu0可行；反向直传没有显式forwarding，不能由它推断 |
| small_1B | 1有效B、4字段B+24协议B；DMA=105 cycle，启动主导，界105 ns |
| tail_513B | target地址4099；3 TLP、516字段B、72协议B；实际copy513 B，界513 ns |
| two_shared | 两个独立512 B任务，目的不相交；critical512 ns，共享必要工作1024 ns；同一root容量只定义一份 |

七个失败案例：staging容量不足、链内物理字节不连续、独立链写冲突、把远端源当本地pull、无反向直传路径、过期phase、目标无write权限。独立测试另覆盖别名中转、未建模wire、重复/摘要资源、错误ceiling/frame格式、4 KiB/64 bit边界和回读篡改。

## 下界解释与后续边界

DMA复用已有控制/数据工作公式；TLP header/padding在frame demand计一次，编码只折算线路capacity。每个leg取已知必要资源时间的最大值，不把不同hop的整包时间相加；整copy依赖才串行累加。独立链可并发，但共享资源工作聚合为一份必要时间界。已知界随启动、MPS、线路速率、共享容量和依赖变化，不是已经实现的排队/流水调度完成时间。

当前只支持conventional非FLIT、NRZ、posted write。本地源需显式read_backing绑定且domain匹配；不覆盖远端read request/completion、MRRS、FLIT/PAM4、DLLP/ACK/flow-control credit、replay、传播、仲裁或设备详细协议状态。整缓冲staging不作分块流水；所有预约在同一逻辑phase有效，phase不是cycle/second。数据内容、cache/coherence、真实访存、host launch、接受/消费/可见性事件与完整能耗未知。

输出`known_service_lower_bound`为lower_bound，而`target_execution_time`和`target_energy`仍为None并带原因。160组固定种子的独立DWORD分包参考、手算、守恒与参数敏感性提供正确性证据；未测AI质量或真实PCIe性能。下一包S4围绕CXL能力、分层驻留与迁移路径继续组合；仅在需要真实重叠/队列证据时接入runtime/simulator。
