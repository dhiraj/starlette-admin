from typing import Any, List, Optional, Sequence, Tuple, Union
from uuid import UUID

from starlette.requests import Request
from starlette_admin import StringField
from starlette_admin._types import RequestAction
from starlette_admin.exceptions import FormValidationError


class MultiplePKField(StringField):
    """Field for handling composite primary keys in TortoiseORM models.
    
    This field handles both single and composite primary keys, automatically converting
    between the internal representation and the string format used in URLs and forms.
    
    For composite primary keys, values are stored as tuples internally but converted
    to comma-separated strings for external representation.
    
    Example:
        ```python
        class OrderItem(Model):
            order_id = fields.IntField(pk=True)
            item_id = fields.IntField(pk=True)
            quantity = fields.IntField()
            
            class Meta:
                unique_together = (("order_id", "item_id"),)
        
        # The primary key will be handled as:
        # Internal: (1, 2)
        # External: "1,2"
        ```
    """

    def __init__(self, name: str) -> None:
        """Initialize the primary key field.
        
        Args:
            name: Name of the field (usually the primary key attribute name)
        """
        super().__init__(name=name, label="ID", required=True, read_only=True)

    async def parse_obj(self, request: Request, obj: Any) -> Union[Tuple[Any, ...], Any]:
        """Get primary key value from model instance.
        
        Returns a tuple for composite keys, single value otherwise.
        """
        value = getattr(obj, self.name)
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return value

    async def serialize_value(
        self, request: Request, value: Any, action: RequestAction
    ) -> str:
        """Convert primary key value to string representation.
        
        Handles various types of primary keys including:
        - Single values (int, str, UUID)
        - Composite keys (tuple of values)
        """
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ",".join(str(v) for v in value)
        if isinstance(value, UUID):
            return str(value)
        return str(value)

    def parse_value(self, value: Any) -> Union[Tuple[Any, ...], Any]:
        """Parse primary key value from string representation.
        
        Converts comma-separated strings back to tuples for composite keys.
        Validates that all parts of composite keys are provided.
        
        Raises:
            FormValidationError: If composite key is missing required parts
        """
        if not value:
            return None
        if isinstance(value, str) and "," in value:
            parts = value.split(",")
            if not all(parts):
                raise FormValidationError(
                    {self.name: "All parts of composite primary key must be provided"}
                )
            return tuple(parts)
        return value
