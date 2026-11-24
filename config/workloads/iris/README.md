# Iris 原始数据来源

本目录按 UCI 的 CC BY 4.0 声明保留原始文件字节，供有限真实分类任务的协议和数值实验使用。数据作者为 R. A. Fisher，原始资料为1936年；UCI记录捐赠者Michael Marshall，1988年7月。引用：Fisher, R. A., *Iris*, UCI Machine Learning Repository，DOI [10.24432/C56C76](https://doi.org/10.24432/C56C76)。

- 原始数据：[iris.data](iris.data)，来源 https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data 。
- 原说明：[iris.names](iris.names)，包含作者、捐赠者、特征单位及原数据差异说明。
- UCI元数据：[iris-metadata.json](iris-metadata.json)，来源 https://archive.ics.uci.edu/api/dataset?id=53 。
- 下载与原始字节身份：[provenance.json](provenance.json)。取得日期为2026-11-23，文件未改动。

UCI[数据页面](https://archive.ics.uci.edu/dataset/53/iris)明确声明“Creative Commons Attribution 4.0 International (CC BY 4.0)”。许可全文：https://creativecommons.org/licenses/by/4.0/legalcode 。原页面快照保存在本轮本地证据references/中，其SHA256在provenance.json记录；这里保留原始来源及署名，不另行声称拥有数据。

数据为150株植物、4项cm测量、3类各50例。iris.names说明第35/38行与Fisher文章有差异；本实现保留UCI原始值，不静默替换为其他库的修正副本。划分/标准化/派生QKV只在运行时产生，并随实验保存。

这是历史小型分类数据，用于检验真实观测上的划分、选参、质量指标和数值简化。它不代表语言模型、生产服务到达、跨数据集泛化或工业部署；协议和替换接口见[W4/W5指南](../../../workloads/docs/mapping_and_quality.md)。
