"""Pagination parameters (limit 1..100, offset >= 0) and the list envelope."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Generic, Sequence, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, Field

T = TypeVar('T')

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description='Page size, 1 to 100')] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, description='Items to skip, 0 or more')] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


PageDep = Annotated[PageParams, Depends(page_params)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_LIMIT)
    offset: int = Field(ge=0)

    @classmethod
    def build(cls, items: Sequence[T], total: int, params: PageParams) -> 'Page[T]':
        return cls(items=list(items), total=total, limit=params.limit, offset=params.offset)
