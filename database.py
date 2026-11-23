import hashlib
import logging
import os
import sqlite3
from sqlcipher3 import dbapi2 as sqlcipher

_db_path = None
_key_sql = None
_log = logging.getLogger(__name__)
_PLAIN_HEADER = b'SQLite format 3\x00'


def _database_key():
    """SQLCipher passphrase derived from the install password. Not stored on disk."""
    global _key_sql
    if _key_sql:
        return _key_sql
    from transport_crypto import install_secret
    secret = install_secret()
    raw = hashlib.pbkdf2_hmac(
        'sha256',
        secret.encode('utf-8'),
        b'inkjoy-nas-memories-sqlcipher-v1',
        200000,
        dklen=32,
    )
    _key_sql = "x'" + raw.hex() + "'"
    return _key_sql


def _apply_key(conn):
    conn.execute('PRAGMA key = "' + _database_key() + '"')


def _protect(path):
    """Do not chmod files on a mounted share.

    UGREEN maps the configured folder into the container. chmod inside the
    container is applied on the NAS and clears the folder's ACL.
    """
    return None


def _is_plain_sqlite(path):
    if not os.path.isfile(path) or os.path.getsize(path) < 16:
        return False
    with open(path, 'rb') as handle:
        return handle.read(16) == _PLAIN_HEADER


def _migrate_plain_db(path):
    """Rewrite a legacy plaintext database so stock sqlite3 can no longer open it."""
    src = sqlite3.connect(path)
    try:
        src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        dump = '\n'.join(src.iterdump())
    finally:
        src.close()

    tmp = path + '.enc'
    if os.path.exists(tmp):
        os.remove(tmp)
    dst = sqlcipher.connect(tmp)
    try:
        _apply_key(dst)
        dst.executescript(dump)
        dst.commit()
    except Exception:
        dst.close()
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    dst.close()
    os.replace(tmp, path)
    for suffix in ('-wal', '-shm', '-journal'):
        extra = path + suffix
        if os.path.exists(extra):
            os.remove(extra)
    _protect(path)
    _log.info('encrypted existing sqlite database')


def _connect():
    conn = sqlcipher.connect(_db_path)
    _apply_key(conn)
    conn.row_factory = sqlcipher.Row
    return conn


