"""Property 9: Access control matrix.

For any endpoint in the route table, for any Role (including no session, an expired token and a revoked token) and
for any request, the response status is 401 when the session is missing, malformed, expired or revoked, 403 when the
Role is not permitted, and the permitted outcome otherwise; every 401 or 403 leaves the database unchanged and
returns no protected data.

The route table is read from the app's OpenAPI document. Every (method, path) must match a rule in `RULES`, so a new
route without a permission entry fails `test_every_route_has_a_permission_entry`.

**Validates: Requirements 6.1, 6.2, 6.4, 6.5, 6.7, 6.8, 10.6, 20.10, 23.8, 33.1**
"""
from __future__ import annotations

import itertools
import re
import shutil
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db, security
from app.config import Settings
from app.main import create_app
from app.time_utils import utc_now

PASSWORD = ''.join(['Secret', '123'])
PROFILE = dict(max_examples=400, deadline=None, suppress_health_check=list(HealthCheck))

ROLES = ['visitor', 'customer', 'seller', 'admin', 'artisan']
STAFF = frozenset({'seller', 'admin'})
CUSTOMER = frozenset({'customer'})
ADMIN = frozenset({'admin'})
NOTIFY = frozenset({'customer', 'seller', 'admin'})
PRODUCTION = frozenset({'seller', 'admin', 'artisan'})
ANY_SESSION = frozenset(ROLES) - {'visitor'}

# Staff: all jobs. Artisan: only jobs assigned to their profile, so an unknown or unassigned job is 403.
PRODUCTION_JOB = 'production_job'

OPEN = 'open'                  # no session dependency: Bearer header is ignored
OPTIONAL = 'optional'          # visitor allowed; a present but invalid token is rejected (deps.optional_session)
LEGACY_ORDER = 'legacy_order'  # guarded by X-Order-Token, independent of sessions
LEGACY_ADMIN = 'legacy_admin'  # guarded by X-Admin-Key, independent of sessions

# (regex over "METHOD /path/template", kind or allowed-role set). First match wins.
RULES: list[tuple[str, object]] = [
    # Legacy routes (separate credentials; design: unchanged legacy API).
    (r'^GET /api/legacy/products$', OPEN),
    (r'^POST /api/legacy/orders$', OPEN),
    (r'^GET /api/legacy/orders/\{order_id\}$', LEGACY_ORDER),
    (r'^PATCH /api/legacy/admin/', LEGACY_ADMIN),
    # Public group: health, catalogue read, home sections, public artisan, register, login.
    (r'^GET /api/health$', OPEN),
    (r'^POST /api/auth/(register|login)$', OPEN),
    (r'^GET /api/categories$', OPEN),
    (r'^GET /api/products$', OPEN),
    (r'^GET /api/products/\{product_id\}$', OPTIONAL),
    (r'^GET /api/home/(best-sellers|new-arrivals)$', OPEN),
    (r'^GET /api/home/recommendations$', OPTIONAL),
    (r'^GET /api/artisans(/\{artisan_id\})?$', OPEN),
    # Any authenticated session.
    (r'^POST /api/auth/logout$', ANY_SESSION),
    (r'^GET /api/auth/session$', ANY_SESSION),
    (r'^GET /api/media/', ANY_SESSION),  # owner or staff is decided per resource (404 for others)
    # Admin only.
    (r'^(PATCH|POST) /api/users/', ADMIN),
    # Notifications (own): customer, seller, admin.
    (r'^(GET|POST) /api/notifications', NOTIFY),
    # Order payments list: owner customer or staff.
    (r'^GET /api/orders/\{order_id\}/payments$', NOTIFY),
    # Production jobs: staff create/assign/status; staff and artisan read and record progress.
    (r'^GET /api/production/jobs$', PRODUCTION),
    (r'^(GET /api/production/jobs/\{job_id\}|POST /api/production/jobs/\{job_id\}/progress)$', PRODUCTION_JOB),
    (r'^(POST|PUT|PATCH|DELETE|GET) /api/production/', STAFF),
    # Staff area.
    (r'^[A-Z]+ /api/staff/', STAFF),
    # Customer-only: profile, addresses, favourites, cart, checkout, own orders/payments, own custom orders.
    (r'^[A-Z]+ /api/(me|favourites|cart|checkout|custom-orders)', CUSTOMER),
    # Hosted-gateway payments: the config is public; starting, reading and cancelling a payment is customer-only.
    # (The Stripe webhook and return page are not in the OpenAPI document; the webhook is signature-checked.)
    (r'^GET /api/payments/config$', OPEN),
    (r'^(GET|POST) /api/payments/sessions(/\{session_id\}(/cancel)?)?$', CUSTOMER),
    (r'^(GET|POST) /api/orders(/\{order_id\}(/payments)?)?$', CUSTOMER),
]

