import json
import logging
import mimetypes
import os
import re
from datetime import timedelta
from functools import wraps
from io import BytesIO

from flask import (
    Flask, render_template, request, session, g,
    redirect, url_for, jsonify, send_file, Response,
)
from PIL import Image, ImageOps
from image_utils import IMAGE_EXTENSIONS, HEIC_EXTENSIONS, RAW_EXTENSIONS, open_image, ensure_rgb, save_for_display
from safe_files import (
    MissingPath, UnsafePath, directory_is_real, ensure_directory,
    iter_regular_files, list_directory, open_regular,
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'inkjoy-manager-secret-change-this')
app.config['IMAGES_DIR'] = os.environ.get('IMAGES_DIR', '/images')
app.config['DATA_DIR'] = os.environ.get('DATA_DIR', '/data')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

IMAGES_DIR = app.config['IMAGES_DIR']

SYSTEM_EXCLUDED_DIRS = {
    '@eaDir', '@Recycle', '#recycle', '.recycle',
    '.thumbnails', '.synology_thumbnails', 'thumbs',
    '.DS_Store', '__MACOSX', 'Thumbs.db',
}

from database import init_db
init_db(app)

from transport_crypto import (
    init_transport, public_key_b64, open_payload, seal_payload, decode_client_pk,
    redact_text,
)
init_transport(app.config['DATA_DIR'])

from database import migrate_sensitive_fields
migrate_sensitive_fields()

from scheduler_manager import init_scheduler
init_scheduler(app)

_SENSITIVE_FIELDS = {'email', 'password', 'device_id', 'deviceId'}


@app.context_processor
def inject_transport_key():
    return {'transport_pubkey': public_key_b64()}


def _install_plain_json(data):
    def _get_json(force=False, silent=False, cache=True):
        return data
    request.get_json = _get_json


def _reply_pk():
    pk = getattr(g, 'reply_pk', None)
    if pk:
        return pk
    pk = decode_client_pk(request.headers.get('X-Inkjoy-Pk', ''))
    if pk:
        return pk
    return decode_client_pk(request.cookies.get('inkjoy_box_pk', ''))


