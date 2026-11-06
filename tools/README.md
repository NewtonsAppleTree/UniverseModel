# 开发工具

`python tools/check_structure.py` 使用 Python 标准库检查：模块目录/设计文档、允许依赖的无环性、本地 Markdown 文件链接、结构示例的身份/包含/端口/视图/堆叠引用，以及维护中的全部 DOCX 的来源哈希。

失败返回非零退出码并列出位置；成功仅代表工程结构一致。该工具不验证业务实现、完整 HardwareSpec、数学公式、外部链接或 DOCX 视觉排版。CI 执行同一命令。

Word 构建工具放在 docs/tools，避免与未来硬件/编译模型执行入口混淆。

`python tools/check_model_rules.py` 检查 chipmodel 每个 class/def 前的说明、字段行尾注释以及每个模块目录的 UNITS.md。字段/公开接口表由 AST 与源码注释生成；默认核对同步，`--write-docs` 只更新标记内生成区。该检查不证明术语、公式或物理假设正确，仍需模型测试和审阅。
