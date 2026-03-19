from __future__ import annotations

from typing import Dict, List, Optional, Protocol, Type, TypeVar, runtime_checkable

from agent.task_state import TaskState


@runtime_checkable
class AbilityInterface(Protocol):
    """Contract that all abilities must satisfy."""

    name: str
    required_fields: List[str]

    async def execute(self, state: TaskState) -> TaskState:
        ...


ABILITY_REGISTRY: Dict[str, AbilityInterface] = {}

TAbility = TypeVar("TAbility", bound=AbilityInterface)


def _coerce_ability(ability: AbilityInterface | Type[TAbility]) -> AbilityInterface:
    if isinstance(ability, type):
        return ability()  # type: ignore[call-arg]
    return ability


def register_ability(ability: AbilityInterface | Type[TAbility]) -> AbilityInterface | Type[TAbility]:
    """Register ability instance or ability class by unique name."""
    coerced = _coerce_ability(ability)
    name = (getattr(coerced, "name", "") or "").strip()
    if not name:
        raise ValueError("Ability must define a non-empty `name`.")
    ABILITY_REGISTRY[name] = coerced
    return ability


def get_ability(name: str) -> Optional[AbilityInterface]:
    return ABILITY_REGISTRY.get(name)


def _missing_required_fields(state: TaskState, required_fields: List[str]) -> List[str]:
    missing: List[str] = []
    for field_name in required_fields or []:
        value = state.fields.get(field_name)
        if value in (None, "", [], {}):
            missing.append(field_name)
    return missing


async def run_ability(name: str, state: TaskState) -> TaskState:
    """Run one ability and update state bookkeeping."""
    ability = get_ability(name)
    if ability is None:
        raise ValueError(f"Ability `{name}` is not registered.")

    required_fields = list(getattr(ability, "required_fields", []) or [])
    missing = _missing_required_fields(state, required_fields)
    if missing:
        msg = f"Ability `{name}` missing required fields: {', '.join(missing)}"
        state.add_error(msg)
        raise ValueError(msg)

    try:
        result = await ability.execute(state)
        next_state = result or state
        next_state.mark_step_done(name)
        return next_state
    except Exception as exc:
        state.increase_retry(name)
        state.add_error(f"{name}: {exc}")
        raise
