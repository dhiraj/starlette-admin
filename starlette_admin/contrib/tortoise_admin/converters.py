from typing import Any, Callable, Dict, Optional, Sequence, Type

from tortoise import fields
from starlette_admin.converters import BaseModelConverter, converts
from starlette_admin.fields import (
    BaseField,
    BooleanField,
    DateField,
    DateTimeField,
    DecimalField,
    EmailField,
    FloatField,
    HasMany,
    HasOne,
    IntegerField,
    JSONField,
    StringField,
    TextAreaField,
    TimeField,
    URLField,
)
from starlette_admin.exceptions import NotSupportedColumn
from starlette_admin.helpers import slugify_class_name


class BaseTortoiseModelConverter(BaseModelConverter):
    """Base converter for TortoiseORM fields to admin fields."""

    def get_converter(self, field_type: Any) -> Callable[..., BaseField]:
        """Get the converter function for a given field type."""
        converter = self.find_converter_for_field_type(type(field_type))
        if converter is not None:
            return converter
        raise NotSupportedColumn(
            f"Field {field_type} cannot be converted automatically. "
            "Find the appropriate field manually or provide your custom converter"
        )

    def convert(self, *args: Any, **kwargs: Any) -> BaseField:
        """Convert a field using the appropriate converter."""
        return self.get_converter(kwargs.get("field"))(*args, **kwargs)

    def find_converter_for_field_type(self, field_type: Any) -> Optional[Callable[..., BaseField]]:
        """Find a converter function for a given field type."""
        for base in field_type.__mro__:
            type_string = f"{base.__module__}.{base.__name__}"
            if type_string in self.converters:
                return self.converters[type_string]
            if base.__name__ in self.converters:
                return self.converters[base.__name__]
        return None

    def convert_fields_list(
        self, *, fields: Sequence[Any], model: Type[Any], **kwargs: Any
    ) -> Sequence[BaseField]:
        """Convert a list of fields to admin fields."""
        converted_fields = []
        for field in fields:
            if isinstance(field, BaseField):
                converted_fields.append(field)
            else:
                field_obj = model._meta.fields_map.get(field)
                if field_obj is None:
                    raise ValueError(f"Can't find field with name {field}")
                
                if isinstance(field_obj, fields.RelationalField):
                    identity = slugify_class_name(field_obj.related_model.__name__)
                    if isinstance(field_obj, (fields.ForeignKeyField, fields.OneToOneField)):
                        converted_fields.append(HasOne(field_obj.model_field_name, identity=identity))
                    else:
                        converted_fields.append(HasMany(field_obj.model_field_name, identity=identity))
                else:
                    converted_fields.append(
                        self.convert(name=field, field=field_obj)
                    )
        return converted_fields


class ModelConverter(BaseTortoiseModelConverter):
    """Default converter implementation for TortoiseORM fields."""

    @classmethod
    def _field_common(cls, *, name: str, field: fields.Field, **kwargs: Any) -> Dict[str, Any]:
        """Get common field attributes."""
        return {
            "name": name,
            "help_text": field.description,
            "required": not field.null and not field.generated,
        }

    @classmethod
    def _string_common(cls, *, field: fields.Field, **kwargs: Any) -> Dict[str, Any]:
        """Get common string field attributes."""
        if hasattr(field, "max_length") and field.max_length:
            return {"maxlength": field.max_length}
        return {}

    @converts("CharField", "UUIDField")
    def conv_string(self, *args: Any, **kwargs: Any) -> BaseField:
        return StringField(
            **self._field_common(*args, **kwargs),
            **self._string_common(*args, **kwargs),
        )

    @converts("TextField")
    def conv_text(self, *args: Any, **kwargs: Any) -> BaseField:
        return TextAreaField(
            **self._field_common(*args, **kwargs),
            **self._string_common(*args, **kwargs),
        )

    @converts("BooleanField")
    def conv_boolean(self, *args: Any, **kwargs: Any) -> BaseField:
        return BooleanField(
            **self._field_common(*args, **kwargs),
        )

    @converts("DatetimeField")
    def conv_datetime(self, *args: Any, **kwargs: Any) -> BaseField:
        return DateTimeField(
            **self._field_common(*args, **kwargs),
        )

    @converts("DateField")
    def conv_date(self, *args: Any, **kwargs: Any) -> BaseField:
        return DateField(
            **self._field_common(*args, **kwargs),
        )

    @converts("TimeField")
    def conv_time(self, *args: Any, **kwargs: Any) -> BaseField:
        return TimeField(
            **self._field_common(*args, **kwargs),
        )

    @converts("IntField", "SmallIntField", "BigIntField")
    def conv_integer(self, *args: Any, **kwargs: Any) -> BaseField:
        field = kwargs["field"]
        extra = self._field_common(*args, **kwargs)
        if hasattr(field, "minimum"):
            extra["min"] = field.minimum
        if hasattr(field, "maximum"):
            extra["max"] = field.maximum
        return IntegerField(**extra)

    @converts("FloatField")
    def conv_float(self, *args: Any, **kwargs: Any) -> BaseField:
        return FloatField(
            **self._field_common(*args, **kwargs),
        )

    @converts("DecimalField")
    def conv_decimal(self, *args: Any, **kwargs: Any) -> BaseField:
        return DecimalField(
            **self._field_common(*args, **kwargs),
        )

    @converts("JSONField")
    def conv_json(self, *args: Any, **kwargs: Any) -> BaseField:
        return JSONField(
            **self._field_common(*args, **kwargs),
        )

    @converts("EmailField")
    def conv_email(self, *args: Any, **kwargs: Any) -> BaseField:
        return EmailField(
            **self._field_common(*args, **kwargs),
            **self._string_common(*args, **kwargs),
        )

    @converts("URLField")
    def conv_url(self, *args: Any, **kwargs: Any) -> BaseField:
        return URLField(
            **self._field_common(*args, **kwargs),
            **self._string_common(*args, **kwargs),
        )
