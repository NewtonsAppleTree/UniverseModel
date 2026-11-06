# storage：本地小数据运行 bundle

`write_run` 创建新目录，写 `run.json`，最后写 `manifest.json`；后者记录 run_id/status/identity_hash、字节数与 SHA-256。`read_run` 核对提交标记、字节/哈希/版本/身份，并重做 RunRecord 语义校验。

最关心覆盖保护、完整性、failed 记录与不完整目录。持久化不是模拟状态 checkpoint；当前不承诺断电持久性、多文件事务、blob/对象存储或断点恢复。无物理公式，校验关系为 `H=SHA256(actual file bytes)`；测试见[工程测试](../../tests/integration/test_framework.py)。

<!-- model-fields:start -->

### [local.py](local.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `write_run(record: RunRecord, directory: str \| Path)` | Create a new directory, write one self-contained run, then commit its byte hash; existing runs are immutable. |
| `read_run(directory: str \| Path)` | Verify committed bytes and experiment identity before returning a fresh view; incomplete bundles fail. |

<!-- model-fields:end -->
