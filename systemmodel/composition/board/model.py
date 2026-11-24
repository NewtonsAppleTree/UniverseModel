"""Board membership references one resource inventory; no copied chip state or additive container capacity."""

from dataclasses import dataclass
from typing import Literal

from chipmodel.composition.die.topology import ancestry
from contracts.hardware.network import string_tuple, validate_identity
from systemmodel.topology.graph import SystemTopology


# A board declares its compute/device members and checks their physical containment against an independent topology.
@dataclass(frozen=True, slots=True, kw_only=True)
class BoardSpec:
    board_id: str  # Existing pure-container resource ID; the board adds no service capacity.
    device_ids: tuple[str, ...]  # Modeled CPU/accelerator/NIC package instances directly declared as board devices.
    source_ref: str  # Board assembly/profile reference or explicit manual assumption.
    schema_version: Literal['system-board/v1'] = 'system-board/v1'  # Static device placement only.

    # Freeze membership and reject duplicate identity; independent board validation uses an explicit topology.
    def __post_init__(self) -> None:
        for name in ('board_id','source_ref'):
            validate_identity(name,getattr(self,name))
        object.__setattr__(self,'device_ids',tuple(sorted(string_tuple('device_ids',self.device_ids,unique=True))))
        if self.board_id in self.device_ids or self.schema_version!='system-board/v1':
            raise ValueError('invalid board identity/schema')

    # Every device belongs below this noncharging board container and refers to an actual model identity.
    def validate(self, topology: SystemTopology) -> None:
        if not isinstance(topology,SystemTopology):
            raise TypeError('board validation requires SystemTopology')
        resources = {r.instance_id:r for r in topology.resources}
        paths = ancestry(topology.resources)
        if self.board_id not in resources or resources[self.board_id].model_id is not None:
            raise ValueError('board must reference a pure resource container')
        for key in self.device_ids:
            if key not in resources or self.board_id not in paths[key] or resources[key].model_id is None:
                raise ValueError('board device missing, outside owner scope or without model reference')
            if set(paths[key][1:])&set(self.device_ids):
                raise ValueError('board device references cannot include a device and its internals')
