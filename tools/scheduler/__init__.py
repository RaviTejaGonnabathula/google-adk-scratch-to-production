"""Read-only synthetic availability; this module cannot book appointments."""
from dataclasses import dataclass
from datetime import date

from google.adk.tools import FunctionTool, ToolContext

from tools.contracts import ToolInputError, authorize, execute, mock_authorization, validate_text


def validate_day(day):
    day = validate_text(day, maximum=10)
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise ToolInputError("day must be an ISO date.") from None
    if parsed.isoformat() != day:
        raise ToolInputError("day must be YYYY-MM-DD.")
    return day


@dataclass(frozen=True)
class MockSchedulingAdapter:
    times: tuple[str, ...] = ("09:00", "14:00")

    def check_slots(self, day, context):
        authorize(context, "scheduler:read")
        return {"day": validate_day(day), "times": list(self.times), "timezone": "UTC", "synthetic": True}


def get_tools(*, adapter, authorization=mock_authorization):
    def check_slots(day: str, tool_context: ToolContext) -> dict:
        """Return synthetic availability for a YYYY-MM-DD date; never make a booking."""
        def operation():
            context = authorization(tool_context)
            authorize(context, "scheduler:read")
            return adapter.check_slots(validate_day(day), context)
        return execute(operation)
    return [FunctionTool(check_slots)]
