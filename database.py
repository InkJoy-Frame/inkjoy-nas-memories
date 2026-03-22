import sqlite3
import os

_db_path = None


def init_db(app):
    global _db_path
    data_dir = app.config.get('DATA_DIR', '/data')
    os.makedirs(data_dir, exist_ok=True)
    _db_path = os.path.join(data_dir, 'inkjoy.db')

    conn = sqlite3.connect(_db_path)
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
    conn.close()


def get_db():
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_schedules(account_id=None):
    conn = get_db()
    if account_id is None:
        rows = conn.execute('SELECT * FROM schedules ORDER BY created_at DESC').fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM schedules WHERE account_id = ? ORDER BY created_at DESC',
            (account_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
    return dict(row) if row else None


def get_account(account_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_accounts():
    conn = get_db()
    rows = conn.execute(
        'SELECT id, name, email, server_url FROM accounts ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_account(name, email, password, server_url, token=None):
    conn = get_db()
    existing = conn.execute(
        'SELECT id FROM accounts WHERE email = ? AND server_url = ?', (email, server_url)
    ).fetchone()
    if existing:
        conn.execute(
            'UPDATE accounts SET password=?, token=?, token_updated_at=datetime("now") WHERE id=?',
            (password, token, existing['id']),
        )
        account_id = existing['id']
    else:
        cur = conn.execute(
            'INSERT INTO accounts (name, email, password, server_url, token, token_updated_at) VALUES (?,?,?,?,?,datetime("now"))',
            (name, email, password, server_url, token),
        )
        account_id = cur.lastrowid
    conn.commit()
    conn.close()
    return account_id


def update_account_token(account_id, token):
    conn = get_db()
    conn.execute(
        'UPDATE accounts SET token=?, token_updated_at=datetime("now") WHERE id=?',
        (token, account_id),
    )
    conn.commit()
    conn.close()


def create_schedule(data):
    conn = get_db()
    cur = conn.execute(
        '''INSERT INTO schedules
           (name, account_id, device_id, device_name, device_width, device_height,
            folder_path, schedule_time, resize_mode, enabled)
           VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (
            data['name'], data['account_id'], data['device_id'],
            data.get('device_name'), data.get('device_width'), data.get('device_height'),
            data['folder_path'], data['schedule_time'],
            data.get('resize_mode', 'crop'), 1,
        ),
    )
    schedule_id = cur.lastrowid
    conn.commit()
    conn.close()
    return schedule_id


def update_schedule(schedule_id, data, account_id=None):
    conn = get_db()
    if account_id is None:
        cur = conn.execute(
            '''UPDATE schedules SET name=?, account_id=?, device_id=?, device_name=?,
               device_width=?, device_height=?, folder_path=?, schedule_time=?, resize_mode=?
               WHERE id=?''',
            (
                data['name'], data['account_id'], data['device_id'],
                data.get('device_name'), data.get('device_width'), data.get('device_height'),
                data['folder_path'], data['schedule_time'],
                data.get('resize_mode', 'crop'), schedule_id,
            ),
        )
    else:
        cur = conn.execute(
            '''UPDATE schedules SET name=?, account_id=?, device_id=?, device_name=?,
               device_width=?, device_height=?, folder_path=?, schedule_time=?, resize_mode=?
               WHERE id=? AND account_id=?''',
            (
                data['name'], data['account_id'], data['device_id'],
                data.get('device_name'), data.get('device_width'), data.get('device_height'),
                data['folder_path'], data['schedule_time'],
                data.get('resize_mode', 'crop'), schedule_id, account_id,
            ),
        )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def toggle_schedule(schedule_id, enabled, account_id=None):
    conn = get_db()
    if account_id is None:
        cur = conn.execute(
            'UPDATE schedules SET enabled=? WHERE id=?',
            (1 if enabled else 0, schedule_id),
        )
    else:
        cur = conn.execute(
            'UPDATE schedules SET enabled=? WHERE id=? AND account_id=?',
            (1 if enabled else 0, schedule_id, account_id),
        )
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


def update_schedule_run_status(schedule_id, status, error=None):
    conn = get_db()
    conn.execute(
        'UPDATE schedules SET last_run_at=datetime("now"), last_status=?, last_error=? WHERE id=?',
        (status, error, schedule_id),
    )
    conn.commit()
    conn.close()
