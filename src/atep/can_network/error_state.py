from uuid import UUID

from atep.can_network.models import CanNetwork
from atep.can_network.schemas import CanNodeErrorMode, CanNodeErrorState


def derive_error_mode(tec: int, rec: int) -> CanNodeErrorMode:
    if tec >= 256:
        return CanNodeErrorMode.BUS_OFF
    if tec >= 128 or rec >= 128:
        return CanNodeErrorMode.ERROR_PASSIVE
    return CanNodeErrorMode.ERROR_ACTIVE


def node_error_state(network: CanNetwork, node_id: UUID) -> CanNodeErrorState:
    value = (network.error_states or {}).get(str(node_id), {})
    tec = int(value.get("transmit_error_count", 0))
    rec = int(value.get("receive_error_count", 0))
    return CanNodeErrorState(
        transmit_error_count=tec,
        receive_error_count=rec,
        state=derive_error_mode(tec, rec),
    )


def set_node_error_state(
    network: CanNetwork, node_id: UUID, *, tec: int, rec: int
) -> CanNodeErrorState:
    state = CanNodeErrorState(
        transmit_error_count=min(tec, 256),
        receive_error_count=min(rec, 255),
        state=derive_error_mode(tec, rec),
    )
    values = dict(network.error_states or {})
    values[str(node_id)] = state.model_dump(mode="json")
    network.error_states = values
    return state


def is_bus_off(network: CanNetwork, node_id: UUID) -> bool:
    return node_error_state(network, node_id).state is CanNodeErrorMode.BUS_OFF
