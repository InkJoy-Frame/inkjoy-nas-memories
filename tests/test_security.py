"""Checks for the LAN manager's transport, session, database, and file rules."""

import base64
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix='inkjoy-security-')
os.environ['DATA_DIR'] = str(Path(_TMP) / 'data')
os.environ['IMAGES_DIR'] = str(Path(_TMP) / 'images')
os.environ['SECRET_KEY'] = 'test-secret-do-not-change'
os.environ.pop('TRUST_FORWARDED_PROTO', None)
Path(os.environ['DATA_DIR']).mkdir()
Path(os.environ['IMAGES_DIR']).mkdir()

import app as app_module  # noqa: E402
import database  # noqa: E402
from nacl.public import Box, PrivateKey, PublicKey  # noqa: E402
from transport_crypto import b64d, b64e, public_key_b64  # noqa: E402

from safe_files import (  # noqa: E402
    UnsafePath, directory_is_real, ensure_directory,
    iter_regular_files, list_directory, open_regular,
)


def _cookie_bytes(value):
    chunks = []
    for part in str(value).split('.'):
        pad = '=' * (-len(part) % 4)
        try:
            chunks.append(base64.urlsafe_b64decode(part + pad))
        except Exception:
            continue
    return b' '.join(chunks)


def _seal(obj, secret):
    nonce = os.urandom(24)
    server = PublicKey(b64d(public_key_b64()))
    raw = bytes(Box(secret, server).encrypt(json.dumps(obj).encode(), nonce))
    return {
        'v': 1,
        'pk': b64e(bytes(secret.public_key)),
        'n': b64e(raw[:24]),
        'c': b64e(raw[24:]),
    }