_counter = itertools.count()


def policy_for(method: str, path: str):
    key = f'{method} {path}'
    for pattern, policy in RULES:
        if re.search(pattern, key):
            return policy
    return None


def route_table(app) -> list[tuple[str, str]]:
    return sorted((m.upper(), p) for p, ops in app.openapi()['paths'].items() for m in ops)


def concrete(path: str) -> str:
    return re.sub(r'\{[^}]+\}', '999999', path)


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='accessmatrix_'))
        self.db_path = self.dir / 't.sqlite3'
        settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.app = create_app(settings)
        self.cm = TestClient(self.app, raise_server_exceptions=False)
        self.client = self.cm.__enter__()
        self.user_ids: dict[str, int] = {}
        for role in ROLES[1:]:
            email = f'{role}{next(_counter)}@example.com'
            r = self.client.post('/api/auth/register', json={'name': role, 'email': email, 'password': PASSWORD})
            assert r.status_code == 201, r.text
            self.sql('UPDATE users SET role = ? WHERE email = ?', (role, email))
            self.user_ids[role] = self.sql('SELECT id FROM users WHERE email = ?', (email,))[0][0]
        self.routes = route_table(self.app)

    def sql(self, query, params=()):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def session(self, role: str, state: str) -> str | None:
        """Insert a session row of the requested state; returns the bearer token."""
        if state == 'missing':
            return None
        if state == 'malformed':
            return 'malformed token with spaces'
        if state == 'unknown':
            return security.new_token()
        token = security.new_token()
        now = utc_now()
        expires = now - timedelta(hours=1) if state == 'expired' else now + timedelta(hours=1)
        revoked = now.isoformat() if state == 'revoked' else None
        self.sql('INSERT INTO sessions (user_id, token_hash, created_at, expires_at, revoked_at) VALUES (?,?,?,?,?)',
                 (self.user_ids[role], security.hash_token(token), (now - timedelta(hours=2)).isoformat(),
                  expires.isoformat(), revoked))
        return token

    def snapshot(self) -> dict[str, list]:
        conn = sqlite3.connect(self.db_path)
        try:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                 "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {t: conn.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall() for t in tables}
        finally:
            conn.close()

    def close(self):
        self.cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env: _Env | None = None


def _get_env() -> _Env:
    global _env
    if _env is None:
        _env = _Env()
    return _env


def teardown_module(_module):
    global _env
    if _env is not None:
        _env.close()
        _env = None


def expected(policy, role: str, state: str) -> str:
    """Return 'allowed', '401', '403' for the given policy, role and token state."""
    if policy == LEGACY_ORDER:
        return '401'   # no X-Order-Token sent
    if policy == LEGACY_ADMIN:
        return '403'   # no X-Admin-Key sent, whatever the session role
    if policy == OPEN:
        return 'allowed'
    has_session = state == 'valid'
    if not has_session:
        if policy == OPTIONAL and state == 'missing':
            return 'allowed'
        return '401'
    if policy == OPTIONAL:
        return 'allowed'
    if policy == PRODUCTION_JOB:
        return '403' if role == 'artisan' else ('allowed' if role in STAFF else '403')
    return 'allowed' if role in policy else '403'


