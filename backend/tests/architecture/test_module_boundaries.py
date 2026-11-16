"""Architecture test (task 22.1, Req 1.6): table ownership and module import boundaries.

1. Every table named in a module's `repository.py` (after FROM, JOIN, INTO, UPDATE, DELETE FROM) must be in that
   module's owned set (design.md, "Table ownership").
2. A module may import another module only through its `api` (or the narrow allow-list below), never its
   `repository`, `service` or `schemas`.

Narrow allow-list (each entry is justified):
- `auth.deps`: FastAPI dependency wiring (ConnDep, require_staff, ...) used by every router. It is HTTP plumbing,
  not business logic, so routers may import it. It is not one of the forbidden layers.
- `legacy` has no repository and `checkout` owns no tables (design); both are asserted below rather than skipped.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

MODULES_DIR = Path(__file__).resolve().parents[2] / 'app' / 'modules'

OWNED_TABLES: dict[str, set[str]] = {
    'auth': {'sessions', 'login_attempts'},
    'users': {'users', 'addresses', 'favourites'},
    'categories': {'categories'},
    'products': {'products', 'product_variations', 'product_images'},
    'inventory': {'stock_levels', 'stock_adjustments', 'inventory_settings'},
    'cart': {'cart_lines'},
    'checkout': set(),  # orchestration only, owns no tables
    'orders': {'orders', 'order_lines', 'order_history'},
    'payments': {'payments'},
    'artisans': {'artisans'},
    'production': {'production_jobs', 'production_progress'},
    'custom_orders': {'custom_orders', 'custom_order_images'},
    'notifications': {'notifications'},
    'analytics': set(),
    'forecasting': set(),
    'settings': {'app_settings'},
    'legacy': set(),  # compat router, uses other modules' api only
}

FORBIDDEN_LAYERS = {'repository', 'service', 'schemas'}
# (importing module, imported "module.submodule") pairs that are allowed.
ALLOWED_CROSS_IMPORTS: set[str] = {'auth.deps'}

_SQL_START = re.compile(r'^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|REPLACE)\b', re.I)
_TABLE_REF = re.compile(r'\b(FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_]\w*)(\()?', re.I)
_CTE = re.compile(r'\b([A-Za-z_]\w*)\s+AS\s*\(', re.I)


def _module_dirs() -> list[Path]:
    return sorted(p for p in MODULES_DIR.iterdir() if p.is_dir() and (p / '__init__.py').exists())


def _sql_strings(tree: ast.AST) -> list[str]:
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if _SQL_START.match(node.value):
                out.append(node.value)
    return out


def tables_in_sql(sql: str) -> set[str]:
    sql = re.sub(r'\bDO\s+UPDATE\b', 'DO NOTHING_UPDATE', sql, flags=re.I)  # upsert clause, not a table
    ctes = {m.group(1).lower() for m in _CTE.finditer(sql)}
    found = set()
    for m in _TABLE_REF.finditer(sql):
        keyword, name, paren = m.group(1).upper(), m.group(2).lower(), m.group(3)
        if paren and keyword in ('FROM', 'JOIN'):
            continue  # table-valued function, e.g. json_each(...)
        if name in ctes or name in ('select', 'set', 'values'):
            continue
        found.add(name)
    return found


def repository_tables(path: Path) -> set[str]:
    tables: set[str] = set()
    for sql in _sql_strings(ast.parse(path.read_text(encoding='utf-8'))):
        tables |= tables_in_sql(sql)
    return tables


def cross_module_imports(path: Path, own: str) -> list[tuple[str, str]]:
    """(other module, submodule or '') for every import in `path` that targets another module of the package."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    # dotted package of this file, relative to `app`: app.modules.<own>
    results: list[tuple[str, str]] = []

    def record(dotted: str, names: list[str]) -> None:
        parts = dotted.split('.')
        if parts[:2] != ['app', 'modules'] or len(parts) < 3:
            return
        mod = parts[2]
        if mod == own:
            return
        if len(parts) > 3:
            results.append((mod, parts[3]))
        else:  # `from app.modules.x import api as x_api` or `from app.modules import x`
            results.extend((mod, n) for n in names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                record(alias.name, [])
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            if node.level:
                # level 1 = own package; level 2 = app.modules; level 3 = app
                pkg = ['app', 'modules', own][: max(0, 4 - node.level)]
                dotted = '.'.join(pkg + ([node.module] if node.module else []))
            else:
                dotted = node.module or ''
            if dotted == 'app.modules':
                for n in names:
                    results.append((n, ''))
            else:
                record(dotted, names)
    return results


@pytest.mark.parametrize('module', sorted(OWNED_TABLES))
def test_repository_only_touches_owned_tables(module: str) -> None:
    repo = MODULES_DIR / module / 'repository.py'
    if not repo.exists():
        pytest.skip(f'{module} has no repository.py')
    foreign = repository_tables(repo) - OWNED_TABLES[module]
    assert not foreign, f'{module}/repository.py touches tables it does not own: {sorted(foreign)}'


def test_every_module_is_declared() -> None:
    assert {p.name for p in _module_dirs()} <= set(OWNED_TABLES), 'new module missing from OWNED_TABLES'


def test_checkout_and_legacy_have_no_repository() -> None:
    assert not (MODULES_DIR / 'checkout' / 'repository.py').exists()
    assert not (MODULES_DIR / 'legacy' / 'repository.py').exists()


def test_modules_import_each_other_only_through_api() -> None:
    violations = []
    for mod_dir in _module_dirs():
        own = mod_dir.name
        for path in sorted(mod_dir.glob('*.py')):
            for other, sub in cross_module_imports(path, own):
                if sub in FORBIDDEN_LAYERS or (sub and sub != 'api' and f'{other}.{sub}' not in ALLOWED_CROSS_IMPORTS):
                    violations.append(f'{path.relative_to(MODULES_DIR)} imports {other}.{sub}')
    assert not violations, 'cross-module imports must go through api:\n' + '\n'.join(violations)


def test_sql_table_parser_examples() -> None:
    assert tables_in_sql('SELECT * FROM a x JOIN b ON 1 WHERE EXISTS (SELECT 1 FROM c)') == {'a', 'b', 'c'}
    assert tables_in_sql('INSERT INTO t (a) VALUES (1) ON CONFLICT(a) DO UPDATE SET a = 2') == {'t'}
    assert tables_in_sql('DELETE FROM d WHERE x = 1') == {'d'}
    assert tables_in_sql('UPDATE u SET a = 1') == {'u'}
    assert tables_in_sql('WITH w AS (SELECT 1) SELECT * FROM w JOIN json_each(?)') == set()
