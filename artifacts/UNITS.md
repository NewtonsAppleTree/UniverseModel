# artifacts：产物一致性

本模块仅依赖 contracts，不计算模型时间/成本。当前[local storage](storage/UNITS.md)保存与读取小运行 bundle，结构/版本/内容验证通过才返回新视图。大数据引用、轨迹与后端扩展见[设计](docs/design.md)。

关键关系是内容哈希、输入身份、run 状态与最终提交标记一致；已有目录拒绝覆盖。使用：producer 记录 → 写运行内容 → 最后提交 manifest → 校验读取；无独立物理计量。验证见[工程测试](../tests/integration/test_framework.py)。

<!-- model-fields:start -->



<!-- model-fields:end -->
