"""The only surface other modules may import from `categories`. Functions use the caller's open connection."""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from . import repository as repo


def list_categories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [{'id': r['id'], 'slug': r['slug'], 'name': r['name']} for r in repo.list_all(conn)]


def exists(conn: sqlite3.Connection, category_id: int) -> bool:
    return repo.exists(conn, category_id)


def by_ids(conn: sqlite3.Connection, category_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """`id -> {id, slug, name}` for the existing categories among `category_ids`."""
    ids = list(dict.fromkeys(category_ids))
    return {int(r['id']): {'id': r['id'], 'slug': r['slug'], 'name': r['name']} for r in repo.get_many(conn, ids)}


def ids_matching(conn: sqlite3.Connection, ref: str) -> list[int]:
    """Ids of categories matching a slug or a numeric id given as text."""
    return repo.ids_matching(conn, ref)


def id_by_slug(conn: sqlite3.Connection, slug: str) -> int | None:
    return repo.id_by_slug(conn, slug)
