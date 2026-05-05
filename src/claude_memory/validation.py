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


def requires_session(
    session_field: str = "session_id", empty_on_missing: bool = False
) -> Callable[..., Any]:
    """Decorator to ensure a session exists before executing a service method.

    If the session does not exist, returns either an empty list (if empty_on_missing=True)
    or a structured error dict.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(self: Any, params: BaseModel, *args: Any, **kwargs: Any) -> Any:
            session_id = getattr(params, session_field, None)

            if not session_id:
                return await func(self, params, *args, **kwargs)

            # A session is just an entity in the graph with label Session,
            # or we can just check if it exists as a node
            existing = self.repo.get_node(session_id)
            if not existing:
                if empty_on_missing:
                    return []
                return {"error": f"Session not found: {session_id}"}

            return await func(self, params, *args, **kwargs)

        return wrapper

    return decorator