def init_db(app):
    global _db_path
    data_dir = app.config.get('DATA_DIR', '/data')
    os.makedirs(data_dir, exist_ok=True)
    _db_path = os.path.join(data_dir, 'inkjoy.db')
    if _is_plain_sqlite(_db_path):
        _migrate_plain_db(_db_path)

    conn = _connect()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT 'Default',
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            server_url TEXT NOT NULL,
            token TEXT,
            token_updated_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS nas_albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            include_subfolders INTEGER DEFAULT 1,
            exclude_folders TEXT DEFAULT '[]',
            filter_system_dirs INTEGER DEFAULT 1,
            selected_folders TEXT,
            account_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT,
            device_width INTEGER,
            device_height INTEGER,
            folder_path TEXT NOT NULL,
            schedule_time TEXT NOT NULL,
            resize_mode TEXT DEFAULT 'crop',
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_run_at TEXT,
            last_status TEXT,
            last_error TEXT
        );
    ''')
    conn.commit()

    cols = {r[1] for r in conn.execute('PRAGMA table_info(nas_albums)').fetchall()}

    for col, defn in [
        ('include_subfolders', 'INTEGER DEFAULT 1'),
        ('exclude_folders', "TEXT DEFAULT '[]'"),
        ('filter_system_dirs', 'INTEGER DEFAULT 1'),
        ('selected_folders', 'TEXT'),
    ]:

        if col not in cols:
            conn.execute(f'ALTER TABLE nas_albums ADD COLUMN {col} {defn}')

    sched_cols = {r[1] for r in conn.execute('PRAGMA table_info(schedules)').fetchall()}

    if 'nas_album_id' not in sched_cols:
        conn.execute('ALTER TABLE schedules ADD COLUMN nas_album_id INTEGER')

    if 'device_orientation' not in sched_cols:
        conn.execute('ALTER TABLE schedules ADD COLUMN device_orientation INTEGER DEFAULT 0')

    acct_cols = {r[1] for r in conn.execute('PRAGMA table_info(accounts)').fetchall()}
    if 'session_version' not in acct_cols:
        conn.execute('ALTER TABLE accounts ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')
    if 'logged_out' not in acct_cols:
        conn.execute('ALTER TABLE accounts ADD COLUMN logged_out INTEGER NOT NULL DEFAULT 0')

    conn.commit()
    conn.close()
    _protect(_db_path)


def get_db():
    return _connect()


def _seal(value):
    from transport_crypto import seal_field
    return seal_field(value)


def _open(value):
    from transport_crypto import open_field
    return open_field(value)


def _account_row(row):
    if not row:
        return None
    data = dict(row)
    if 'email' in data:
        data['email'] = _open(data.get('email'))
    if 'password' in data and data.get('password') is not None:
        data['password'] = _open(data.get('password'))
    return data


def _schedule_row(row):
    if not row:
        return None
    data = dict(row)
    if data.get('device_id'):
        data['device_id'] = _open(data['device_id'])
    return data


def _scrub_device_copy(data):
    """Keep the device id out of the display name columns."""
    device_id = data.get('device_id')
    if not device_id:
        return
    if data.get('device_name') == device_id:
        data['device_name'] = ''
    name = data.get('name')
    if name and device_id in str(name):
        data['name'] = str(name).replace(device_id, '').strip(' →') or 'schedule'


def migrate_sensitive_fields():
    """Encrypt legacy plaintext email, password, and device id rows.

    Passwords stay reversible because scheduled jobs log in to InkJoy with them.
    A password that is only checked locally would be stored as a hash instead.
    """
    from transport_crypto import discard_legacy_field_key
    conn = get_db()
    failed = False

    def reseal(value):
        nonlocal failed
        if value is None:
            return None
        try:
            return _seal(value)
        except Exception:
            failed = True
            _log.warning('could not re-encrypt a stored secret')
            return value

    accounts = conn.execute('SELECT id, email, password FROM accounts').fetchall()
    for row in accounts:
        email = reseal(row['email'])
        password = reseal(row['password'])
        if email != row['email'] or password != row['password']:
            conn.execute(
                'UPDATE accounts SET email=?, password=? WHERE id=?',
                (email, password, row['id']),
            )
    schedules = conn.execute('SELECT id, device_id, device_name, name FROM schedules').fetchall()
    for row in schedules:
        stored = reseal(row['device_id'])
        device_name = row['device_name']
        name = row['name']
        try:
            device_id = _open(stored) if stored else ''
        except Exception:
            failed = True
            device_id = None
        if device_id is not None:
            if device_name == device_id:
                device_name = ''
            if name and device_id and device_id in name:
                name = name.replace(device_id, '').strip(' →') or 'schedule'
        if stored != row['device_id'] or device_name != row['device_name'] or name != row['name']:
            conn.execute(
                'UPDATE schedules SET device_id=?, device_name=?, name=? WHERE id=?',
                (stored, device_name, name, row['id']),
            )
    conn.commit()
    conn.close()
    _protect(_db_path)
    if not failed:
        discard_legacy_field_key()


def get_all_schedules(account_id=None):
    conn = get_db()
    if account_id is None:
        rows = conn.execute('SELECT * FROM schedules ORDER BY schedule_time ASC').fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM schedules WHERE account_id = ? ORDER BY schedule_time ASC',
            (account_id,),
        ).fetchall()
    conn.close()
    return [_schedule_row(r) for r in rows]


def get_schedule(schedule_id, account_id=None):
    conn = get_db()
    if account_id is None:
        row = conn.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,)).fetchone()
    else:
        row = conn.execute(
            'SELECT * FROM schedules WHERE id = ? AND account_id = ?',
            (schedule_id, account_id),
        ).fetchone()
    conn.close()
    return _schedule_row(row)


def get_account(account_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
    conn.close()
    return _account_row(row)


def get_all_accounts():
    conn = get_db()
    rows = conn.execute(
        'SELECT id, name, email, server_url FROM accounts ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [_account_row(r) for r in rows]


def save_account(name, email, password, server_url, token=None):
    conn = get_db()
    existing_id = None
    for row in conn.execute('SELECT id, email, server_url FROM accounts').fetchall():
        if _open(row['email']) == email and row['server_url'] == server_url:
            existing_id = row['id']
            break
    stored_email = _seal(email)
    # 密码还要交给 InkJoy 登录，不能只存哈希。可逆密钥来自 SECRET_KEY，不写进数据目录。
    stored_password = _seal(password)
    if existing_id:
        conn.execute(
            'UPDATE accounts SET email=?, password=?, token=?, token_updated_at=datetime("now") WHERE id=?',
            (stored_email, stored_password, token, existing_id),
        )
        account_id = existing_id
    else:
        cur = conn.execute(
            'INSERT INTO accounts (name, email, password, server_url, token, token_updated_at) VALUES (?,?,?,?,?,datetime("now"))',
            (name, stored_email, stored_password, server_url, token),
        )
        account_id = cur.lastrowid
    conn.commit()
    conn.close()
    return account_id


def activate_web_session(account_id):
    """Start a new browser session and invalidate any previously issued cookie."""
    conn = get_db()
    conn.execute(
        'UPDATE accounts SET logged_out=0, session_version=COALESCE(session_version, 0) + 1 WHERE id=?',
        (account_id,),
    )
    row = conn.execute('SELECT session_version FROM accounts WHERE id=?', (account_id,)).fetchone()
    conn.commit()
    conn.close()
    return int(row['session_version'])


def revoke_web_session(account_id):
    """Logout: the current cookie and any copy of it must stop working."""
    conn = get_db()
    conn.execute(
        'UPDATE accounts SET logged_out=1, session_version=COALESCE(session_version, 0) + 1 WHERE id=?',
        (account_id,),
    )
    conn.commit()
    conn.close()


def update_account_token(account_id, token):
    conn = get_db()
    conn.execute(
        'UPDATE accounts SET token=?, token_updated_at=datetime("now") WHERE id=?',
        (token, account_id),
    )
    conn.commit()
    conn.close()


def create_schedule(data):
    _scrub_device_copy(data)
    conn = get_db()
    cur = conn.execute(
        '''INSERT INTO schedules
           (name, account_id, device_id, device_name, device_width, device_height,
            device_orientation, folder_path, schedule_time, resize_mode, enabled, nas_album_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            data['name'], data['account_id'], _seal(data['device_id']),
            data.get('device_name'), data.get('device_width'), data.get('device_height'),
            data.get('device_orientation') or 0,
            data['folder_path'], data['schedule_time'],
            data.get('resize_mode', 'crop'), 1,
            data.get('nas_album_id'),
        ),
    )
    schedule_id = cur.lastrowid
    conn.commit()
    conn.close()
    return schedule_id