def _open_response(body, secret):
    env = json.loads(body)
    server = PublicKey(b64d(public_key_b64()))
    plain = Box(secret, server).decrypt(b64d(env['c']), b64d(env['n']))
    return json.loads(plain)


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app_module.app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()
        cls.images = Path(os.environ['IMAGES_DIR'])
        cls.data = Path(os.environ['DATA_DIR'])
        cls.calls = []

        import api_client

        def fake_login(self, email, password):
            cls.calls.append((self.server_url, email, password))
            if 'advisor' in self.server_url:
                raise Exception('no')
            return {'token': 'upstream-token'}

        def fake_devices(self):
            raise AssertionError('device list should not run for a rejected cookie')

        api_client.InkJoyClient.login = fake_login
        api_client.InkJoyClient.get_devices = fake_devices

    def setUp(self):
        self.calls.clear()

    def test_frame_options_on_login_static_and_api(self):
        for path in ('/login', '/static/js/i18n.js', '/api/devices'):
            resp = self.client.get(path)
            self.assertEqual(resp.headers.get('X-Frame-Options'), 'DENY', path)

    def test_http_rejects_plaintext_secrets(self):
        body = {'email': 'person@example.com', 'password': 's3cret', 'agreed': True}
        resp = self.client.post('/login', json=body)
        self.assertEqual(resp.status_code, 400)
        self.assertTrue('明文' in resp.get_json()['error'] or 'encrypted' in resp.get_json()['error'])
        self.assertEqual(self.calls, [])
        self.assertNotIn(b's3cret', resp.get_data())

        listed = self.client.get('/api/browse?device_id=device-1')
        self.assertEqual(listed.status_code, 400)
        self.assertNotIn(b'device-1', listed.get_data())

        spoofed = self.client.post(
            '/login', json=body, headers={'X-Forwarded-Proto': 'https'},
        )
        self.assertEqual(spoofed.status_code, 400)
        self.assertEqual(self.calls, [])

        form = self.client.post('/login', data={'email': 'person@example.com', 'password': 's3cret'})
        self.assertEqual(form.status_code, 400)
        nested = self.client.post('/login', json={'profile': {'email': 'person@example.com', 'password': 's3cret'}})
        self.assertEqual(nested.status_code, 400)
        self.assertEqual(self.calls, [])

    def test_https_uses_tls_without_a_second_encryption_layer(self):
        resp = self.client.post(
            '/login',
            json={'email': 'person@example.com', 'password': 's3cret'},
            base_url='https://nas.local',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue('同意' in resp.get_json()['error'] or 'agree' in resp.get_json()['error'].lower())
        self.assertEqual(self.calls, [])

        resp = self.client.post(
            '/login',
            json={'email': 'person@example.com', 'password': 's3cret', 'agreed': True},
            base_url='https://nas.local',
        )
        self.assertTrue(any(email == 'person@example.com' for _, email, _ in self.calls))
        self.assertEqual(self.calls[0][1], 'person@example.com')
        self.assertNotIn('v', resp.get_json())

    def test_http_sealed_login_hides_secrets_and_requires_agreement(self):
        secret = PrivateKey.generate()
        sealed = _seal(
            {'email': 'person@example.com', 'password': 's3cret', 'agreed': False},
            secret,
        )
        raw = json.dumps(sealed).encode()
        self.assertNotIn(b'person@example.com', raw)
        self.assertNotIn(b's3cret', raw)
        resp = self.client.post('/login', json=sealed)
        opened = _open_response(resp.get_data(), secret)
        self.assertTrue('同意' in opened['error'] or 'agree' in opened['error'].lower())
        self.assertEqual(self.calls, [])

        sealed = _seal(
            {'email': 'person@example.com', 'password': 's3cret', 'agreed': True},
            secret,
        )
        resp = self.client.post('/login', json=sealed)
        self.assertEqual(self.calls[0][1:], ('person@example.com', 's3cret'))
        cookie = self.client.get_cookie('session')
        blob = _cookie_bytes(cookie.value if cookie else '')
        self.assertNotIn(b'person@example.com', blob)
        self.assertNotIn(b's3cret', blob)

    def test_logout_rejects_the_old_cookie_without_logging_in_again(self):
        from database import activate_web_session, save_account
        account_id = save_account(
            'N', 'again@example.com', 'stored-password', 'https://openapi.example', 'tok-1',
        )
        version = activate_web_session(account_id)
        with self.client.session_transaction() as sess:
            sess['token'] = 'tok-1'
            sess['account_id'] = account_id
            sess['sv'] = version
        self.assertEqual(self.client.get('/').status_code, 200)
        saved = self.client.get_cookie('session').value
        self.client.get('/logout')
        self.client.set_cookie('session', saved)
        before = len(self.calls)
        page = self.client.get('/')
        api = self.client.get('/api/devices')
        self.assertEqual(page.status_code, 302)
        self.assertIn('/login', page.headers['Location'])
        self.assertEqual(api.status_code, 401)
        self.assertEqual(len(self.calls), before)
        self.assertFalse(hasattr(database, 'get_saved_account'))

    def test_database_file_is_encrypted_and_secrets_are_not_plaintext(self):
        db_path = self.data / 'inkjoy.db'
        self.assertFalse((self.data / 'field_key.bin').exists())
        key_file = self.data / 'transport_private.bin'
        self.assertTrue(key_file.exists())
        with self.assertRaises(sqlite3.DatabaseError) as caught:
            plain_db = sqlite3.connect(db_path)
            try:
                plain_db.execute('select 1')
            finally:
                plain_db.close()
        self.assertIn('not a database', str(caught.exception).lower())

        from database import get_account, save_account
        account_id = save_account(
            'N', 'stored@example.com', 'db-password', 'https://openapi.example', 'tok',
        )
        raw = db_path.read_bytes()
        self.assertNotIn(b'stored@example.com', raw)
        self.assertNotIn(b'db-password', raw)
        self.assertEqual(get_account(account_id)['email'], 'stored@example.com')

        plain = self.data / 'legacy.db'
        conn = sqlite3.connect(plain)
        conn.execute('create table t (email text)')
        conn.execute("insert into t values ('plain@example.com')")
        conn.commit()
        conn.close()
        self.assertTrue(database._is_plain_sqlite(str(plain)))
        database._migrate_plain_db(str(plain))
        self.assertFalse(database._is_plain_sqlite(str(plain)))
        with self.assertRaises(sqlite3.DatabaseError):
            migrated = sqlite3.connect(plain)
            try:
                migrated.execute('select email from t')
            finally:
                migrated.close()
        opened = database._connect.__wrapped__ if hasattr(database._connect, '__wrapped__') else None
        enc = __import__('sqlcipher3').dbapi2.connect(str(plain))
        database._apply_key(enc)
        self.assertEqual(enc.execute('select email from t').fetchone()[0], 'plain@example.com')
        enc.close()
        self.assertIsNone(opened)

    def test_legacy_field_key_file_is_migrated_off_disk(self):
        from nacl.secret import SecretBox
        from database import get_account, get_db, migrate_sensitive_fields
        from transport_crypto import init_transport

        legacy = os.urandom(32)
        token = bytes(SecretBox(legacy).encrypt(b'legacy@example.com'))
        stored = 'nacl1:' + b64e(token)
        field_path = self.data / 'field_key.bin'
        field_path.write_bytes(legacy)
        os.chmod(field_path, 0o600)
        conn = get_db()
        cur = conn.execute(
            'INSERT INTO accounts (name, email, password, server_url) VALUES (?,?,?,?)',
            ('L', stored, stored, 'https://openapi.example'),
        )
        account_id = cur.lastrowid
        conn.commit()
        conn.close()
        init_transport(str(self.data))
        migrate_sensitive_fields()
        self.assertFalse(field_path.exists())
        self.assertEqual(get_account(account_id)['email'], 'legacy@example.com')
        self.assertNotIn(b'legacy@example.com', (self.data / 'inkjoy.db').read_bytes())

    def test_symlink_is_not_listed_or_read(self):
        from PIL import Image
        pictures = self.images / 'photos'
        outside = Path(_TMP) / 'outside'
        pictures.mkdir()
        outside.mkdir()
        Image.new('RGB', (2, 2), (20, 30, 40)).save(pictures / 'ok.jpg', 'JPEG')
        canary = outside / 'secret.jpg'
        canary.write_bytes(b'SECRET-CANARY-CONTENT')
        (pictures / 'link.jpg').symlink_to(canary)
        (pictures / 'jump').symlink_to(outside)
        (pictures / 'inside.jpg').symlink_to('ok.jpg')

        names = [item['name'] for item in list_directory(self.images, 'photos')]
        self.assertIn('ok.jpg', names)
        self.assertNotIn('link.jpg', names)
        self.assertNotIn('jump', names)
        self.assertNotIn('inside.jpg', names)
        self.assertEqual(
            list(iter_regular_files(self.images, 'photos')),
            ['photos/ok.jpg'],
        )
        from scheduler_manager import _pick_random_image
        self.assertEqual(_pick_random_image(1, 'photos'), 'photos/ok.jpg')
        with self.assertRaises(Exception) as picked:
            _pick_random_image(1, 'photos/jump')
        self.assertIn('非法', str(picked.exception))
        with self.assertRaises(UnsafePath):
            ensure_directory(self.images, 'photos/jump/created')
        self.assertFalse((outside / 'created').exists())
        with self.assertRaises(UnsafePath):
            open_regular(self.images, 'photos/link.jpg')
        self.assertTrue(directory_is_real(self.images, 'photos'))
        self.assertFalse(directory_is_real(self.images, 'photos/missing'))

        from database import activate_web_session, save_account
        account_id = save_account(
            'N', 'files@example.com', 'pw', 'https://openapi.example', 'tok-files',
        )
        version = activate_web_session(account_id)
        with self.client.session_transaction() as sess:
            sess['token'] = 'tok-files'
            sess['account_id'] = account_id
            sess['sv'] = version
            sess['server_url'] = 'https://openapi.example'
        secret = PrivateKey.generate()
        headers = {'X-Inkjoy-Pk': b64e(bytes(secret.public_key))}
        listing = self.client.get('/api/browse?path=photos', headers=headers)
        self.assertEqual(listing.headers.get('X-Frame-Options'), 'DENY')
        listed = _open_response(listing.get_data(), secret)
        listed_names = [item['name'] for item in listed['items']]
        self.assertEqual(listed_names, ['ok.jpg'])
        self.assertNotIn(b'SECRET-CANARY-CONTENT', listing.get_data())

        blocked = self.client.get('/api/image?path=photos/link.jpg')
        self.assertEqual(blocked.status_code, 400)
        self.assertNotIn(b'SECRET-CANARY-CONTENT', blocked.get_data())
        self.assertEqual(blocked.headers.get('X-Frame-Options'), 'DENY')

        image = self.client.get('/api/image?path=photos/ok.jpg')
        self.assertEqual(image.status_code, 200)
        self.assertTrue(image.data.startswith(b'\xff\xd8'))

    def test_accounts_response_does_not_leak_email_on_http(self):
        from database import activate_web_session, save_account
        account_id = save_account(
            'N', 'hidden@example.com', 'hidden-password', 'https://openapi.example', 'tok-h',
        )
        version = activate_web_session(account_id)
        with self.client.session_transaction() as sess:
            sess['token'] = 'tok-h'
            sess['account_id'] = account_id
            sess['sv'] = version
        secret = PrivateKey.generate()
        resp = self.client.get(
            '/api/accounts',
            headers={'X-Inkjoy-Pk': b64e(bytes(secret.public_key))},
        )
        raw = resp.get_data()
        self.assertNotIn(b'hidden@example.com', raw)
        self.assertNotIn(b'hidden-password', raw)
        opened = _open_response(raw, secret)
        emails = [row['email'] for row in opened['accounts']]
        self.assertIn('hidden@example.com', emails)


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        from scheduler_manager import scheduler
        if scheduler.running:
            scheduler.shutdown(wait=False)
