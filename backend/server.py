"""Compatibility shim for the original single-file demo server.

Run: pip install -r backend/requirements.txt
     python backend/server.py

The implementation now lives in the `app` package (legacy routes under /api/legacy).
Only demo payments are implemented. No real cards, transactions, or couriers.
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Prototype defaults, preserved from the original server.
os.environ.setdefault('SAGEMAKER_DEMO_DB', str(BACKEND_DIR / 'demo_orders.sqlite3'))
os.environ.setdefault('DEMO_MODE', '1')
os.environ.setdefault('ALLOWED_ORIGINS', 'http://localhost:5353,http://127.0.0.1:5353')

from app.main import application as app  # noqa: E402
from app.migrations.runner import run_migrations  # noqa: E402

# The original server created its schema at import time; keep that (idempotent).
run_migrations(app.state.settings.database_path)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
