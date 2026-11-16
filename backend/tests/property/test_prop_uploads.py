"""Property 41: Upload validation.

**Validates: Requirements 16.2, 16.3, 20.5, 20.6, 33.3, 33.4**

An upload is accepted iff the extension is .jpg/.jpeg/.png/.webp, the content signature matches the same type
and the size is at most 5 MB. A rejected upload stores no file and no database row and gives a reason.
(The custom-order upload endpoint does not exist yet; the 5-file cap is not covered here.)
"""
from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app import db, uploads
from app.errors import ValidationFailed
from app.modules.users import api as users_api
from app.security import hash_password

LIMIT = 5 * 1024 * 1024
PASSWORD = ''.join(['Secret', '123'])

SIGNATURES = {
    'jpeg': b'\xff\xd8\xff',
    'png': b'\x89PNG\r\n\x1a\n',
    'webp': b'RIFF\x00\x00\x00\x00WEBP',
}
EXT_KIND = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.png': 'png', '.webp': 'webp'}

stems = st.text(alphabet='abcdefXYZ019_-', min_size=1, max_size=12)
extensions = st.sampled_from(['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.PnG', '.WEBP',
                              '.gif', '.bmp', '.svg', '.php', '.exe', '.txt', '.png.php', '.pngx', ''])
filenames = st.builds(lambda s, e: s + e, stems, extensions)


@st.composite
def contents(draw, small=True):
    """Bytes with a valid signature (any type), a random/garbage prefix, or empty; sizes near the limit sometimes."""
    kind = draw(st.sampled_from(['jpeg', 'png', 'webp', 'none', 'empty']))
    if kind == 'empty':
        return b''
    head = SIGNATURES.get(kind) or draw(st.binary(min_size=1, max_size=16))
    if small:
        pad = draw(st.integers(0, 64))
    else:
        pad = draw(st.sampled_from([0, 10, LIMIT - len(head) - 1, LIMIT - len(head), LIMIT - len(head) + 1]))
    return head + b'0' * pad


def expected_accept(name: str, data: bytes) -> bool:
    ext = ('.' + name.rsplit('.', 1)[1].lower()) if '.' in name else ''
    if ext not in EXT_KIND or len(data) > LIMIT or not data:
        return False
    if data.startswith(SIGNATURES['jpeg']):
        sig = 'jpeg'
    elif data.startswith(SIGNATURES['png']):
        sig = 'png'
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        sig = 'webp'
    else:
        sig = None
    return sig == EXT_KIND[ext]


@settings(max_examples=150, deadline=None)
@given(name=filenames, data=contents(small=False))
def test_validate_image_accepts_iff_rules_hold(name, data):
    if expected_accept(name, data):
        result = uploads.validate_image(name, data)
        assert EXT_KIND[result] == EXT_KIND[name[name.rindex('.'):].lower()]
    else:
        with pytest.raises(ValidationFailed) as exc:
            uploads.validate_image(name, data)
        assert exc.value.status == 422
        assert exc.value.details  # a reason is given


@pytest.fixture()
def staff(client, settings):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='U', email='seller@example.com',
                              password_hash=hash_password(PASSWORD), role='seller')
    conn.close()
    token = client.post('/api/auth/login', json={'email': 'seller@example.com', 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def _stored_files(media_dir):
    if not media_dir.exists():
        return set()
    return {p.name for p in media_dir.rglob('*') if p.is_file()}


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(name=filenames, data=contents(small=False))
def test_staff_image_endpoint_accepts_iff_rules_hold(client, settings, staff, name, data):
    pid = _product_id(client, staff)
    url = f'/api/staff/products/{pid}/images'
    before_files = _stored_files(settings.media_dir)
    before_images = len(client.get(f'/api/staff/products/{pid}', headers=staff).json()['images'])

    r = client.post(url, files={'file': (name, data, 'application/octet-stream')}, headers=staff)

    after_files = _stored_files(settings.media_dir)
    after_images = len(client.get(f'/api/staff/products/{pid}', headers=staff).json()['images'])
    if expected_accept(name, data):
        assert r.status_code == 201
        assert after_images == before_images + 1
        assert len(after_files - before_files) == 1
    else:
        assert r.status_code == 422
        err = r.json()['error']
        assert err['code'] and err['message']
        assert after_images == before_images
        assert after_files == before_files


_PRODUCT_CACHE: dict = {}


def _product_id(client, staff):
    key = id(client)
    if key not in _PRODUCT_CACHE:
        body = {'name': 'Tote', 'description': 'Nice', 'categoryId': 1, 'priceSen': 3000, 'stock': 10}
        _PRODUCT_CACHE[key] = client.post('/api/staff/products', json=body, headers=staff).json()['id']
    return _PRODUCT_CACHE[key]
