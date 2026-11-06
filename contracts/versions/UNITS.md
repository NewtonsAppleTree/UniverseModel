# versions：规范化与内容身份

json_codec 支持 dataclass、字符串 key 的 mapping、tuple/list 与有限 JSON 标量。`canonical_json` 采用排序 key、紧凑分隔、UTF-8；`content_hash=SHA256(canonical bytes)`。规范化 v1 保留 int/float 的表示区别，不等同于跨语言数值标准。

最关心 key 唯一、非有限数拒绝、版本解释与输入快照完整性。`parse_json` 拒绝重复 key、NaN/Infinity 与溢出数。使用顺序：解析 → producer 类型/语义校验 → canonical snapshot/hash；哈希不能代替语义校验。验证见[工程测试](../../tests/integration/test_framework.py)。无物理参数/状态。

<!-- model-fields:start -->

### [json_codec.py](json_codec.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `canonical_json(value: object)` | Canonical JSON v1: sorted string keys, compact separators, UTF-8, finite numbers; 1 differs from 1.0. |
| `content_hash(value: object)` | Content identity H=SHA256(canonical_json(value).encode('utf-8')); excludes filename and wall time. |
| `parse_json(source: str)` | Decode strict JSON; round-trip validation also rejects numeric overflow such as 1e999. |

<!-- model-fields:end -->
