"""Decorators for semantic validation of MCP requests at the service boundary."""

import functools
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel


def requires_entity(
    entity_field: str = "entity_id", empty_on_missing: bool = True
) -> Callable[..., Any]:
    """Decorator to ensure an entity exists before executing a service method.

    If the entity does not exist, returns either an empty list (if empty_on_missing=True)
    or a structured error dict, depending on the tool's expected return signature.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(self: Any, params: BaseModel, *args: Any, **kwargs: Any) -> Any:
            entity_id = getattr(params, entity_field, None)

            # If the parameter isn't present, let the function handle it or fail loud.
            if not entity_id:
                return await func(self, params, *args, **kwargs)

            existing = self.repo.get_node(entity_id)
            if not existing:
                if empty_on_missing:
                    return []
                return {"error": f"Entity not found: {entity_id}"}

            return await func(self, params, *args, **kwargs)

        return wrapper

    return decorator