def _contains_sensitive(obj):
    if isinstance(obj, dict):
        if _SENSITIVE_FIELDS.intersection(obj):
            return True
        return any(_contains_sensitive(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_sensitive(v) for v in obj)
    return False


def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: '' if k in _SENSITIVE_FIELDS else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj

API_I18N = {
    'en': {
        'error.unauthorized': 'Not signed in',
        'error.session_expired': 'Login expired, please sign in again',
        'error.invalid_path': 'Invalid path',
        'error.name_required': 'Name cannot be empty',
        'error.folder_required': 'Please select at least one folder',
        'error.no_update': 'Nothing to update',
        'error.album_forbidden': 'Album not found or no permission',
        'error.album_missing': 'Album not found',
        'error.device_required': 'Please select a target device',
        'error.file_required': 'No image file received',
        'error.dir_forbidden': 'No permission to access this folder',
        'error.file_missing': 'File not found',
        'error.missing_body': 'Missing request data',
        'error.schedule_gap': 'Must be at least 30 minutes from existing time {time}',
        'error.schedule_forbidden': 'Schedule not found or no permission',
        'error.execute_failed': 'Run failed',
        'error.login_failed_email': 'Login failed for {email}',
        'error.login_failed': 'Login failed',
        'error.plaintext_forbidden': 'Email, password, and device id must be encrypted',
        'error.terms_required': 'Please read and agree to the User Agreement and Privacy Policy before signing in.',
        'error.transport': 'Could not read the encrypted request',
        'error.devices_failed': 'Failed to get device list',
        'error.publish_failed': 'Failed to publish image',
        'error.account_missing': 'Linked account not found',
        'error.folder_missing': 'Folder not found: {path}',
        'error.folder_empty': 'No images in folder (including subfolders): {path}',
    },
    'zh': {
        'error.unauthorized': '未登录',
        'error.session_expired': '登录已过期，请重新登录',
        'error.invalid_path': '非法路径',
        'error.name_required': '名称不能为空',
        'error.folder_required': '请至少选择一个文件夹',
        'error.no_update': '无更新内容',
        'error.album_forbidden': '相册不存在或无权限',
        'error.album_missing': '相册不存在',
        'error.device_required': '请选择目标设备',
        'error.file_required': '未收到图片文件',
        'error.dir_forbidden': '无权限访问此目录',
        'error.file_missing': '文件不存在',
        'error.missing_body': '缺少请求数据',
        'error.schedule_gap': '与已有时间点 {time} 间隔不足30分钟',
        'error.schedule_forbidden': '计划不存在或无权限',
        'error.execute_failed': '执行失败',
        'error.login_failed_email': '登录失败：{email}',
        'error.login_failed': '登录失败',
        'error.plaintext_forbidden': '邮箱、密码和设备标识不能明文传输',
        'error.terms_required': '请先阅读并同意《用户协议》和《隐私政策》后再登录。',
        'error.transport': '无法读取加密请求',
        'error.devices_failed': '获取设备列表失败',
        'error.publish_failed': '发布图片失败',
        'error.account_missing': '关联账号不存在',
        'error.folder_missing': '文件夹不存在: {path}',
        'error.folder_empty': '文件夹（含子文件夹）中没有图片: {path}',
    },
}


def _lang():
    header = (request.headers.get('X-InkJoy-Lang') or '').strip().lower()
    if header in API_I18N:
        return header
    cookie = (request.cookies.get('inkjoy_lang') or '').strip().lower()
    if cookie in API_I18N:
        return cookie
    best = request.accept_languages.best_match(['zh', 'zh-CN', 'zh-TW', 'en'])
    if best and best.startswith('zh'):
        return 'zh'
    return 'en'


def _t(key, **kwargs):
    table = API_I18N.get(_lang()) or API_I18N['en']
    text = table.get(key) or API_I18N['en'].get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def _json_error(key, status=400, **kwargs):
    return jsonify({'success': False, 'error': _t(key, **kwargs)}), status


def _translate_exception(msg):
    if not msg:
        return _t('error.execute_failed')

    exact = {
        '未登录': 'error.unauthorized',
        'Not signed in': 'error.unauthorized',
        '登录已过期，请重新登录': 'error.session_expired',
        'Login expired, please sign in again': 'error.session_expired',
        '非法路径': 'error.invalid_path',
        'Invalid path': 'error.invalid_path',
        '名称不能为空': 'error.name_required',
        'Name cannot be empty': 'error.name_required',
        '请至少选择一个文件夹': 'error.folder_required',
        'Please select at least one folder': 'error.folder_required',
        '无更新内容': 'error.no_update',
        'Nothing to update': 'error.no_update',
        '相册不存在或无权限': 'error.album_forbidden',
        'Album not found or no permission': 'error.album_forbidden',
        '相册不存在': 'error.album_missing',
        'Album not found': 'error.album_missing',
        '请选择目标设备': 'error.device_required',
        'Please select a target device': 'error.device_required',
        '未收到图片文件': 'error.file_required',
        'No image file received': 'error.file_required',
        '无权限访问此目录': 'error.dir_forbidden',
        'No permission to access this folder': 'error.dir_forbidden',
        '文件不存在': 'error.file_missing',
        'File not found': 'error.file_missing',
        '缺少请求数据': 'error.missing_body',
        'Missing request data': 'error.missing_body',
        '计划不存在或无权限': 'error.schedule_forbidden',
        'Schedule not found or no permission': 'error.schedule_forbidden',
        '执行失败': 'error.execute_failed',
        'Run failed': 'error.execute_failed',
        '登录失败': 'error.login_failed',
        'Login failed': 'error.login_failed',
        '获取设备列表失败': 'error.devices_failed',
        'Failed to get device list': 'error.devices_failed',
        '发布图片失败': 'error.publish_failed',
        'Failed to publish image': 'error.publish_failed',
    }
    if msg in exact:
        return _t(exact[msg])

    patterns = [
        (r'^与已有时间点 (.+) 间隔不足30分钟$', 'error.schedule_gap', 'time'),
        (r'^Must be at least 30 minutes from existing time (.+)$', 'error.schedule_gap', 'time'),
        (r'^登录失败：(.+)$', 'error.login_failed', None),
        (r'^Login failed for (.+)$', 'error.login_failed', None),
        (r'^文件夹不存在: (.+)$', 'error.folder_missing', 'path'),
        (r'^Folder not found: (.+)$', 'error.folder_missing', 'path'),
        (r'^文件夹（含子文件夹）中没有图片: (.+)$', 'error.folder_empty', 'path'),
        (r'^No images in folder \(including subfolders\): (.+)$', 'error.folder_empty', 'path'),
        (r'^关联账号不存在(?: \(account_id=.+\))?$', 'error.account_missing', None),
        (r'^Linked account not found(?: \(account_id=.+\))?$', 'error.account_missing', None),
    ]
    for pattern, key, arg in patterns:
        m = re.match(pattern, msg)
        if m:
            if arg:
                return _t(key, **{arg: m.group(1)})
            return _t(key)
    return redact_text(msg)


def _needs_app_crypto():
    """HTTPS already encrypts the login, cookies, and API calls.

    http://<lan-ip>:<port> is not a secure context, so those fields must be
    sealed. A client-supplied X-Forwarded-Proto is ignored unless the
    operator explicitly trusts the proxy; otherwise HTTP could skip the seal.
    """
    if request.is_secure:
        return False
    if os.environ.get('TRUST_FORWARDED_PROTO') == '1':
        proto = (request.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip().lower()
        if proto == 'https':
            return False
    return True


def _sensitive_present(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _SENSITIVE_FIELDS and value not in (None, ''):
                return True
            if _sensitive_present(value):
                return True
        return False
    if isinstance(obj, list):
        return any(_sensitive_present(item) for item in obj)
    return False


def _reject_plaintext():
    g.skip_transport = True
    return _json_error('error.plaintext_forbidden')


def _web_session_current():
    """Cookie 里的登录态必须仍是服务端当前这一次，退出后的旧 Cookie 无效。"""
    account_id = session.get('account_id')
    sv = session.get('sv')
    if not account_id or sv is None:
        return False
    from database import get_account
    account = get_account(account_id)
    if not account or account.get('logged_out'):
        return False
    return int(account.get('session_version') or 0) == int(sv)


@app.before_request
def reject_stale_session():
    """没有本次登录签发的 Cookie 时，不能从数据库自动登录。
    退出后的旧 Cookie 也不再有效。同一次请求里不能接着用库里的密码再登录。
    """
    g.session_rejected = False
    session.pop('email', None)
    session.pop('password', None)
    session.pop('device_id', None)
    if request.endpoint == 'static':
        return
    if 'token' in session and not _web_session_current():
        g.session_rejected = True
        session.clear()


@app.before_request
def unwrap_secure_body():
    """On HTTP, reject plaintext email, password, and device id. Open sealed bodies."""
    if request.endpoint == 'static':
        return None
    if _needs_app_crypto():
        for key in _SENSITIVE_FIELDS:
            if request.args.get(key):
                return _reject_plaintext()

    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None

    ctype = (request.content_type or '').lower()
    if 'application/json' in ctype:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return None
        if data.get('v') == 1 and 'c' in data and 'pk' in data:
            try:
                plain = open_payload(data)
            except Exception:
                logging.getLogger(__name__).warning('rejected sealed json body')
                g.skip_transport = True
                return _json_error('error.transport')
            if not isinstance(plain, dict):
                g.skip_transport = True
                return _json_error('error.transport')
            g.reply_pk = decode_client_pk(data.get('pk', ''))
            _install_plain_json(plain)
            return None
        if _needs_app_crypto() and _sensitive_present(data):
            return _reject_plaintext()
        return None

    if 'multipart/form-data' in ctype or 'application/x-www-form-urlencoded' in ctype:
        if _needs_app_crypto():
            for key in _SENSITIVE_FIELDS:
                if (request.form.get(key) or '').strip():
                    return _reject_plaintext()
        raw = request.form.get('payload')
        if raw:
            try:
                envelope = json.loads(raw)
                plain = open_payload(envelope)
            except Exception:
                logging.getLogger(__name__).warning('rejected sealed form body')
                g.skip_transport = True
                return _json_error('error.transport')
            if not isinstance(plain, dict):
                g.skip_transport = True
                return _json_error('error.transport')
            g.secure_form = plain
            if isinstance(envelope, dict):
                g.reply_pk = decode_client_pk(envelope.get('pk', ''))
    return None


@app.after_request
def set_frame_options(resp):
    """Refuse to be embedded. Blocks clickjacking of the login page."""
    resp.headers['X-Frame-Options'] = 'DENY'
    return resp


@app.after_request
def seal_json_response(resp):
    if not _needs_app_crypto():
        return resp
    if getattr(g, 'skip_transport', False):
        return resp
    if 'application/json' not in (resp.content_type or '').lower():
        return resp
    data = resp.get_json(silent=True)
    if data is None:
        return resp
    pk = _reply_pk()
    if not pk:
        if _contains_sensitive(data):
            redacted = jsonify(_redact(data))
            redacted.status_code = resp.status_code
            return redacted
        return resp
    try:
        sealed = jsonify(seal_payload(pk, data))
    except Exception:
        logging.getLogger(__name__).warning('response seal failed')
        failed = jsonify({'success': False, 'error': 'transport'})
        failed.status_code = 500
        return failed
    sealed.status_code = resp.status_code
    return sealed


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'token' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return _json_error('error.unauthorized', 401)
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def _handle_api_error(e):
    """上游 InkJoy API 返回 401 时清 session 并透传 401，与 webtool 的 apiFetch 拦截逻辑对齐。"""
    from requests.exceptions import HTTPError

    if isinstance(e, HTTPError) and e.response is not None and e.response.status_code == 401:
        session.clear()
        return _json_error('error.session_expired', 401)

    return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


def _try_refresh_token():
    """上游 token 过期时，用数据库中保存的账号密码重新登录并更新 session。

    只在这次请求的 Cookie 仍然有效时做。旧 Cookie 被拒绝后，不能在同一请求里再登录。
    """
    if getattr(g, 'session_rejected', False):
        return False
    account_id = session.get('account_id')
    if not account_id:
        return False

    from database import get_account, update_account_token
    from api_client import InkJoyClient

    account = get_account(account_id)
    if not account or not account.get('password'):
        return False

    try:
        client = InkJoyClient(account['server_url'])
        login_data = client.login(account['email'], account['password'])
        session['token'] = login_data['token']
        update_account_token(account_id, login_data['token'])
        logging.getLogger(__name__).info(f'token refreshed for account {account_id}')
        return True
    except Exception as e:
        logging.getLogger(__name__).warning(f'token refresh failed: {redact_text(e)}')
        return False


def _call_inkjoy(make_client_fn):
    """执行 InkJoy API 调用；401 时自动刷新 token 并重试一次。"""
    from requests.exceptions import HTTPError

    try:
        return make_client_fn()
    except HTTPError as e:
        if e.response is not None and e.response.status_code == 401 and _try_refresh_token():
            return make_client_fn()
        raise


def _time_to_minutes(time_str):
    h, m = time_str.split(':')
    return int(h) * 60 + int(m)


def _validate_time_gap(device_id, account_id, new_time, exclude_id=None):
    """同一设备上的推送间隔不得少于30分钟。"""
    from database import get_device_schedule_times

    existing = get_device_schedule_times(device_id, account_id, exclude_id)
    new_min = _time_to_minutes(new_time)

    for s in existing:
        old_min = _time_to_minutes(s['schedule_time'])
        gap = abs(new_min - old_min)
        gap = min(gap, 1440 - gap)

        if gap < 30:
            return False, s['schedule_time']

    return True, None


def _require_account_id():
    """从 session 取 account_id，缺失时返回 (None, 401 response)。"""
    aid = session.get('account_id')

    if aid:
        return aid, None

    return None, _json_error('error.unauthorized', 401)


def _validate_folder_paths(selected_folders):
    """校验文件夹路径合法性，非法时返回错误 response。"""
    for fp in selected_folders:
        try:
            ok = directory_is_real(IMAGES_DIR, fp)
        except UnsafePath:
            return _json_error('error.invalid_path')
        if not ok:
            return _json_error('error.invalid_path')

    return None


def _get_album_photos(album):
    """扫描相册包含的所有目录，返回 (img_count, cover, photos)。兼容老格式（仅 folder_path）。"""
    selected = json.loads(album.get('selected_folders') or 'null') or [album['folder_path']]
    filter_sys = bool(album.get('filter_system_dirs', 1))
    return _scan_selected_folders(selected, filter_system_dirs=filter_sys)


def _scan_selected_folders(selected_folders, filter_system_dirs=True):
    """扫描多个选中目录（各自递归），去重后返回 (img_count, cover, photos)。"""
    seen = set()
    photos = []
    blocked = SYSTEM_EXCLUDED_DIRS if filter_system_dirs else set()

    def skip_dir(name):
        return name in blocked

    for folder_path in selected_folders:
        try:
            paths = iter_regular_files(IMAGES_DIR, folder_path, skip_dir=skip_dir)
        except (UnsafePath, MissingPath):
            continue

        for rel in paths:
            name = rel.rsplit('/', 1)[-1]
            if os.path.splitext(name)[1].lower() not in IMAGE_EXTENSIONS:
                continue
            if rel not in seen:
                seen.add(rel)
                photos.append({'name': name, 'path': rel})

    cover = photos[0]['path'] if photos else None
    return len(photos), cover, photos


# ── Pages ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'token' in session:
        return render_template('home.html')
    return redirect(url_for('login'))


@app.route('/legal/collected')
def legal_collected():
    return render_template('legal_list.html', kind='collected', lang=_lang())


@app.route('/legal/shared')
def legal_shared():
    return render_template('legal_list.html', kind='shared', lang=_lang())


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method != 'POST':
        return render_template('login.html')

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from api_client import InkJoyClient, SERVERS

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form or {}
    if data.get('agreed') is not True:
        return _json_error('error.terms_required', 400)

    email = (data.get('email') or '').strip()
    password = data.get('password', '')

    chosen_server = data.get('server_url')
    if chosen_server:
        try:
            client = InkJoyClient(chosen_server)
            login_data = client.login(email, password)
            _finish_login(email, password, chosen_server, login_data)
            return jsonify({'success': True, 'server_environment': _server_environment(chosen_server)})
        except Exception as e:
            return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400

    def _try_server(name, url):
        try:
            client = InkJoyClient(url)
            return name, url, client.login(email, password)
        except Exception:
            return name, url, None

    with ThreadPoolExecutor(max_workers=len(SERVERS)) as pool:
        futures = {pool.submit(_try_server, k, v): k for k, v in SERVERS.items()}
        successes = []
        for f in as_completed(futures):
            name, url, login_data = f.result()
            if login_data:
                successes.append({'name': name, 'url': url, 'token': login_data['token']})

    if not successes:
        return _json_error('error.login_failed')

    if len(successes) == 1:
        s = successes[0]
        _finish_login(email, password, s['url'], {'token': s['token']})
        return jsonify({'success': True, 'server_environment': _server_environment(s['url'])})

    return jsonify({
        'success': False,
        'conflict': True,
        'servers': [{'name': s['name'], 'url': s['url']} for s in successes],
    })


def _server_environment(server_url):
    """Map an API host to the privacy-policy environment code.

    Guangzhou test (app.ink.epaperframe.com) stays CN_TEST. Privacy pages for
    CN and CN_TEST both use the Guangzhou production host.
    """
    host = (server_url or '').lower()
    if 'ink.epaperframe.com' in host:
        return 'CN_TEST'
    if 'advisor.epaperframe.com' in host:
        return 'CN'
    return 'FR'


def _finish_login(email, password, server_url, login_data):
    from database import activate_web_session, save_account
    from api_client import SERVERS

    session.permanent = True
    session['token'] = login_data['token']
    session['server_url'] = server_url
    session['server_key'] = next((k for k, v in SERVERS.items() if v == server_url), 'unknown')

    account_id = save_account(
        'InkJoy', email, password, server_url, login_data['token']
    )
    session['account_id'] = account_id
    session['sv'] = activate_web_session(account_id)


@app.route('/logout')
def logout():
    from database import revoke_web_session
    account_id = session.get('account_id')
    if account_id:
        revoke_web_session(account_id)
    session.clear()
    return redirect(url_for('login'))


# ── API: Devices ──────────────────────────────────────────────────────────────

@app.route('/api/devices')
@login_required
def api_devices():
    from api_client import InkJoyClient
    try:
        def _fetch():
            client = InkJoyClient(session['server_url'], session['token'])
            return client.get_devices()

        devices = _call_inkjoy(_fetch)
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        return _handle_api_error(e)


# ── API: Albums ──────────────────────────────────────────────────────────────

@app.route('/api/nas-albums')
@login_required
def api_nas_albums_list():
    from database import get_nas_albums
    account_id, err = _require_account_id()

    if err:
        return err

    albums = get_nas_albums(account_id)
    result = []

    for a in albums:
        img_count, cover_path, _ = _get_album_photos(a)
        result.append({**a, 'imgCount': img_count, 'coverPath': cover_path})

    return jsonify({'success': True, 'albums': result})


@app.route('/api/nas-albums', methods=['POST'])
@login_required
def api_nas_albums_create():
    from database import create_nas_album
    account_id, err = _require_account_id()

    if err:
        return err

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    selected_folders = data.get('selected_folders', [])

    if not name:
        return _json_error('error.name_required')

    if not selected_folders:
        return _json_error('error.folder_required')

    path_err = _validate_folder_paths(selected_folders)

    if path_err:
        return path_err

    filter_system_dirs = 1 if data.get('filter_system_dirs', True) else 0
    folder_path = selected_folders[0]

    album_id = create_nas_album(
        name, folder_path, account_id,
        filter_system_dirs=filter_system_dirs,
        selected_folders=json.dumps(selected_folders),
    )
    return jsonify({'success': True, 'id': album_id})


@app.route('/api/nas-albums/<int:album_id>', methods=['PUT'])
@login_required
def api_nas_albums_update(album_id):
    from database import update_nas_album, update_schedules_folder_by_album
    account_id, err = _require_account_id()

    if err:
        return err

    data = request.get_json() or {}
    kwargs = {}

    if 'name' in data:
        name = data['name'].strip()

        if not name:
            return _json_error('error.name_required')

        kwargs['name'] = name

    if 'selected_folders' in data:
        selected_folders = data['selected_folders']

        if not selected_folders:
            return _json_error('error.folder_required')

        path_err = _validate_folder_paths(selected_folders)

        if path_err:
            return path_err

        kwargs['selected_folders'] = json.dumps(selected_folders)
        kwargs['folder_path'] = selected_folders[0]

    if 'filter_system_dirs' in data:
        kwargs['filter_system_dirs'] = 1 if data['filter_system_dirs'] else 0

    if not kwargs:
        return _json_error('error.no_update')

    if not update_nas_album(album_id, account_id, **kwargs):
        return _json_error('error.album_forbidden', 404)

    if 'folder_path' in kwargs:
        update_schedules_folder_by_album(album_id, kwargs['folder_path'])

    return jsonify({'success': True})


@app.route('/api/nas-albums/<int:album_id>', methods=['DELETE'])
@login_required
def api_nas_albums_delete(album_id):
    from database import delete_nas_album, get_schedules_by_album
    from scheduler_manager import remove_job
    account_id, err = _require_account_id()

    if err:
        return err

    schedules = get_schedules_by_album(album_id)

    if not delete_nas_album(album_id, account_id):
        return _json_error('error.album_forbidden', 404)

    for s in schedules:
        remove_job(s['id'])

    return jsonify({'success': True})


@app.route('/api/nas-albums/<int:album_id>/photos')
@login_required
def api_nas_album_photos(album_id):
    from database import get_nas_album
    account_id, err = _require_account_id()

    if err:
        return err

    album = get_nas_album(album_id, account_id)

    if not album:
        return _json_error('error.album_missing', 404)

    _, _, photos = _get_album_photos(album)
    return jsonify({'success': True, 'photos': photos})


@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    from api_client import InkJoyClient
    try:
        secure = getattr(g, 'secure_form', None) or {}
        device_id = str(secure.get('device_id') or '').strip()
        if not device_id and not _needs_app_crypto():
            device_id = str(request.form.get('device_id') or '').strip()
        if not device_id:
            return _json_error('error.device_required')

        file = request.files.get('file')
        if not file:
            return _json_error('error.file_required')

        pre_processed = request.form.get('pre_processed') == '1'

        if pre_processed:
            raw = file.read()
            ext = 'png' if file.content_type == 'image/png' else 'jpg'
        else:
            img = ensure_rgb(Image.open(file.stream))

            dw = request.form.get('device_width', type=int)
            dh = request.form.get('device_height', type=int)

            if dw and dh:
                img = ImageOps.fit(img, (dw, dh), Image.LANCZOS)

            output = BytesIO()
            ext, _ = save_for_display(img, output)
            output.seek(0)
            raw = output.read()

        def _upload():
            client = InkJoyClient(session['server_url'], session['token'])
            return client.publish_image(device_id, raw, filename=f'image.{ext}')

        result = _call_inkjoy(_upload)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return _handle_api_error(e)


# ── API: File Browser ─────────────────────────────────────────────────────────

@app.route('/api/browse')
@login_required
def api_browse():
    rel_path = request.args.get('path', '')
    try:
        ensure_directory(IMAGES_DIR, rel_path)
        entries = list_directory(IMAGES_DIR, rel_path)
    except PermissionError:
        return _json_error('error.dir_forbidden', 403)
    except (UnsafePath, MissingPath):
        return _json_error('error.invalid_path')

    items = []
    for entry in entries:
        if entry['kind'] == 'dir':
            items.append({'name': entry['name'], 'path': entry['rel'], 'type': 'dir'})
        elif os.path.splitext(entry['name'])[1].lower() in IMAGE_EXTENSIONS:
            items.append({
                'name': entry['name'],
                'path': entry['rel'],
                'type': 'image',
                'size': entry['size'],
            })
    items.sort(key=lambda item: (item['type'] != 'dir', item['name'].lower()))
    return jsonify({'success': True, 'path': rel_path, 'items': items})


@app.route('/api/image')
@login_required
def api_image():
    rel_path = request.args.get('path', '')
    try:
        fd = open_regular(IMAGES_DIR, rel_path)
    except UnsafePath:
        return Response(_t('error.invalid_path'), status=400)
    except MissingPath:
        return Response(_t('error.file_missing'), status=404)

    fh = os.fdopen(fd, 'rb')
    ext = os.path.splitext(rel_path)[1].lower()
    needs_transcode = ext in HEIC_EXTENSIONS or ext in RAW_EXTENSIONS
    thumb = request.args.get('thumb', 'false').lower() == 'true'

    if thumb or needs_transcode:
        try:
            img = open_image(fh, ext)
            if thumb:
                img.thumbnail((160, 160))
            img = ensure_rgb(img) if needs_transcode else img
            output = BytesIO()
            if thumb:
                img.save(output, format='JPEG', quality=75)
            elif needs_transcode:
                img.save(output, format='JPEG', quality=90)
            output.seek(0)
            return send_file(output, mimetype='image/jpeg')
        except Exception:
            return Response(_t('error.file_missing'), status=404)
        finally:
            fh.close()

    mime = mimetypes.guess_type(rel_path)[0] or 'application/octet-stream'
    return send_file(fh, mimetype=mime)


# ── API: Schedules ────────────────────────────────────────────────────────────

@app.route('/api/schedules', methods=['GET'])
@login_required
def api_schedules_list():
    from database import get_all_schedules
    account_id, err = _require_account_id()

    if err:
        return err

    return jsonify({'success': True, 'schedules': get_all_schedules(account_id=account_id)})


@app.route('/api/schedules', methods=['POST'])
@login_required
def api_schedules_create():
    from database import create_schedule, get_schedule
    from scheduler_manager import add_job
    account_id, err = _require_account_id()

    if err:
        return err

    data = request.get_json()
    if not data:
        return _json_error('error.missing_body')
    data['account_id'] = account_id

    device_id = data.get('device_id')
    schedule_time = data.get('schedule_time')

    if device_id and schedule_time:
        ok, conflict = _validate_time_gap(device_id, account_id, schedule_time)

        if not ok:
            return _json_error('error.schedule_gap', time=conflict)

    try:
        sid = create_schedule(data)
        if data.get('enabled', True):
            add_job(get_schedule(sid))
        return jsonify({'success': True, 'id': sid})
    except Exception as e:
        return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


@app.route('/api/schedules/<int:sid>', methods=['PUT'])
@login_required
def api_schedules_update(sid):
    from database import update_schedule, get_schedule
    from scheduler_manager import add_job, remove_job
    account_id, err = _require_account_id()

    if err:
        return err

    data = request.get_json()
    if not data:
        return _json_error('error.missing_body')

    if 'schedule_time' in data:
        schedule = get_schedule(sid, account_id=account_id)

        if not schedule:
            return _json_error('error.schedule_forbidden', 404)

        ok, conflict = _validate_time_gap(schedule['device_id'], account_id, data['schedule_time'], exclude_id=sid)

        if not ok:
            return _json_error('error.schedule_gap', time=conflict)

    try:
        updated = update_schedule(sid, data, account_id=account_id)

        if not updated:
            return _json_error('error.schedule_forbidden', 404)

        schedule = get_schedule(sid)
        remove_job(sid)

        if schedule['enabled']:
            add_job(schedule)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


@app.route('/api/schedules/<int:sid>', methods=['DELETE'])
@login_required
def api_schedules_delete(sid):
    from database import delete_schedule
    from scheduler_manager import remove_job
    account_id, err = _require_account_id()

    if err:
        return err
    try:
        deleted = delete_schedule(sid, account_id=account_id)
        if not deleted:
            return _json_error('error.schedule_forbidden', 404)
        remove_job(sid)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


@app.route('/api/schedules/<int:sid>/toggle', methods=['POST'])
@login_required
def api_schedules_toggle(sid):
    from database import update_schedule, get_schedule
    from scheduler_manager import add_job, remove_job
    account_id, err = _require_account_id()

    if err:
        return err

    data = request.get_json() or {}
    enabled = 1 if data.get('enabled', True) else 0

    try:
        updated = update_schedule(sid, {'enabled': enabled}, account_id=account_id)

        if not updated:
            return _json_error('error.schedule_forbidden', 404)

        schedule = get_schedule(sid)
        remove_job(sid)

        if enabled:
            add_job(schedule)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


@app.route('/api/schedules/<int:sid>/run', methods=['POST'])
@login_required
def api_schedules_run(sid):
    from database import get_schedule
    from scheduler_manager import execute_schedule
    account_id, err = _require_account_id()

    if err:
        return err
    try:
        s = get_schedule(sid, account_id=account_id)
        if not s:
            return _json_error('error.schedule_forbidden', 404)
        execute_schedule(sid)
        s = get_schedule(sid)
        if s and s.get('last_status') == 'error':
            return jsonify({'success': False, 'error': _translate_exception(s.get('last_error', ''))}), 400
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


@app.route('/api/nas-albums/<int:album_id>/schedules')
@login_required
def api_nas_album_schedules(album_id):
    from database import get_nas_album, get_schedules_by_album
    account_id, err = _require_account_id()

    if err:
        return err

    if not get_nas_album(album_id, account_id):
        return _json_error('error.album_forbidden', 404)

    return jsonify({'success': True, 'schedules': get_schedules_by_album(album_id)})


# ── API: Accounts ─────────────────────────────────────────────────────────────

@app.route('/api/accounts')
@login_required
def api_accounts():
    from database import get_all_accounts
    return jsonify({'success': True, 'accounts': get_all_accounts()})


# ── API: Scheduler Debug ───────────────────────────────────────────────────────

@app.route('/api/scheduler/status')
@login_required
def api_scheduler_status():
    from scheduler_manager import get_scheduler_status
    return jsonify({'success': True, **get_scheduler_status()})


@app.route('/api/scheduler/reload', methods=['POST'])
@login_required
def api_scheduler_reload():
    """从数据库重新加载所有已启用的 job（用于排查 job 丢失问题）。"""
    from database import get_all_schedules
    from scheduler_manager import add_job, remove_job, get_scheduler_status
    try:
        for schedule in get_all_schedules():
            remove_job(schedule['id'])
            if schedule['enabled']:
                add_job(schedule)
        return jsonify({'success': True, **get_scheduler_status()})
    except Exception as e:
        return jsonify({'success': False, 'error': _translate_exception(str(e))}), 400


if __name__ == '__main__':
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(app.config['DATA_DIR'], exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=os.environ.get('FLASK_DEBUG', '0') == '1')
