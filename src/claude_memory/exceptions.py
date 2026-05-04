"""Domain exceptions for the Claude Memory system.

Centralises typed errors so callers can distinguish operational
failures from "no results found".
"""


class SearchError(Exception):
    """Raised when the search pipeline encounters an infrastructure failure.

    Distinguishes "no results found" (empty list returned normally) from
    "the memory system is degraded" (this exception).  Callers should
    catch this to surface a clear error to the user rather than silently
    returning an empty result set.
    """
