"""Repository secret scan (Requirements 1.9, 1.10).

Scans lib/, assets/, backend/ and root config files for hard-coded passwords,
admin keys and tokens. Any match fails the test. Secrets must be read from the
environment (os.environ / os.getenv / String.fromEnvironment) or be clearly empty
placeholders. Test fixtures must generate their secret values at runtime.
"""
import re
import secrets
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
THIS_FILE = Path(__file__).resolve()
SCAN_DIRS = ('lib', 'assets', 'backend')
SKIP_DIRS = {'node_modules', 'venv', '.venv', 'env', '.git', 'build', '__pycache__',
             '.dart_tool', '.hypothesis', '.pytest_cache', '.idea', '.vscode'}
SKIP_SUFFIXES = {'.sqlite', '.sqlite3', '.db', '.bak', '.pyc', '.png', '.jpg', '.jpeg',
                 '.gif', '.webp', '.ico', '.pdf', '.ttf', '.otf', '.woff', '.woff2', '.zip'}
TEXT_SUFFIXES = {'.py', '.dart', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.txt',
                 '.env', '.properties', '.sh', '.ps1', '.js', '.html', '.example'}
KV_SUFFIXES = {'.yaml', '.yml', '.toml', '.ini', '.cfg', '.properties', '.env', '.example'}
MAX_BYTES = 1_000_000

KEYWORDS = r'(?:password|passwd|pwd|secret|token|api_?key|admin_?key|private_?key|access_?key|auth_?key)'
# Names that merely describe a secret (lifetimes, header names, paths) are not secrets.
HARMLESS_NAME = re.compile(r'(?:lifetime|ttl|expir|seconds|length|header|name|path|url|field|type|prefix|label|hint)',
                           re.I)
# name = "literal"  /  name: 'literal'  (quoted literal; the name may not follow a hyphen,
# so header names such as X-Order-Token are not treated as variables).
QUOTED = re.compile(r'(?<![-\w])(?P<name>\w*' + KEYWORDS + r'\w*)["\']?\s*[:=]\s*[rbfu]{0,2}'
                    r'(?P<q>["\'])(?P<value>[^"\'\n]*)(?P=q)', re.I)
