"""Small deterministic boundaries; provider integrations are deliberately absent."""
from dataclasses import dataclass
from typing import Callable, Literal, Protocol, TypedDict, runtime_checkable

from google.adk.tools import ToolContext


class ToolInputError(ValueError):
    pass


class AuthorizationError(PermissionError):
    pass


class AdapterError(RuntimeError):
    """Expected provider failure; private upstream details stay out of results."""


@dataclass(frozen=True)
class AuthorizationContext:
    subject: str
    tenant: str
    scopes: frozenset[str]


AuthorizationProvider = Callable[[ToolContext], AuthorizationContext]


def mock_authorization(_context: ToolContext) -> AuthorizationContext:
    """Synthetic demo identity, never a claim about the authenticated caller."""
    return AuthorizationContext("demo-reader", "demo", frozenset({"faq:read", "scheduler:read", "rag:read"}))


def authorize(context: AuthorizationContext, scope: str, tenant="demo"):
    if not isinstance(context, AuthorizationContext) or not context.subject or context.tenant != tenant or scope not in context.scopes:
        raise AuthorizationError("Operation is not authorized.")


def validate_text(value, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ToolInputError("A nonempty bounded string is required.")
    return value.strip()


class ToolResult(TypedDict):
    status: Literal["success", "error"]
    data: dict
    error: str | None


def execute(operation) -> ToolResult:
    try:
        return {"status": "success", "data": operation(), "error": None}
    except AuthorizationError:
        return {"status": "error", "data": {}, "error": "not_authorized"}
    except ToolInputError:
        return {"status": "error", "data": {}, "error": "invalid_input"}
    except TimeoutError:
        return {"status": "error", "data": {}, "error": "adapter_timeout"}
    except AdapterError:
        return {"status": "error", "data": {}, "error": "adapter_unavailable"}


@runtime_checkable
class FAQAdapter(Protocol):
    def lookup(self, question: str, context: AuthorizationContext) -> dict: ...


@runtime_checkable
class SchedulingAdapter(Protocol):
    def check_slots(self, day: str, context: AuthorizationContext) -> dict: ...


@runtime_checkable
class RetrievalAdapter(Protocol):
    def retrieve(self, query: str, context: AuthorizationContext) -> dict: ...
