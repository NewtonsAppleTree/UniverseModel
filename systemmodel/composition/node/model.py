"""One host node combines independently validated boards and standalone device references."""

from dataclasses import dataclass
from typing import Literal

from chipmodel.composition.die.topology import ancestry
from contracts.hardware.network import string_tuple
from contracts.versions.json_codec import content_hash
from systemmodel.composition.board.model import BoardSpec
from systemmodel.topology.graph import SystemTopology, freeze_inventory


# Node membership refers to topology scope and existing instances; it does not instantiate a second hardware hierarchy.
@dataclass(frozen=True, slots=True, kw_only=True)
class NodeSpec:
    topology: SystemTopology  # Authoritative resource/port/domain inventory; scope_id is the node ID.
    boards: tuple[BoardSpec, ...] = ()  # Optional disjoint board subtrees; each remains independently validatable.
    standalone_device_ids: tuple[str, ...] = ()  # Modeled devices outside every declared board, e.g. a host CPU.
    schema_version: Literal['system-node/v1'] = 'system-node/v1'  # Static node inventory, not a scheduler or device executor.

    # Enforce complete single ownership of declared devices and disjoint board scopes.
    def __post_init__(self) -> None:
        if not isinstance(self.topology,SystemTopology) or self.schema_version!='system-node/v1':
            raise ValueError('invalid node topology/schema')
        object.__setattr__(self,'boards',freeze_inventory('boards',self.boards,BoardSpec,'board_id'))
        object.__setattr__(self,'standalone_device_ids',tuple(sorted(string_tuple('standalone_device_ids',self.standalone_device_ids,unique=True,allow_empty=True))))
        resources = {r.instance_id:r for r in self.topology.resources}
        paths = ancestry(self.topology.resources)
        board_ids = {board.board_id for board in self.boards}
        members = list(self.standalone_device_ids)
        for board in self.boards:
            board.validate(self.topology)
            if board.board_id==self.topology.scope_id or set(paths[board.board_id][1:])&board_ids:
                raise ValueError('node boards must be disjoint proper subtrees')
            members.extend(board.device_ids)
        for key in self.standalone_device_ids:
            if key not in resources or resources[key].model_id is None or set(paths[key])&board_ids:
                raise ValueError('standalone device missing, unmodeled or owned by a board')
        if not members or len(set(members))!=len(members):
            raise ValueError('node requires unique device references')
        if any(set(paths[key][1:])&set(members) for key in members):
            raise ValueError('node device inventory overlaps with device internals')

    # Return declared device IDs once, independent of board ordering; support resources are not promoted to devices.
    @property
    def device_ids(self) -> tuple[str, ...]:
        return tuple(sorted((*self.standalone_device_ids,*(key for board in self.boards for key in board.device_ids))))

    # Include topology provenance and all membership declarations in the node identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)
