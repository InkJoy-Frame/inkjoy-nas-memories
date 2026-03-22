import os
import logging
from datetime import timedelta
from functools import wraps
from io import BytesIO

from flask import (
    Flask, render_template, request, session,
    redirect, url_for, jsonify, send_file, Response,
)
from PIL import Image

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'inkjoy-manager-secret-change-this')
app.config['IMAGES_DIR'] = os.environ.get('IMAGES_DIR', '/images')
app.config['DATA_DIR'] = os.environ.get('DATA_DIR', '/data')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

IMAGES_DIR = app.config['IMAGES_DIR']
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

from database import init_db
init_db(app)

from scheduler_manager import init_scheduler
init_scheduler(app)


@app.before_request
def auto_restore_session():
    """Session 丢失时（Cookie 过期/浏览器清 Cookie），从数据库中读取已保存的
    token 直接恢复 session，无需发起任何网络请求。
    若 token 已过期，后续 API 调用会返回 401 并跳转登录页。
    """
    skip = {'static', 'login', 'logout'}
    if request.endpoint in skip:
        return
    if 'token' in session:
        return

    try:
        from database import get_saved_account
        account = get_saved_account()
        if not account or not account.get('token'):
            return
        session.permanent = True
        session['token'] = account['token']
        session['server_url'] = account['server_url']
        session['email'] = account['email']
        session['account_id'] = account['id']
        logging.getLogger(__name__).info(
            f'auto_restore_session: restored session for {account["email"]} (token from DB, no network call)'
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f'auto_restore_session failed: {e}')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'token' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': '未登录'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── Pages ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'token' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() or request.form
        server_key = data.get('server', 'global')
        email = data.get('email', '').strip()
        password = data.get('password', '')

        from api_client import InkJoyClient, SERVERS
        server_url = SERVERS.get(server_key, SERVERS['global'])

        try:
            client = InkJoyClient(server_url)
            login_data = client.login(email, password)

            session.permanent = True
            session['token'] = login_data['token']
            session['uid'] = login_data.get('uid')
            session['server_url'] = server_url
            session['server_key'] = server_key
            session['email'] = email

            from database import save_account
            account_id = save_account(
                email.split('@')[0], email, password, server_url, login_data['token']
            )
            session['account_id'] = account_id

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/upload')
@login_required
def upload():
    return render_template('upload.html')


@app.route('/schedules')
@login_required
def schedules():
    return render_template('schedules.html')


# ── API: Devices ──────────────────────────────────────────────────────────────

@app.route('/api/devices')
@login_required
def api_devices():
    from api_client import InkJoyClient
    try:
        client = InkJoyClient(session['server_url'], session['token'])
        devices = client.get_devices()
        return jsonify({'success': True, 'devices': devices})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    from api_client import InkJoyClient
    try:
        device_id = request.form.get('device_id', '').strip()
        if not device_id:
            return jsonify({'success': False, 'error': '请选择目标设备'}), 400

        file = request.files.get('file')
        if not file:
            return jsonify({'success': False, 'error': '未收到图片文件'}), 400

        img = Image.open(file.stream)
        if img.mode not in ('RGB',):
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            else:
                img = img.convert('RGB')

        output = BytesIO()
        img.save(output, format='JPEG', quality=95)
        output.seek(0)

        client = InkJoyClient(session['server_url'], session['token'])
        result = client.publish_image(device_id, output.read())
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ── API: File Browser ─────────────────────────────────────────────────────────

@app.route('/api/browse')
@login_required
def api_browse():
    rel_path = request.args.get('path', '')
    safe_path = os.path.normpath(os.path.join(IMAGES_DIR, rel_path))

    if not safe_path.startswith(os.path.normpath(IMAGES_DIR)):
        return jsonify({'success': False, 'error': '非法路径'}), 400

    if not os.path.isdir(safe_path):
        os.makedirs(safe_path, exist_ok=True)

    items = []
    try:
        for name in sorted(os.listdir(safe_path), key=lambda x: (not os.path.isdir(os.path.join(safe_path, x)), x.lower())):
            full = os.path.join(safe_path, name)
            rel = os.path.relpath(full, IMAGES_DIR).replace('\\', '/')
            if os.path.isdir(full):
                items.append({'name': name, 'path': rel, 'type': 'dir'})
            elif os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS:
                items.append({
                    'name': name,
                    'path': rel,
                    'type': 'image',
                    'size': os.path.getsize(full),
                })
    except PermissionError:
        return jsonify({'success': False, 'error': '无权限访问此目录'}), 403

    return jsonify({'success': True, 'path': rel_path, 'items': items})


