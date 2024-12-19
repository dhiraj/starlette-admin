from typing import Any, Dict, List, Optional, Sequence, Type, Union

from starlette.requests import Request
from starlette.responses import Response
from starlette_admin import BaseField
from starlette_admin._types import RequestAction
from starlette_admin.exceptions import ActionFailed, FormValidationError
from starlette_admin.fields import FileField, RelationField
from starlette_admin.views import BaseModelView
from tortoise import Model
from tortoise.exceptions import ValidationError
from tortoise.expressions import Q
from tortoise.fields import Field, ReverseRelation, relational

from .converters import ModelConverter
from .fields import MultiplePKField
from .helpers import (
    build_filter_query,
    build_order_query,
    build_search_query,
    normalize_list,
)


class ModelView(BaseModelView):
    """A view for managing TortoiseORM models."""

    def __init__(
        self,
        model: Type[Model],
        icon: Optional[str] = None,
        name: Optional[str] = None,
        label: Optional[str] = None,
        identity: Optional[str] = None,
        converter: Optional[ModelConverter] = None,
    ):
        """Initialize the ModelView.
        
        Args:
            model: The TortoiseORM model class
            icon: Icon for the model in the admin interface
            name: Display name for the model
            label: Label for the model (plural form)
            identity: Unique identifier for the model
            converter: Custom field converter (optional)
        """
        # Initialize parent class first to set up actions
        super().__init__()
        
        self.model = model
        self.identity = identity or self.identity or model.__name__.lower()
        self.label = label or self.label or model.__name__ + "s"
        self.name = name or self.name or model.__name__
        self.icon = icon

        # Get model fields if not explicitly set
        if not self.fields:
            self.fields = []
            for field_name, field in model._meta.fields_map.items():
                if isinstance(field, Field):
                    self.fields.append(field_name)

        # Convert fields using converter
        self.fields = (converter or ModelConverter()).convert_fields_list(
            fields=self.fields,
            model=self.model
        )

        # Set up primary key field
        pk_name = model._meta.pk_attr
        self.pk_attr = pk_name
        self.pk_field = next(
            (f for f in self.fields if f.name == pk_name),
            MultiplePKField(pk_name)
        )

        # Normalize field lists
        self.exclude_fields_from_list = normalize_list(self.exclude_fields_from_list)
        self.exclude_fields_from_detail = normalize_list(self.exclude_fields_from_detail)
        self.exclude_fields_from_create = normalize_list(self.exclude_fields_from_create)
        self.exclude_fields_from_edit = normalize_list(self.exclude_fields_from_edit)
        _default_list = [
            field.name
            for field in self.fields
            if not isinstance(field, (RelationField, FileField))
        ]
        self.searchable_fields = normalize_list(
            self.searchable_fields if self.searchable_fields is not None else _default_list
        )
        self.sortable_fields = normalize_list(
            self.sortable_fields if self.sortable_fields is not None else _default_list
        )
        self.export_fields = normalize_list(self.export_fields)
        self.fields_default_sort = normalize_list(self.fields_default_sort, is_default_sort_list=True)

    async def find_all(
        self,
        request: Request,
        skip: int = 0,
        limit: int = 100,
        where: Union[Dict[str, Any], str, None] = None,
        order_by: Optional[List[str]] = None,
    ) -> Sequence[Any]:
        """Find all records with pagination, filtering and sorting."""
        query = self.model.all()

        # Apply filters
        if where is not None:
            if isinstance(where, dict):
                query = query.filter(build_filter_query(where, self.model))
            else:
                query = query.filter(self.get_search_query(request, str(where)))

        # Apply sorting
        if order_by:
            query = query.order_by(*build_order_query(order_by))

        # Apply pagination
        if skip:
            query = query.offset(skip)
        if limit > 0:
            query = query.limit(limit)

        # Load related fields
        for field_name, field in self.model._meta.fields_map.items():
            if isinstance(field, relational.RelationalField):
                query = query.prefetch_related(field_name)

        return await query

    async def count(
        self,
        request: Request,
        where: Union[Dict[str, Any], str, None] = None,
    ) -> int:
        """Count total records with filtering."""
        query = self.model.all()
        if where is not None:
            if isinstance(where, dict):
                query = query.filter(build_filter_query(where, self.model))
            else:
                query = query.filter(self.get_search_query(request, str(where)))
        return await query.count()

    async def find_by_pk(self, request: Request, pk: Any) -> Optional[Any]:
        """Find one record by primary key."""
        try:
            query = self.model.get(pk=pk)
            # Load related fields
            for field_name, field in self.model._meta.fields_map.items():
                if isinstance(field, relational.RelationalField):
                    query = query.prefetch_related(field_name)
            return await query
        except Exception:
            return None

    async def find_by_pks(self, request: Request, pks: List[Any]) -> Sequence[Any]:
        """Find records by primary keys."""
        query = self.model.filter(pk__in=pks)
        # Load related fields
        for field_name, field in self.model._meta.fields_map.items():
            if isinstance(field, relational.RelationalField):
                query = query.prefetch_related(field_name)
        return await query

    async def validate(self, request: Request, data: Dict[str, Any]) -> None:
        """Validate the data before create/edit."""
        try:
            # Create a temporary instance for validation
            instance = self.model(**data)
            await instance.validate()
        except ValidationError as e:
            raise FormValidationError(e.errors)

    async def create(self, request: Request, data: Dict[str, Any]) -> Any:
        """Create a new record."""
        try:
            data = await self._arrange_data(request, data)
            await self.validate(request, data)
            
            # Handle relations
            relations = {}
            for field_name, field in self.model._meta.fields_map.items():
                if isinstance(field, relational.RelationalField) and field_name in data:
                    relations[field_name] = data.pop(field_name)

            # Create instance
            instance = self.model(**data)
            await self.before_create(request, data, instance)
            await instance.save()

            # Set relations
            for field_name, value in relations.items():
                field = self.model._meta.fields_map[field_name]
                if isinstance(field, relational.ManyToManyField):
                    await getattr(instance, field_name).add(*value)
                else:
                    setattr(instance, field_name, value)
                    await instance.save()

            await self.after_create(request, instance)
            return instance
        except Exception as e:
            return self.handle_exception(e)

    async def edit(self, request: Request, pk: Any, data: Dict[str, Any]) -> Any:
        """Edit an existing record."""
        try:
            data = await self._arrange_data(request, data, True)
            await self.validate(request, data)
            
            instance = await self.find_by_pk(request, pk)
            if not instance:
                raise FormValidationError({"error": "Record not found"})

            # Handle relations
            relations = {}
            for field_name, field in self.model._meta.fields_map.items():
                if isinstance(field, relational.RelationalField) and field_name in data:
                    relations[field_name] = data.pop(field_name)

            # Update fields
            await self._populate_obj(request, instance, data, True)
            await self.before_edit(request, data, instance)
            await instance.save()

            # Update relations
            for field_name, value in relations.items():
                field = self.model._meta.fields_map[field_name]
                if isinstance(field, relational.ManyToManyField):
                    rel = getattr(instance, field_name)
                    await rel.clear()
                    await rel.add(*value)
                else:
                    setattr(instance, field_name, value)
                    await instance.save()

            await self.after_edit(request, instance)
            return instance
        except Exception as e:
            return self.handle_exception(e)

    async def delete(self, request: Request, pks: List[Any]) -> Optional[int]:
        """Delete records by primary keys."""
        try:
            objs = await self.find_by_pks(request, pks)
            for obj in objs:
                await self.before_delete(request, obj)
                await obj.delete()
            for obj in objs:
                await self.after_delete(request, obj)
            return len(objs)
        except Exception as e:
            return self.handle_exception(e)

    async def _arrange_data(
        self,
        request: Request,
        data: Dict[str, Any],
        is_edit: bool = False,
    ) -> Dict[str, Any]:
        """Arrange data before create/edit by handling relationships."""
        arranged_data: Dict[str, Any] = {}
        for field in self.get_fields_list(request, request.state.action):
            if isinstance(field, RelationField) and data[field.name] is not None:
                foreign_model = self._find_foreign_model(field.identity)
                if not field.multiple:
                    arranged_data[field.name] = await foreign_model.find_by_pk(
                        request, data[field.name]
                    )
                else:
                    arranged_data[field.name] = await foreign_model.find_by_pks(
                        request, data[field.name]
                    )
            else:
                arranged_data[field.name] = data[field.name]
        return arranged_data

    async def _populate_obj(
        self,
        request: Request,
        obj: Any,
        data: Dict[str, Any],
        is_edit: bool = False,
    ) -> Any:
        """Populate object with data handling special fields like File fields."""
        for field in self.get_fields_list(request, request.state.action):
            name, value = field.name, data.get(field.name, None)
            if isinstance(field, FileField):
                value, should_be_deleted = value
                if should_be_deleted:
                    setattr(obj, name, None)
                elif (not field.multiple and value is not None) or (
                    field.multiple and isinstance(value, list) and len(value) > 0
                ):
                    setattr(obj, name, value)
            else:
                setattr(obj, name, value)
        return obj

    async def get_field_value(
        self, request: Request, field: BaseField, obj: Any
    ) -> Any:
        """Get field value from model instance."""
        value = getattr(obj, field.name, None)
        if isinstance(value, ReverseRelation):
            return await value.all()
        return value

    def handle_exception(self, exc: Exception) -> None:
        """Handle exceptions during operations."""
        if isinstance(exc, ValidationError):
            raise FormValidationError(exc.errors)
        raise exc

    async def handle_action(
        self, request: Request, pks: List[Any], name: str
    ) -> Union[str, Response]:
        """Handle custom actions."""
        try:
            return await super().handle_action(request, pks, name)
        except Exception as exc:
            raise ActionFailed(str(exc))

    async def handle_row_action(
        self, request: Request, pk: Any, name: str
    ) -> Union[str, Response]:
        """Handle custom row actions."""
        try:
            return await super().handle_row_action(request, pk, name)
        except Exception as exc:
            raise ActionFailed(str(exc))

    def get_search_query(self, request: Request, term: str) -> Q:
        """Build search query for full text search."""
        return build_search_query(term, self.searchable_fields)
