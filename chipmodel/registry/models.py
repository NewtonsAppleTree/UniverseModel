"""可选的显式名称→构造器映射；没有导入扫描、全局注册或硬件状态。"""

from collections.abc import Callable

from chipmodel.common import identifier


# 注册表只管理软件构造入口；重复身份拒绝，动态硬件状态由创建出的实例持有。
class ModelRegistry:
    _factories: dict[str, Callable[..., object]]  # 本注册表独占的构造器映射；无物理单位。

    # 创建独立空表；不同实验不共享注册状态。
    def __init__(self) -> None:
        self._factories = {}

    # 按显式 model_id 注册 callable；不解析或执行配置字符串中的代码。
    def register(self, model_id: str, factory: Callable[..., object]) -> None:
        identifier("model_id", model_id)
        if model_id in self._factories:
            raise ValueError("model_id already registered")
        if not callable(factory):
            raise TypeError("factory must be callable")
        self._factories[model_id] = factory

    # 将显式关键字参数交给所选构造器；字段与范围校验仍由模型负责。
    def create(self, model_id: str, **parameters: object) -> object:
        if model_id not in self._factories:
            raise ValueError(f"unknown model_id: {model_id}")
        return self._factories[model_id](**parameters)

    # 返回稳定排序的名称副本；观察不暴露内部可变映射。
    def model_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
