"""Migration CLI: `python -m backend.migrate [status|up]` (or `python migrate.py ...` in backend/)."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import ConfigError, Settings  # noqa: E402
from app.migrations.runner import MigrationError, get_status, run_migrations  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else 'status'
    if command not in ('status', 'up') or len(args) > 1:
        print('Usage: python -m backend.migrate [status|up]', file=sys.stderr)
        return 2
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        if command == 'status':
            status = get_status(settings.database_path)
            print(f'Applied: {", ".join(status.applied) or "(none)"}')
            print(f'Pending: {", ".join(status.pending) or "(none)"}')
        else:
            applied = run_migrations(settings.database_path)
            print(f'Applied: {", ".join(applied)}' if applied else 'Nothing to apply')
    except MigrationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
