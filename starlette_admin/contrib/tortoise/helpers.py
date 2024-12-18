from typing import Any, List, Optional, Sequence, Tuple, Union


def normalize_list(
    arr: Optional[Sequence[Any]], is_default_sort_list: bool = False
) -> Optional[Union[List[str], List[Tuple[str, bool]]]]:
    """Convert field names to strings and validate format."""
    if arr is None:
        return None
    
    _new_list = []
    for v in arr:
        if isinstance(v, str):
            if is_default_sort_list:
                _new_list.append((v, False))  # Default to ascending order
            else:
                _new_list.append(v)
        elif (
            isinstance(v, tuple) and is_default_sort_list
        ):  # Support for fields_default_sort
            if len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], bool):
                _new_list.append((v[0], v[1]))
            else:
                raise ValueError(
                    "Invalid argument, Expected Tuple[str, bool]"
                )
        else:
            raise ValueError(f"Expected str, got {type(v).__name__}")
    return _new_list