def send(env: _Env, method: str, path: str, token: str | None):
    headers = {'Authorization': f'Bearer {token}'} if token is not None else {}
    kwargs = {'headers': headers}
    if method not in ('GET', 'DELETE'):
        # The legacy admin route checks its key inside the handler, after body validation.
        kwargs['json'] = {}
        if '/legacy/admin/' in path:
            kwargs['json'] = {'status': 'shipped'}
        elif path.endswith('/progress'):
            kwargs['json'] = {'percent': 50}  # ownership is checked after body validation
    return env.client.request(method, concrete(path), **kwargs)


@st.composite
def requests(draw):
    env = _get_env()
    method, path = draw(st.sampled_from(env.routes))
    role = draw(st.sampled_from(ROLES))
    if role == 'visitor':
        state = draw(st.sampled_from(['missing', 'malformed', 'unknown']))
    else:
        state = draw(st.sampled_from(['valid', 'valid', 'valid', 'missing', 'malformed', 'unknown', 'expired',
                                      'revoked']))
    return method, path, role, state


def test_every_route_has_a_permission_entry():
    env = _get_env()
    assert len(env.routes) > 60
    missing = [f'{m} {p}' for m, p in env.routes if policy_for(m, p) is None]
    assert not missing, f'routes without a permission entry: {missing}'


@hsettings(**PROFILE)
@given(requests())
def test_access_matrix(req):
    method, path, role, state = req
    env = _get_env()
    policy = policy_for(method, path)
    assert policy is not None
    token = env.session(role, state)
    before = env.snapshot()
    r = send(env, method, path, token)
    outcome = expected(policy, role, state)
    label = f'{method} {path} role={role} token={state} -> {r.status_code} {r.text[:200]}'
    if outcome == 'allowed':
        assert r.status_code not in (401, 403), label
        assert r.status_code < 500, label
        return
    assert r.status_code == int(outcome), label
    body = r.json()
    assert set(body) == {'error'}, label                      # no protected data, only the error envelope
    code = body['error']['code']
    if outcome == '401':
        assert code == ('session_expired' if state == 'expired' and policy not in (LEGACY_ORDER,) else code), label
        assert code in ('unauthenticated', 'session_expired'), label
    else:
        assert code == 'forbidden' or policy == LEGACY_ADMIN, label
    assert env.snapshot() == before, label                    # 401/403 leave the database unchanged


def test_artisan_is_not_allowed_on_staff_production_actions_and_may_read_jobs():
    env = _get_env()
    token = env.session('artisan', 'valid')
    for method, path in [('POST', '/api/production/jobs'), ('POST', '/api/production/jobs/1/assign'),
                         ('POST', '/api/production/jobs/1/status')]:
        assert send(env, method, path, token).status_code == 403, path
    assert send(env, 'GET', '/api/production/jobs', token).status_code == 200


def test_artisan_reads_only_jobs_assigned_to_their_profile():
    from app.modules.artisans import api as artisans_api
    from app.modules.production import repository as production_repo

    env = _get_env()
    staff = env.session('seller', 'valid')
    artisan_ids = []
    for name in ('Own maker', 'Other maker'):
        r = env.client.post('/api/staff/artisans', json={'name': name, 'specialisation': 'Batik',
                                                         'availability': 'available'},
                            headers={'Authorization': f'Bearer {staff}'})
        assert r.status_code == 201, r.text
        artisan_ids.append(r.json()['id'])
    conn = db.connect(env.db_path)
    try:
        with db.transaction(conn):
            artisans_api.link_user(conn, artisan_ids[0], env.user_ids['artisan'])
            jobs = []
            for artisan_id in artisan_ids:
                job_id = production_repo.insert(conn, {'quantity': 1}, 'now')
                conn.execute('UPDATE production_jobs SET artisan_id = ? WHERE id = ?', (artisan_id, job_id))
                jobs.append(job_id)
    finally:
        conn.close()
    token = env.session('artisan', 'valid')
    headers = {'Authorization': f'Bearer {token}'}
    assert env.client.get(f'/api/production/jobs/{jobs[0]}', headers=headers).status_code == 200
    assert env.client.get(f'/api/production/jobs/{jobs[1]}', headers=headers).status_code == 403
