from typing import Any, List

from starlette.requests import Request
from starlette_admin import StringField
from starlette_admin._types import RequestAction


class MultiplePKField(StringField):
    """Field for handling composite primary keys."""

    def __init__(self, name: str) -> None:
        super().__init__(name=name, label="ID", required=True, read_only=True)

    async def parse_obj(self, request: Request, obj: Any) -> Any:
        """Get primary key value from model instance."""
        return getattr(obj, self.name)

    async def serialize_value(
        self, request: Request, value: Any, action: RequestAction
    ) -> Any:
        """Convert primary key value to string."""
        if isinstance(value, (list, tuple)):
            return ",".join(str(v) for v in value)
        return str(value)

    def parse_value(self, value: Any) -> Any:
        """Parse primary key value from string."""
        if isinstance(value, str) and "," in value:
            return value.split(",")
        return value