def update_schedule(schedule_id, data, account_id=None):
    conn = get_db()
    updatable = ('name', 'device_id', 'device_name', 'device_width', 'device_height',
                 'device_orientation', 'folder_path', 'schedule_time', 'resize_mode', 'enabled')
    sets = []
    params = []

    _scrub_device_copy(data)
    for field in updatable:
        if field in data:
            value = _seal(data[field]) if field == 'device_id' else data[field]
            sets.append(f'{field} = ?')
            params.append(value)

    if not sets:
        conn.close()
        return False

    where = 'WHERE id = ?'
    params.append(schedule_id)

    if account_id is not None:
        where += ' AND account_id = ?'
        params.append(account_id)

    cur = conn.execute(f'UPDATE schedules SET {", ".join(sets)} {where}', params)
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_schedule(schedule_id, account_id=None):
    conn = get_db()
    if account_id is None:
        cur = conn.execute('DELETE FROM schedules WHERE id=?', (schedule_id,))
    else:
        cur = conn.execute(
            'DELETE FROM schedules WHERE id=? AND account_id=?',
            (schedule_id, account_id),
        )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_nas_albums(account_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM nas_albums WHERE account_id = ? ORDER BY created_at DESC',
        (account_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_nas_album(album_id, account_id=None):
    conn = get_db()
    if account_id is None:
        row = conn.execute('SELECT * FROM nas_albums WHERE id = ?', (album_id,)).fetchone()
    else:
        row = conn.execute(
            'SELECT * FROM nas_albums WHERE id = ? AND account_id = ?',
            (album_id, account_id),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_nas_album(name, folder_path, account_id,
                     filter_system_dirs=1, selected_folders=None):
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO nas_albums (name, folder_path, account_id, filter_system_dirs, selected_folders) VALUES (?,?,?,?,?)',
        (name, folder_path, account_id, filter_system_dirs, selected_folders),
    )
    album_id = cur.lastrowid
    conn.commit()
    conn.close()
    return album_id


def update_nas_album(album_id, account_id, **kwargs):
    conn = get_db()
    sets = []
    params = []

    for field in ('name', 'folder_path', 'selected_folders', 'filter_system_dirs'):
        if field in kwargs:
            sets.append(f'{field} = ?')
            params.append(kwargs[field])

    if not sets:
        conn.close()
        return False

    params.extend([album_id, account_id])
    cur = conn.execute(
        f'UPDATE nas_albums SET {", ".join(sets)} WHERE id = ? AND account_id = ?',
        params,
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def update_schedules_folder_by_album(album_id, folder_path):
    conn = get_db()
    conn.execute(
        'UPDATE schedules SET folder_path = ? WHERE nas_album_id = ?',
        (folder_path, album_id),
    )
    conn.commit()
    conn.close()


def get_device_schedule_times(device_id, account_id, exclude_id=None):
    conn = get_db()
    rows = conn.execute(
        'SELECT id, schedule_time, device_id FROM schedules WHERE account_id = ?',
        (account_id,),
    ).fetchall()
    conn.close()
    matched = []
    for row in rows:
        if exclude_id and row['id'] == exclude_id:
            continue
        if _open(row['device_id']) == device_id:
            matched.append({'id': row['id'], 'schedule_time': row['schedule_time']})
    return matched


def delete_nas_album(album_id, account_id):
    conn = get_db()
    cur = conn.execute(
        'DELETE FROM nas_albums WHERE id = ? AND account_id = ?',
        (album_id, account_id),
    )
    if cur.rowcount > 0:
        conn.execute('DELETE FROM schedules WHERE nas_album_id = ?', (album_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def update_schedule_run_status(schedule_id, status, error=None):
    from transport_crypto import redact_text
    conn = get_db()
    conn.execute(
        'UPDATE schedules SET last_run_at=datetime("now"), last_status=?, last_error=? WHERE id=?',
        (status, redact_text(error) if error else error, schedule_id),
    )
    conn.commit()
    conn.close()


def get_schedules_by_album(album_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM schedules WHERE nas_album_id = ? ORDER BY schedule_time ASC',
        (album_id,),
    ).fetchall()
    conn.close()
    return [_schedule_row(r) for r in rows]