@app.route('/api/image')
@login_required
def api_image():
    rel_path = request.args.get('path', '')
    safe_path = os.path.normpath(os.path.join(IMAGES_DIR, rel_path))

    if not safe_path.startswith(os.path.normpath(IMAGES_DIR)):
        return Response('非法路径', status=400)
    if not os.path.isfile(safe_path):
        return Response('文件不存在', status=404)

    thumb = request.args.get('thumb', 'false').lower() == 'true'
    if thumb:
        try:
            img = Image.open(safe_path)
            img.thumbnail((160, 160))
            output = BytesIO()
            img.save(output, format='JPEG', quality=75)
            output.seek(0)
            return send_file(output, mimetype='image/jpeg')
        except Exception:
            pass

    return send_file(safe_path)


# ── API: Schedules ────────────────────────────────────────────────────────────

@app.route('/api/schedules', methods=['GET'])
@login_required
def api_schedules_list():
    from database import get_all_schedules
    account_id = session.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': '未登录账号上下文'}), 401
    return jsonify({'success': True, 'schedules': get_all_schedules(account_id=account_id)})


@app.route('/api/schedules', methods=['POST'])
@login_required
def api_schedules_create():
    from database import create_schedule, get_schedule
    from scheduler_manager import add_job
    account_id = session.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': '未登录账号上下文'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '缺少请求数据'}), 400
    data['account_id'] = account_id
    try:
        sid = create_schedule(data)
        if data.get('enabled', True):
            add_job(get_schedule(sid))
        return jsonify({'success': True, 'id': sid})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/schedules/<int:sid>', methods=['PUT'])
@login_required
def api_schedules_update(sid):
    from database import update_schedule, get_schedule
    from scheduler_manager import add_job, remove_job
    account_id = session.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': '未登录账号上下文'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '缺少请求数据'}), 400
    data['account_id'] = account_id
    try:
        updated = update_schedule(sid, data, account_id=account_id)
        if not updated:
            return jsonify({'success': False, 'error': '计划不存在或无权限'}), 404
        schedule = get_schedule(sid)
        remove_job(sid)
        if schedule['enabled']:
            add_job(schedule)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/schedules/<int:sid>', methods=['DELETE'])
@login_required
def api_schedules_delete(sid):
    from database import delete_schedule
    from scheduler_manager import remove_job
    account_id = session.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': '未登录账号上下文'}), 401
    try:
        deleted = delete_schedule(sid, account_id=account_id)
        if not deleted:
            return jsonify({'success': False, 'error': '计划不存在或无权限'}), 404
        remove_job(sid)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/schedules/<int:sid>/toggle', methods=['POST'])
@login_required
def api_schedules_toggle(sid):
    from database import toggle_schedule, get_schedule
    from scheduler_manager import add_job, remove_job
    account_id = session.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': '未登录账号上下文'}), 401
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    try:
        updated = toggle_schedule(sid, enabled, account_id=account_id)
        if not updated:
            return jsonify({'success': False, 'error': '计划不存在或无权限'}), 404
        schedule = get_schedule(sid)
        remove_job(sid)
        if enabled:
            add_job(schedule)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/schedules/<int:sid>/run', methods=['POST'])
@login_required
def api_schedules_run(sid):
    from database import get_schedule
    from scheduler_manager import execute_schedule
    account_id = session.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': '未登录账号上下文'}), 401
    try:
        s = get_schedule(sid, account_id=account_id)
        if not s:
            return jsonify({'success': False, 'error': '计划不存在或无权限'}), 404
        execute_schedule(sid)
        s = get_schedule(sid)
        if s and s.get('last_status') == 'error':
            return jsonify({'success': False, 'error': s.get('last_error', '执行失败')}), 400
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


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
        return jsonify({'success': False, 'error': str(e)}), 400


if __name__ == '__main__':
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(app.config['DATA_DIR'], exist_ok=True)
    app.run(host='0.0.0.0', port=8080, debug=False)
