# tests：编译阶段独立验证

Attention新增3项计划/区域/容量测试，见[test_attention_mapping.py](test_attention_mapping.py)；独立数值参考的3项跨模块验证放在[集成测试](../../tests/integration/test_attention_mapping_experiment.py)，避免compiler反向依赖workloads。

使用标准库 unittest、contracts 和 compiler，不跨边界导入 workloads/chipmodel。无独立硬件 Unit、物理参数或运行状态；手算矩形乘法、缓冲容量和请求字节提供数值证据，缺失/重复/非法 ROI 与提前释放提供反例。最大规模参数只限制测试/宿主材料化。

运行 `python -m unittest discover -s compiler/tests -p "test_*.py" -v`。跨模块独立参考、目标服务参数、保存回读由[集成测试](../../tests/integration/test_linear_experiment.py)覆盖。测试通过不声称事件时序或物理成本已校准。

训练测试 [test_training.py](test_training.py) 增加单层手算、ReLU 零/负输入、SGD 旧状态/异源梯度拒绝、连续两个 step、独立生命周期反例、双容量边界与反向收缩轴；仍不导入 workloads/chipmodel。

<!-- model-fields:start -->

### [test_attention_mapping.py](test_attention_mapping.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AttentionMappingTests` | Coverage and data movement are checked independently of the builder's own validation. |
| `AttentionMappingTests.setUp(self)` | Small causal GQA task gives hand-countable full-key loads and real query tails. |
| `AttentionMappingTests.test_hand_counts_and_capacity(self)` | Fusion removes four intermediate payload transfers; larger query blocks reduce repeated KV loads. |
| `AttentionMappingTests.test_output_regions_and_layout(self)` | Explicitly enumerate output elements; every row/head is written exactly once, including non-divisible tails. |
| `AttentionMappingTests.test_plan_and_budget_guards(self)` | Reject forged ownership, omitted/repeated rows, stale task hashes and host allocation/work limits. |

### [test_linear_mapping.py](test_linear_mapping.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinearMappingTests` | Verify compiler semantics without importing workloads or hardware across its dependency boundary. |
| `LinearMappingTests.test_rectangular_tails_and_oversized_tiles(self)` | Tail tiles and oversized tiles execute a rectangular hand-computed GEMM under both policies. |
| `LinearMappingTests.test_scratch_capacity_boundary(self)` | Three reserved arenas have nonoverlapping byte intervals and reject capacity one byte too small. |
| `LinearMappingTests.test_traffic_counts_and_row_requests(self)` | Hand-derived payload totals include each output once and two extra C transfers per K boundary. |
| `LinearMappingTests.test_no_reduction_split_has_no_spill_cost(self)` | Without a K split both policies have identical traffic, including tail dimensions. |
| `LinearMappingTests.test_corrupted_plan_rejected(self)` | Independent coverage validator rejects omissions, duplicates, overlaps, misalignment and identity changes. |
| `LinearMappingTests.test_premature_c_release_rejected(self)` | A single resident C buffer cannot switch output tiles before the prior reduction finishes. |
| `LinearMappingTests.test_legal_output_group_reordering(self)` | Legal complete output groups may be reordered, so validation is independent of producer enumeration. |
| `LinearMappingTests.test_float_rounding_and_overflow(self)` | Native binary64 operations preserve K order, expose cancellation, and reject overflowing partial sums. |
| `LinearMappingTests.test_materialization_limits(self)` | Work, plan and request materialization have separate host safety bounds. |

### [test_training.py](test_training.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TrainingCompilerTests` | Verify explicit training lowering without importing workload references or hardware across compiler boundaries. |
| `TrainingCompilerTests.test_single_layer_execution(self)` | Rectangular Linear hand values remain correct with split reductions and preserve caller state. |
| `TrainingCompilerTests.test_relu_mask_and_zero_boundary(self)` | ReLU backward uses the saved activation, including derivative zero for both zero and negative preactivation. |
| `TrainingCompilerTests.test_sgd_state_provenance_and_repeated_steps(self)` | Parameter version and content hash both reject stale/foreign gradients; new steps use the updated weights. |
| `TrainingCompilerTests.test_hand_lifetime_and_capacity(self)` | Inclusive lifetime accounting keeps input/output simultaneously allocated and honors retained observations. |
| `TrainingCompilerTests.test_lifetime_counterexamples(self)` | Missing production, reads from the future and overwriting old input allocations are all invalid. |
| `TrainingCompilerTests.test_lowering_axes_and_update_order(self)` | Backward contraction axes differ from forward; all updates follow all backward contractions and transposes. |
| `TrainingCompilerTests.test_independent_capacity_and_work_limits(self)` | Scratch and backing capacity are independent budgets, and the full-step work limit is enforced before lowering. |
| `TrainingCompilerTests.test_numerical_overflow(self)` | Nonfinite loss or update is rejected rather than silently producing an apparently successful training state. |

<!-- model-fields:end -->
