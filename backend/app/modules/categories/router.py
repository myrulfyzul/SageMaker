"""Public category list (Req 9.13)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..auth.deps import ConnDep
from .api import list_categories

router = APIRouter(prefix='/api/categories', tags=['categories'])


@router.get('')
def get_categories(conn: ConnDep) -> list[dict[str, Any]]:
    return list_categories(conn)
