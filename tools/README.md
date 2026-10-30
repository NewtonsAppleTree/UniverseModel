# 开发工具

`python tools/check_structure.py` 使用 Python 标准库检查：模块目录/设计文档、允许依赖的无环性、本地 Markdown 文件链接、结构示例的身份/包含/端口/视图/堆叠引用，以及三份 DOCX 的来源哈希。

失败返回非零退出码并列出位置；成功仅代表工程结构一致。该工具不验证业务实现、完整 HardwareSpec、数学公式、外部链接或 DOCX 视觉排版。CI 执行同一命令。

Word 构建工具放在 docs/tools，避免与未来硬件/编译模型执行入口混淆。
