from __future__ import annotations

from typing import List

from agent.abilities.base import register_ability
from agent.task_state import TaskState
from services.tree_id_resolver import TreeIDResolver


@register_ability
class SearchTreeAbility:
    name = "search_tree"
    required_fields: List[str] = []

    def __init__(self) -> None:
        self._resolver = TreeIDResolver()

    async def execute(self, state: TaskState) -> TaskState:
        full_tree_id = self._resolver.resolve_from_case(state.fields or {})
        if full_tree_id:
            state.fields["tree_id"] = full_tree_id
            parts = full_tree_id.split()
            if len(parts) >= 2:
                slope_no = parts[0]
                tree_no = parts[-1]
                state.fields["tree_no"] = tree_no
                tree_row = self._resolver.lookup_tree(slope_no, tree_no)
                if tree_row:
                    state.external_data["tree_lookup"] = tree_row
        return state
