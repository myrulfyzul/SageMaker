"""Property 53: Seed reset confirmation.

For any input other than the exact confirmation word, ``seed --reset`` deletes nothing, changes nothing and exits
with the reset-cancelled message.

**Validates: Requirements 29.7, 29.9, 29.12**
"""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import seed  # noqa: E402
from app.db import connect  # noqa: E402


def _snapshot(path):
    conn = connect(path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: [tuple(r) for r in conn.execute(f'SELECT * FROM "{n}" ORDER BY 1')] for n in names}
    finally:
        conn.close()


@pytest.fixture(scope='module')
def seeded():
    root = Path(tempfile.mkdtemp(prefix='sagemaker_prop_seed_'))
    env = {'DATABASE_PATH': str(root / 'seed.sqlite3')}
    assert seed.main([], environ=env) == seed.EXIT_OK
    yield env, _snapshot(root / 'seed.sqlite3')
    shutil.rmtree(root, ignore_errors=True)


# Any text, EOF (None) and near misses of the exact word.
answers = st.one_of(
    st.none(),
    st.text(max_size=30).filter(lambda s: s != seed.RESET_WORD),
    st.sampled_from([seed.RESET_WORD.lower(), seed.RESET_WORD + ' ', ' ' + seed.RESET_WORD, seed.RESET_WORD[:-1],
                     seed.RESET_WORD + '\n', 'RESET_DEMO', 'reset demo', '']),
)


@settings(max_examples=25, deadline=None)
@given(answer=answers)
def test_reset_only_proceeds_for_exact_word(seeded, answer):
    env, before = seeded

    def ask(_prompt):
        if answer is None:
            raise EOFError
        return answer

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = seed.main(['--reset'], environ=env, input_fn=ask)
    assert code == seed.EXIT_CANCELLED
    assert seed.MSG_CANCELLED in err.getvalue()
    assert _snapshot(Path(env['DATABASE_PATH'])) == before
