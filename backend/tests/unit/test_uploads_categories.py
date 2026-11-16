"""Upload validation and GET /api/categories (Req 9.13, 20.5, 20.6, 33.3, 33.4)."""
from __future__ import annotations

import io

import pytest

from app import uploads
from app.errors import ValidationFailed

JPEG = b'\xff\xd8\xff\xe0' + b'0' * 20
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 20
WEBP = b'RIFF\x00\x00\x00\x00WEBP' + b'0' * 20


@pytest.mark.parametrize('name,data,ext', [
    ('a.jpg', JPEG, '.jpg'), ('a.JPEG', JPEG, '.jpg'), ('a.png', PNG, '.png'), ('a.webp', WEBP, '.webp'),
])
def test_valid_images(name, data, ext):
    assert uploads.validate_image(name, data) == ext


@pytest.mark.parametrize('name,data', [
    ('a.gif', JPEG), ('a', JPEG), ('a.png', JPEG), ('a.jpg', PNG), ('a.webp', PNG), ('a.png', b''),
    ('a.png', b'<script>'), ('a.php.png', b'<?php'),
])
def test_rejected_images(name, data):
    with pytest.raises(ValidationFailed):
        uploads.validate_image(name, data)


def test_size_limit_boundary():
    ok = PNG + b'0' * (uploads.MAX_IMAGE_BYTES - len(PNG))
    assert uploads.validate_image('a.png', ok) == '.png'
    with pytest.raises(ValidationFailed) as exc:
        uploads.validate_image('a.png', ok + b'0')
    assert exc.value.status == 422


def test_read_limited_reads_at_most_limit_plus_one():
    stream = io.BytesIO(b'0' * (uploads.MAX_IMAGE_BYTES + 100))
    assert len(uploads.read_limited(stream)) == uploads.MAX_IMAGE_BYTES + 1


def test_store_image_uses_uuid_name_and_leaves_no_temp(tmp_path):
    name = uploads.store_image(tmp_path, PNG, '.png')
    assert len(name) == 32 + 4 and name.endswith('.png')
    assert (tmp_path / name).read_bytes() == PNG
    assert list((tmp_path / '.tmp').iterdir()) == []
    assert uploads.store_image(tmp_path, PNG, '.png') != name


def test_categories_endpoint(client):
    res = client.get('/api/categories')
    assert res.status_code == 200
    assert [c['slug'] for c in res.json()] == ['tote-bags', 'fabric-books', 'toys', 'gifts', 'accessories']
    assert res.json()[0] == {'id': 1, 'slug': 'tote-bags', 'name': 'Tote bags'}
