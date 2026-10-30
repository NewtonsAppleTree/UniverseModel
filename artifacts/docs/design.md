# artifacts：产物、清单与来源

## 核心与边界

最重要的是结果能追溯到完整输入和执行依据。artifacts 只依赖 contracts，负责 codecs、storage、manifest 和 provenance；不计算硬件性能、不决定参考结果是否通过。

输入是各模块生成的版本化对象、文件/内容引用和状态变更；输出是可校验产物引用与运行清单。语义由生产模块负责，序列化和保存一致性由本模块负责。具体规范见[实验产物](../../docs/interfaces/artifacts.md)。

## 参数与工作流

关键参数为 storage backend、hash/canonicalization version、compression、保留策略、trace policy 和大数据路径映射。运行准备阶段冻结输入；执行期间追加诊断；完成时核验必需产物再写终态 manifest。

单文件临时写入/替换与完成清单构成提交协议，不假定跨文件或跨对象存储事务。失败和取消也是有效记录类型。内容去重不能造成不同 run 互相修改；历史核心产物保持不可变。

## 重用与优化

Replay 需要代码/模型/输入完整，Reanalysis 需要原始输出与计数器，Resume 还需要完整状态检查点。三者分开声明，不以“有 JSON”承诺可恢复执行。

优化存储优先采用内容寻址、压缩、分层保留和索引；减少记录前先判断哪些结论将无法审计。run_id 代表尝试，hash 代表内容，时间戳只用于观察，不替代身份。

## 验证

重点是中断写入、缺失 blob、哈希不符、不支持的 schema、dirty 源码遗漏和保留策略删除。验证可恢复的来源链，不仅检查文件存在。清单不能把 incomplete 运行标成 succeeded；更正历史解释产生新分析版本。

## 复现输入补充

运行身份还包含初始化方式/状态引用、ROI、到达过程、随机子流、成本覆盖清单及验证范围。执行成功、功能未验证与部分成本估计可以同时存在，必须分别保存；参考[实验有效性](../../docs/methods/experiment_validity.md)和[模型组合](../../docs/architecture/model_composition.md)。
