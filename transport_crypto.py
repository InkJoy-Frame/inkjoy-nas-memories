"""Seal HTTP bodies on the LAN.

The NAS is opened at http://<lan-ip>:<port>. That origin is not a secure
context, so the page uses tweetnacl (X25519 + XSalsa20-Poly1305) instead of
Web Crypto. Only the public key is embedded in the page. The X25519 private
key stays in DATA_DIR.

HTTPS does not use this layer; TLS already covers the login, cookies, and
API calls. Field encryption uses a key derived from SECRET_KEY and is not
written into the data directory. Do not change SECRET_KEY after the first
successful start, or the existing database cannot be opened.
"""

import base64
import hashlib
import json
import os
import re
import threading

from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey
from nacl.secret import SecretBox

_lock = threading.Lock()
_private = None
_field_key = None
_legacy_field_key = None
_legacy_path = None
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')
_UUID_RE = re.compile(
    r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
)
_FIELD_PREFIX = 'nacl1:'


def install_secret():
    """Password from the install environment. Not stored beside the database."""
    return os.environ.get('SECRET_KEY') or 'inkjoy-manager-secret-change-this'


def _derive_field_key():
    return hashlib.pbkdf2_hmac(
        'sha256',
        install_secret().encode('utf-8'),
        b'inkjoy-nas-memories-field-v1',
        200000,
        dklen=SecretBox.KEY_SIZE,
    )


def init_transport(data_dir):
    global _private, _field_key, _legacy_field_key, _legacy_path
    os.makedirs(data_dir, exist_ok=True)
    box_path = os.path.join(data_dir, 'transport_private.bin')
    field_path = os.path.join(data_dir, 'field_key.bin')
    with _lock:
        if os.path.exists(box_path):
            with open(box_path, 'rb') as handle:
                raw = handle.read()
            if len(raw) != PrivateKey.SIZE:
                raise CryptoError('bad key file')
            _private = PrivateKey(raw)
        else:
            key = PrivateKey.generate()
            try:
                fd = os.open(box_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                with open(box_path, 'rb') as handle:
                    _private = PrivateKey(handle.read())
            else:
                try:
                    os.write(fd, bytes(key))
                finally:
                    os.close(fd)
                _private = key
        _field_key = _derive_field_key()
        _legacy_field_key = None
        _legacy_path = None
        if os.path.isfile(field_path):
            # Older builds wrote a random field key next to the database.
            # Load it once so those rows can be rewritten with SECRET_KEY.
            _legacy_path = field_path
            with open(field_path, 'rb') as handle:
                raw = handle.read()
            if len(raw) == SecretBox.KEY_SIZE:
                _legacy_field_key = raw


def _require_private():
    if _private is None:
        raise CryptoError('transport key is not initialized')
    return _private


def _require_field_key():
    if _field_key is None:
        raise CryptoError('field key is not initialized')
    return _field_key


def b64e(data):
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def b64d(value):
    if not isinstance(value, str) or not value:
        raise CryptoError('bad encoding')
    pad = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def public_key_b64():
    return b64e(bytes(_require_private().public_key))


def decode_client_pk(value):
    if not value:
        return None
    try:
        pk = b64d(value)
    except Exception:
        return None
    if len(pk) != 32:
        return None
    return pk


def open_payload(envelope):
    if not isinstance(envelope, dict) or envelope.get('v') != 1:
        raise CryptoError('bad envelope')
    pk = b64d(envelope.get('pk', ''))
    nonce = b64d(envelope.get('n', ''))
    ciphertext = b64d(envelope.get('c', ''))
    if len(pk) != 32 or len(nonce) != 24:
        raise CryptoError('bad envelope')
    box = Box(_require_private(), PublicKey(pk))
    plain = box.decrypt(ciphertext, nonce)
    data = json.loads(plain.decode('utf-8'))
    if not isinstance(data, dict):
        raise CryptoError('bad payload')
    return data


def redact_text(value):
    """Strip emails and device UUIDs from logs and error strings."""
    if value is None:
        return value
    text = _EMAIL_RE.sub('[email]', str(value))
    return _UUID_RE.sub('[device]', text)


def is_sealed_field(value):
    return isinstance(value, str) and value.startswith(_FIELD_PREFIX)


def _decrypt_field(value, key):
    raw = b64d(value[len(_FIELD_PREFIX):])
    return SecretBox(key).decrypt(raw).decode('utf-8')


def field_uses_current_key(value):
    if not is_sealed_field(value):
        return False
    try:
        _decrypt_field(value, _require_field_key())
        return True
    except Exception:
        return False


def seal_field(value):
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if is_sealed_field(text):
        if field_uses_current_key(text):
            return text
        text = open_field(text)
    token = bytes(SecretBox(_require_field_key()).encrypt(text.encode('utf-8')))
    return _FIELD_PREFIX + b64e(token)


def open_field(value):
    if value is None or not is_sealed_field(value):
        return value
    try:
        return _decrypt_field(value, _require_field_key())
    except CryptoError:
        if _legacy_field_key is None:
            raise
        return _decrypt_field(value, _legacy_field_key)


def discard_legacy_field_key():
    """Remove the old on-disk field key after every row uses SECRET_KEY."""
    global _legacy_field_key, _legacy_path
    path = _legacy_path
    _legacy_field_key = None
    _legacy_path = None
    if path and os.path.isfile(path):
        os.remove(path)


def seal_payload(client_pk, obj):
    if len(client_pk) != 32:
        raise CryptoError('bad key')
    box = Box(_require_private(), PublicKey(client_pk))
    encrypted = bytes(box.encrypt(
        json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ))
    return {
        'v': 1,
        'n': b64e(encrypted[:24]),
        'c': b64e(encrypted[24:]),
    }
