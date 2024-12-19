from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from tortoise.expressions import Q


def normalize_list(
    value: Optional[Union[List[Any], Any]], is_default_sort_list: bool = False
) -> List[Any]:
    """Normalize a value to a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        if is_default_sort_list:
            return [(v, False) if isinstance(v, str) else v for v in value]
        return list(value)
    if is_default_sort_list:
        return [(value, False)] if isinstance(value, str) else [value]
    return [value]


def build_search_query(term: str, fields: List[str]) -> Q:
    """Build a search query for the given term and fields."""
    if not fields or not term:
        return Q()
    
    queries = []
    for field in fields:
        queries.append(Q(**{f"{field}__icontains": term}))
    return Q(*queries, join_type="OR")


def build_order_query(order_by: List[str]) -> List[str]:
    """Build order by query from order list."""
    order_clauses = []
    for value in order_by:
        field, direction = value.strip().split(maxsplit=1)
        order_clauses.append(
            f"-{field}" if direction.lower() == "desc" else field
        )
    return order_clauses


def build_filter_query(where: Dict[str, Any], model: Any) -> Q:
    """Build filter query from where dict."""
    if not where:
        return Q()
    
    queries = []
    for field, value in where.items():
        if isinstance(value, (list, tuple)):
            queries.append(Q(**{f"{field}__in": value}))
        else:
            queries.append(Q(**{field: value}))
    return Q(*queries, join_type="AND")
