from typing import Any, Dict, List, Optional, Sequence, Type

from starlette.requests import Request
from starlette_admin import BaseField
from starlette_admin.exceptions import FormValidationError
from starlette_admin.views import BaseModelView
from tortoise import Model
from tortoise.expressions import Q
from tortoise.fields import Field, ReverseRelation, relational

from .fields import MultiplePKField
from .helpers import normalize_list


class ModelView(BaseModelView):
    """A view for managing TortoiseORM models."""

    def __init__(
        self,
        model: Type[Model],
        icon: Optional[str] = None,
        name: Optional[str] = None,
        label: Optional[str] = None,
        identity: Optional[str] = None,
    ):
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
            field_name for field_name in self.fields
            if not isinstance(model._meta.fields_map.get(field_name), (ReverseRelation, relational.RelationalField))
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
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
    ) -> Sequence[Any]:
        """Find all records with pagination, filtering and sorting."""
        query = self.model.all()

        # Apply filters
        if where:
            query = query.filter(**where)

        # Apply sorting
        if order_by:
            query = query.order_by(*order_by)

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
        where: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count total records with filtering."""
        query = self.model.all()
        if where:
            query = query.filter(**where)
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

    async def create(self, request: Request, data: Dict[str, Any]) -> Any:
        """Create a new record."""
        try:
            # Handle relations
            relations = {}
            for field_name, field in self.model._meta.fields_map.items():
                if isinstance(field, relational.RelationalField) and field_name in data:
                    relations[field_name] = data.pop(field_name)

            # Create instance
            instance = await self.model.create(**data)

            # Set relations
            for field_name, value in relations.items():
                field = self.model._meta.fields_map[field_name]
                if isinstance(field, relational.ManyToManyField):
                    await getattr(instance, field_name).add(*value)
                else:
                    setattr(instance, field_name, value)
                    await instance.save()

            return instance
        except Exception as e:
            raise FormValidationError({"error": str(e)})

    async def edit(self, request: Request, pk: Any, data: Dict[str, Any]) -> Any:
        """Edit an existing record."""
        try:
            instance = await self.find_by_pk(request, pk)
            if not instance:
                raise FormValidationError({"error": "Record not found"})

            # Handle relations
            relations = {}
            for field_name, field in self.model._meta.fields_map.items():
                if isinstance(field, relational.RelationalField) and field_name in data:
                    relations[field_name] = data.pop(field_name)

            # Update fields
            for key, value in data.items():
                setattr(instance, key, value)
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

            return instance
        except Exception as e:
            raise FormValidationError({"error": str(e)})

    async def delete(self, request: Request, pks: List[Any]) -> Optional[int]:
        """Delete records by primary keys."""
        try:
            deleted_count = await self.model.filter(pk__in=pks).delete()
            return deleted_count
        except Exception as e:
            raise FormValidationError({"error": str(e)})

    async def get_field_value(
        self, request: Request, field: BaseField, obj: Any
    ) -> Any:
        """Get field value from model instance."""
        value = getattr(obj, field.name, None)
        if isinstance(value, ReverseRelation):
            return await value.all()
        return value

    def get_search_query(self, request: Request, term: str) -> Q:
        """Build search query for full text search."""
        search_fields = self.searchable_fields or []
        if not search_fields:
            return Q()

        queries = []
        for field in search_fields:
            queries.append(Q(**{f"{field}__icontains": term}))
        return Q(*queries, join_type="OR")
