from __future__ import annotations





if TYPE_CHECKING:
    from typing import Union
    from typing_extensions import TypeAlias
    JSON_TYPE: TypeAlias = Union[dict[str, "JSON_TYPE"], list["JSON_TYPE"], str, int, float, bool, None]
else:
    JSON_TYPE = Any