# NAME=value / name: value without quotes (env, yaml, ini files only).
UNQUOTED = re.compile(r'^\s*(?P<name>[\w.\-]*' + KEYWORDS + r'[\w.\-]*)\s*[:=]\s*(?P<value>[^#\n]*)', re.I)
# A literal X-Admin-Key header value.
ADMIN_HEADER = re.compile(r'x-admin-key["\']?\s*[:=]\s*(?P<q>["\'])(?P<value>[^"\'\n]*)(?P=q)', re.I)
KNOWN_FORMATS = [
    ('bearer token', re.compile(r'Bearer\s+(?![\w$<{(]*(?:token|key|secret))[A-Za-z0-9._~+/=-]{16,}')),
    ('private key block', re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')),
    ('aws access key', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('github token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b')),
    ('stripe live key', re.compile(r'\b[sr]k_live_[A-Za-z0-9]{10,}')),
    ('slack token', re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}')),
    ('jwt', re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{5,}')),
]
ENV_READ = re.compile(r'os\.environ|os\.getenv|\.fromEnvironment|environ\.get|\benv\.get\(|process\.env', re.I)
PLACEHOLDER = re.compile(
    r'^(?:<.*>|\$.*|\{.*|%.*|x{3,}|\*{3,}|\.{3,}|changeme|change-me|todo|none|null|'
    r'your[-_ ].*|.*placeholder.*|replace[-_ ].*|.*example.*)$', re.I)


def is_allowed_value(value: str) -> bool:
    """Empty values, placeholders and interpolations are not hard-coded secrets."""
    v = value.strip().strip('"\'').strip()
    return v == '' or '{' in v or '$' in v or bool(PLACEHOLDER.match(v))


def scan_text(text: str, kv_style: bool = False):
    """Return a list of (line_number, reason) for suspicious lines."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if ENV_READ.search(line):
            continue
        for m in QUOTED.finditer(line):
            if not HARMLESS_NAME.search(m.group('name')) and not is_allowed_value(m.group('value')):
                found.append((number, f"hard-coded value for '{m.group('name')}'"))
        for m in ADMIN_HEADER.finditer(line):
            if not is_allowed_value(m.group('value')):
                found.append((number, 'hard-coded X-Admin-Key value'))
        if kv_style:
            m = UNQUOTED.match(line)
            if (m and not HARMLESS_NAME.search(m.group('name'))
                    and not is_allowed_value(m.group('value')) and not QUOTED.search(line)):
                found.append((number, f"hard-coded value for '{m.group('name')}'"))
        for label, pattern in KNOWN_FORMATS:
            if pattern.search(line):
                found.append((number, f'embedded {label}'))
    return found


def _is_text_candidate(path: Path) -> bool:
    if path.resolve() == THIS_FILE or path.suffix.lower() in SKIP_SUFFIXES:
        return False
    if path.stat().st_size > MAX_BYTES:
        return False
    name = path.name.lower()
    return name.startswith('.env') or path.suffix.lower() in TEXT_SUFFIXES


def iter_scan_files(root: Path):
    for directory in SCAN_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob('*'):
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
                continue
            if path.is_file() and _is_text_candidate(path):
                yield path
    for path in root.iterdir():  # root-level config files (pubspec.yaml, .env*, ...)
        if path.is_file() and _is_text_candidate(path):
            yield path


def scan_repository(root: Path):
    matches = []
    for path in iter_scan_files(root):
        kv = path.suffix.lower() in KV_SUFFIXES or path.name.lower().startswith('.env')
        text = path.read_text(encoding='utf-8', errors='ignore')
        for number, reason in scan_text(text, kv_style=kv):
            matches.append(f'{path.relative_to(root).as_posix()}:{number}: {reason}')
    return matches


def test_repository_has_no_hard_coded_secrets():
    matches = scan_repository(REPO_ROOT)
    assert matches == [], 'Hard-coded secrets found (read them from the environment):\n' + '\n'.join(matches)


def test_scan_covers_expected_locations():
    files = {p.relative_to(REPO_ROOT).as_posix() for p in iter_scan_files(REPO_ROOT)}
    assert 'pubspec.yaml' in files
    assert 'backend/.env.example' in files
    assert any(f.startswith('lib/') for f in files)
    assert any(f.startswith('backend/app/') for f in files)
    assert 'backend/tests/unit/test_secret_scan.py' not in files
    assert not any(f.endswith(('.sqlite3', '.bak')) or '__pycache__' in f for f in files)


# --- the detector itself: planted values are built at runtime, never stored as literals ---
@pytest.mark.parametrize('template,kv', [
    ("password = '{v}'", False),
    ("ADMIN_KEY = \"{v}\"", False),
    ("headers = {{'X-Admin-Key': '{v}'}}", False),
    ("const token = '{v}';", False),
    ("SAGEMAKER_ADMIN_KEY={v}", True),
    ("api_key: {v}", True),
    ("Authorization: 'Bearer {v}'", False),
])
def test_detector_flags_planted_secrets(template, kv):
    planted = template.format(v=secrets.token_hex(12))
    assert scan_text(planted, kv_style=kv), planted


@pytest.mark.parametrize('line,kv', [
    ("key = os.environ.get('SAGEMAKER_ADMIN_KEY', '')", False),
    ("legacy_admin_key=env.get('SAGEMAKER_ADMIN_KEY', '')", False),
    ("password = ''", False),
    ("SAGEMAKER_ADMIN_KEY=", True),
    ("SAGEMAKER_ADMIN_KEY=<your-admin-key>", True),
    ("TOKEN_LIFETIME_SECONDS=604800", True),
    ("CORS_HEADERS = ['Content-Type', 'X-Order-Token', 'X-Admin-Key']", False),
    ("headers={'X-Order-Token': saved.token}", False),
    ("headers={'X-Admin-Key': key}", False),
    ("final token = const String.fromEnvironment('TOKEN');", False),
    ("password = f'{value}'", False),
])
def test_detector_allows_env_reads_and_placeholders(line, kv):
    assert scan_text(line, kv_style=kv) == []


def test_scan_repository_fails_on_planted_file(tmp_path):
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'lib' / 'bad.dart').write_text(f"const adminKey = '{secrets.token_hex(12)}';\n")
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'ignored.py').write_text(f"password = '{secrets.token_hex(12)}'\n")
    matches = scan_repository(tmp_path)
    assert len(matches) == 1 and matches[0].startswith('lib/bad.dart:1')
