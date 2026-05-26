# NAS 极简版重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 NAS 版从多页面（dashboard + albums + schedules）重构为单页极简应用，相册为核心概念，设备绑定内嵌于相册卡片中。

**Architecture:** 删除 dashboard/upload/cloud-albums 模板和路由，新建 `home.html` 单页模板，合并相册管理 + 设备绑定 + 快速推送。后端 API 基本不变，仅增加 `nas_album_id` 外键关联相册和 schedule，以及级联删除。

**Tech Stack:** Flask + Jinja2 + SQLite + Vanilla JS + Bootstrap 5（仅 CSS 工具类）+ APScheduler

**Spec:** `docs/superpowers/specs/2026-05-26-minimal-nas-redesign.md`

---

### Task 1: 数据库 — 增加 nas_album_id 外键 + 级联删除

**Files:**
- Modify: `database.py:7-71` (init_db schema migration)
- Modify: `database.py:154-171` (create_schedule)
- Modify: `database.py:283-291` (delete_nas_album)

- [ ] **Step 1: 在 init_db 中增加 nas_album_id 列迁移**

在 `database.py` 的 `init_db` 函数中，现有列迁移逻辑（第 58-70 行）之后，增加 schedules 表的列迁移：

```python
# 在 nas_albums 列迁移之后，增加 schedules 表的 nas_album_id 迁移
sched_cols = {r[1] for r in conn.execute('PRAGMA table_info(schedules)').fetchall()}

if 'nas_album_id' not in sched_cols:
    conn.execute('ALTER TABLE schedules ADD COLUMN nas_album_id INTEGER')

conn.commit()
conn.close()
```

- [ ] **Step 2: 修改 create_schedule 支持 nas_album_id**

修改 `database.py:create_schedule`，在 INSERT 语句中增加 `nas_album_id` 字段：

```python
def create_schedule(data):
    conn = get_db()
    cur = conn.execute(
        '''INSERT INTO schedules
           (name, account_id, device_id, device_name, device_width, device_height,
            folder_path, schedule_time, resize_mode, enabled, nas_album_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (
            data['name'], data['account_id'], data['device_id'],
            data.get('device_name'), data.get('device_width'), data.get('device_height'),
            data['folder_path'], data['schedule_time'],
            data.get('resize_mode', 'crop'), 1,
            data.get('nas_album_id'),
        ),
    )
    schedule_id = cur.lastrowid
    conn.commit()
    conn.close()
    return schedule_id
```

- [ ] **Step 3: 增加 get_schedules_by_album 查询函数**

在 `database.py` 末尾（`update_schedule_run_status` 之后）添加：

```python
def get_schedules_by_album(album_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM schedules WHERE nas_album_id = ? ORDER BY created_at DESC',
        (album_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: 修改 delete_nas_album 增加级联删除**

修改 `database.py:delete_nas_album`，在删除相册前先删除关联的 schedules：

```python
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
```

- [ ] **Step 5: 手动验证**

启动应用，登录后在浏览器 console 确认无报错。在 SQLite 中确认 schedules 表有 `nas_album_id` 列：

```
python -c "import sqlite3; c=sqlite3.connect('data/inkjoy.db'); print([r[1] for r in c.execute('PRAGMA table_info(schedules)').fetchall()])"
```

- [ ] **Step 6: 提交**

```bash
git add database.py
git commit -m "数据库增加 nas_album_id 外键，支持相册-任务关联和级联删除"
```

---

### Task 2: 后端路由清理 — 删除废弃路由 + 新建首页

**Files:**
- Modify: `app.py:137-238` (pages section)
- Modify: `app.py:257-278` (cloud albums API)

- [ ] **Step 1: 修改首页路由**

将 `app.py` 中的 `index` 和 `dashboard` 路由替换为：

```python
@app.route('/')
def index():
    if 'token' in session:
        return render_template('home.html')
    return redirect(url_for('login'))
```

- [ ] **Step 2: 删除废弃的页面路由**

删除以下路由函数：
- `dashboard()` (第 217-220 行)
- `albums()` (第 222-226 行)
- `upload()` (第 228-232 行)
- `schedules()` (第 234-238 行)

- [ ] **Step 3: 删除云端相册 API 路由**

删除以下函数：
- `api_cloud_albums()` (第 257-265 行)
- `api_cloud_album_photos()` (第 268-278 行)

- [ ] **Step 4: 修改 delete_nas_album 路由增加 scheduler job 清理**

修改 `app.py:api_nas_albums_delete` 函数，删除相册时同时移除关联的 scheduler jobs：

```python
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
        return jsonify({'success': False, 'error': '相册不存在或无权限'}), 404

    for s in schedules:
        remove_job(s['id'])

    return jsonify({'success': True})
```

- [ ] **Step 5: 增加按相册获取 schedules 的 API**

在 schedules API 区域末尾添加，供前端按相册分组加载绑定：

```python
@app.route('/api/nas-albums/<int:album_id>/schedules')
@login_required
def api_nas_album_schedules(album_id):
    from database import get_schedules_by_album
    return jsonify({'success': True, 'schedules': get_schedules_by_album(album_id)})
```

- [ ] **Step 6: 提交**

```bash
git add app.py
git commit -m "清理废弃路由(dashboard/upload/cloud-albums)，首页改为渲染 home.html"
```

---

### Task 3: base.html — 删除侧边栏 + 导航栏居中

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: 重写 base.html**

将 `templates/base.html` 中 `{% if session.get('token') %}` 块内的内容替换为（去掉侧边栏，导航栏内容居中）：

```html
{% if session.get('token') %}
<!-- 顶部导航栏 -->
<header class="navbar">
  <div class="navbar-inner">
    <a class="navbar-brand" href="/" title="Home">
      <img src="{{ url_for('static', filename='images/logo-white.svg') }}" alt="InkJoy" class="navbar-logo-img">
    </a>
    <div class="navbar-right">
      <button class="lang-btn" id="langBtn"
              onclick="setLang(getLang()==='en'?'zh':'en')">中文</button>
      <span class="server-tag">
        {% if session.server_key == 'global' %}Global{% else %}China{% endif %}
      </span>
      <a class="btn-logout" href="{{ url_for('logout') }}" data-i18n="nav.logout">Sign Out</a>
    </div>
  </div>
</header>

<!-- 主内容区（无侧边栏） -->
<main class="page-content">
  {% block content %}{% endblock %}
</main>

{% endif %}
```

- [ ] **Step 2: 提交**

```bash
git add templates/base.html
git commit -m "base.html: 删除侧边栏，导航栏内容居中"
```

---

### Task 4: CSS 重构 — 删除旧样式 + 新增单页布局

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: 删除侧边栏相关 CSS**

删除以下 CSS 区块（通过注释标识）：
- `/* ── 主布局（侧边栏 + 内容区）*/` 整个区块（`.app-layout` 到 `.main-content`，约第 306-357 行）
- `/* ── 侧边栏响应式 */` 整个区块（约第 359-399 行）

- [ ] **Step 2: 删除 dashboard 相关 CSS**

删除以下区块：
- `/* ── 设备网格 */`（`.device-grid`、`.home-device-grid`，约第 438-444 行）
- `/* ── 设备卡片（画框风格）*/` 整个区块（约第 446-605 行）
- `/* ── Home Hint 区 */` 整个区块（约第 607-673 行）
- `/* ── Push Panel 锁定层 */` 整个区块（约第 675-715 行）
- `/* ── 图片来源选择器 */` 整个区块（约第 717-767 行）
- `/* ── 图标按钮 */` 区块（约第 769-784 行）
- `/* ── 辅助按钮 */` 区块（约第 786-801 行）

- [ ] **Step 3: 删除定时任务卡片 CSS**

删除 `/* ── 定时任务卡片 */` 区块（`.schedule-card`，约第 867-872 行）。

- [ ] **Step 4: 新增单页布局 CSS**

在导航栏 CSS 之后、相册管理 CSS 之前添加新的布局样式：

```css
/* ── 导航栏居中 ────────────────────────────────────────────────────────── */
.navbar-inner {
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  align-items: center;
}
.navbar-inner .navbar-right { margin-left: auto; }

/* ── 单页主内容区 ──────────────────────────────────────────────────────── */
.page-content {
  max-width: 800px;
  margin: 0 auto;
  padding: 1.25rem 1rem;
  min-height: calc(100vh - 60px);
}

/* ── 内容区块卡片 ──────────────────────────────────────────────────────── */
.content-card {
  background: #fff;
  border-radius: .75rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
  margin-bottom: 1.25rem;
}
.content-card-header {
  padding: .875rem 1rem;
  border-bottom: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.content-card-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--ink);
}
.content-card-subtitle {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}
.content-card-body { padding: .75rem 1rem; }

/* ── 相册子卡片（含设备绑定） ──────────────────────────────────────────── */
.album-item {
  border: 1px solid #e8e8e8;
  border-radius: .5rem;
  margin-bottom: .75rem;
  overflow: hidden;
}
.album-item-header {
  padding: .625rem .875rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fafffe;
}
.album-item-info {
  display: flex;
  align-items: center;
  gap: .625rem;
  min-width: 0;
}
.album-item-thumb {
  width: 44px;
  height: 44px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: center;
}
.album-item-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.album-item-name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.album-item-meta {
  font-size: 11px;
  color: #999;
}
.album-item-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* ── 设备绑定行 ────────────────────────────────────────────────────────── */
.binding-list { padding: 0 .875rem .625rem; }
.binding-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: .5rem .625rem;
  margin-top: .375rem;
  background: #f8faf9;
  border-radius: 6px;
  border-left: 3px solid #4caf50;
}
.binding-row.disabled {
  opacity: .5;
  border-left-color: #ccc;
}
.binding-device { font-size: 12px; font-weight: 500; }
.binding-detail { font-size: 11px; color: #888; }
.binding-status {
  display: flex;
  align-items: center;
  gap: .5rem;
  flex-shrink: 0;
}
.binding-empty {
  text-align: center;
  padding: .5rem;
  color: #bbb;
  font-size: 11px;
}

/* ── 新建相册虚线入口 ──────────────────────────────────────────────────── */
.album-add-card {
  border: 2px dashed #d0d0d0;
  border-radius: .5rem;
  padding: 1rem;
  text-align: center;
  cursor: pointer;
  color: #999;
  font-size: 13px;
  transition: border-color .2s, color .2s;
}
.album-add-card:hover {
  border-color: var(--ink);
  color: var(--ink);
}

/* ── 快速推送区 ────────────────────────────────────────────────────────── */
.quick-push-entry {
  border: 2px dashed #c8e6c9;
  border-radius: .5rem;
  padding: 1.25rem;
  text-align: center;
  cursor: pointer;
  transition: border-color .2s, background .2s;
}
.quick-push-entry:hover {
  border-color: var(--ink);
  background: #f0f7f4;
}

/* ── 小型操作按钮 ──────────────────────────────────────────────────────── */
.btn-sm-outline {
  background: none;
  border: 1px solid var(--ink);
  color: var(--ink);
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.btn-sm-outline:hover {
  background: var(--ink);
  color: #fff;
}
.btn-sm-primary {
  background: var(--ink);
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background .15s;
}
.btn-sm-primary:hover { background: var(--ink-dark); }

/* ── 向导步骤 ──────────────────────────────────────────────────────────── */
.wizard-step {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #eee;
}
.wizard-step-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  margin-bottom: .5rem;
}

/* ── 设备多选网格 ──────────────────────────────────────────────────────── */
.device-pick-grid {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
}
.device-pick-item {
  border: 1.5px solid #e2e8f0;
  border-radius: .5rem;
  padding: .5rem .75rem;
  cursor: pointer;
  font-size: 12px;
  transition: border-color .15s, background .15s;
  display: flex;
  align-items: center;
  gap: .375rem;
}
.device-pick-item:hover { border-color: var(--ink); }
.device-pick-item.picked {
  border-color: var(--ink);
  background: var(--ink-light);
  font-weight: 600;
}

/* ── 响应式（移动端）─────────────────────────────────────────────────── */
@media (max-width: 767px) {
  .page-content { padding: .75rem .5rem; }
  .content-card-header { flex-wrap: wrap; gap: .5rem; }
  .album-item-header { flex-wrap: wrap; gap: .5rem; }
}
```

- [ ] **Step 5: 提交**

```bash
git add static/css/style.css
git commit -m "CSS: 删除侧边栏/dashboard/设备卡片样式，新增单页布局样式"
```

---

### Task 5: i18n — 清理废弃 key + 新增绑定流程 key

**Files:**
- Modify: `static/js/i18n.js`

- [ ] **Step 1: 删除废弃的 i18n key**

从 `I18N.en` 和 `I18N.zh` 中删除以下前缀的所有 key：
- `dash.*`（dashboard 相关，全部删除）
- `up.*`（upload 相关，全部删除）

- [ ] **Step 2: 新增首页和绑定流程 key**

在 `I18N.en` 的 Albums 区域之后，添加：

```javascript
/* ── Home ─────────────────────────────────── */
'home.albums.title':       'NAS Albums',
'home.albums.subtitle':    'Select local folders as albums. Bind a frame to auto-push photos daily.',
'home.albums.new':         '+ New Album',
'home.push.title':         'Quick Push',
'home.push.subtitle':      'Push a single photo to your frame — no schedule needed.',
'home.push.browse':        'Browse & Push',

/* ── Binding ──────────────────────────────── */
'bind.add':                '+ Bind Frame',
'bind.modal.title':        'Bind Frame',
'bind.device':             'Target Frame',
'bind.device.ph':          '-- Select Frame --',
'bind.time':               'Daily Push Time',
'bind.resize':             'Fill Mode',
'bind.empty':              'No frame bound yet. Click the button above to add one.',
'bind.daily':              'Daily',
'bind.next':               'Next:',

/* ── Wizard ───────────────────────────────── */
'wizard.title':            'New Album',
'wizard.step.name':        'Album Name',
'wizard.step.folders':     'Select Folders',
'wizard.step.devices':     'Bind Frames (optional)',
'wizard.step.devices.hint':'Select frames to auto-push. You can skip this step.',
'wizard.step.schedule':    'Push Settings',
'wizard.skip':             'Skip, create album only',
'wizard.create':           'Create',

/* ── Album menu ───────────────────────────── */
'albums.menu.edit_folders': 'Edit Folders',
```

对应的中文 key 添加到 `I18N.zh`：

```javascript
/* ── Home ─────────────────────────────────── */
'home.albums.title':       'NAS 相册',
'home.albums.subtitle':    '选择本地文件夹作为相册，绑定相框后自动每天推送',
'home.albums.new':         '+ 新建相册',
'home.push.title':         '快速推送',
'home.push.subtitle':      '临时推一张照片到相框，不走定时任务',
'home.push.browse':        '浏览并推送',

/* ── Binding ──────────────────────────────── */
'bind.add':                '+ 绑定相框',
'bind.modal.title':        '绑定相框',
'bind.device':             '目标相框',
'bind.device.ph':          '-- 选择相框 --',
'bind.time':               '每天推送时间',
'bind.resize':             '图片填充方式',
'bind.empty':              '尚未绑定相框，点击上方按钮添加',
'bind.daily':              '每天',
'bind.next':               '下次：',

/* ── Wizard ───────────────────────────────── */
'wizard.title':            '新建相册',
'wizard.step.name':        '相册名称',
'wizard.step.folders':     '选择文件夹',
'wizard.step.devices':     '绑定相框（可选）',
'wizard.step.devices.hint':'选择要自动推送的相框，也可以跳过此步。',
'wizard.step.schedule':    '推送设置',
'wizard.skip':             '跳过，仅创建相册',
'wizard.create':           '创建',

/* ── Album menu ───────────────────────────── */
'albums.menu.edit_folders': '编辑文件夹',
```

- [ ] **Step 3: 提交**

```bash
git add static/js/i18n.js
git commit -m "i18n: 删除 dashboard/upload key，新增首页和绑定流程 key"
```

---

### Task 6: home.html — 页面骨架 + 相册列表渲染

**Files:**
- Create: `templates/home.html`

- [ ] **Step 1: 创建 home.html 页面骨架**

创建 `templates/home.html`，包含两个区块的 HTML 结构 + 相册列表加载和渲染逻辑。

页面结构：

```
{% extends 'base.html' %}
{% block content %}

  <!-- 区块 1: NAS 相册 -->
  <div class="content-card">
    <div class="content-card-header">
      <div>
        <div class="content-card-title" data-i18n="home.albums.title">NAS Albums</div>
        <div class="content-card-subtitle" data-i18n="home.albums.subtitle">...</div>
      </div>
      <button class="btn-sm-primary" onclick="openWizard()" data-i18n="home.albums.new">+ New Album</button>
    </div>
    <div class="content-card-body" id="albumList">
      <!-- JS 动态渲染相册子卡片 -->
    </div>
  </div>

  <!-- 区块 2: 快速推送 -->
  <div class="content-card">
    <div class="content-card-header">
      <div>
        <div class="content-card-title" data-i18n="home.push.title">Quick Push</div>
        <div class="content-card-subtitle" data-i18n="home.push.subtitle">...</div>
      </div>
    </div>
    <div class="content-card-body">
      <div class="quick-push-entry" onclick="openQuickPush()" data-i18n="home.push.browse">Browse & Push</div>
    </div>
  </div>

  <!-- Modal 容器（ink-modal 复用） -->
  <div id="inkModal" class="ink-modal-overlay" style="display:none" onclick="if(event.target===this)inkModalCancel()">
    <div class="ink-modal-box">
      <div class="ink-modal-title" id="inkModalTitle"></div>
      <div class="ink-modal-body" id="inkModalBody"></div>
      <div class="ink-modal-footer" id="inkModalFooter"></div>
    </div>
  </div>

  <!-- Lightbox -->
  <div id="photoLightbox" class="photo-lightbox d-none" onclick="closeLightbox()">
    <img id="lightboxImg" src="" alt="">
  </div>

{% endblock %}
{% block scripts %}
<script>
// ── 全局状态 ──
let albumsData = [];
let schedulerJobsCache = {};

// ── 工具函数 ──
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ── 相册列表加载 ──
async function loadAlbums() { ... }
function renderAlbums() { ... }
function renderAlbumCard(album) { ... }
function renderBindingRow(schedule) { ... }

// ── 初始化 ──
loadAlbums();
</script>
{% endblock %}
```

关键实现细节：

**`loadAlbums()`**：并行请求 `/api/nas-albums` 和 `/api/scheduler/status`，将 scheduler 的 next_run 信息缓存到 `schedulerJobsCache`。然后对每个相册请求 `/api/nas-albums/<id>/schedules` 获取绑定列表。

**`renderAlbumCard(album)`**：渲染一个相册子卡片，包含：
- 头部：缩略图 + 名称 + 照片数 + 「绑定相框」按钮 + 菜单按钮
- 绑定列表：遍历 `album.schedules`，每个渲染为 `binding-row`
- 无绑定时显示 `binding-empty` 提示

**`renderBindingRow(schedule)`**：一行显示设备名、时间、填充模式、下次执行、状态标签、开关。

- [ ] **Step 2: 手动验证**

启动 dev server，登录后确认：
1. 首页展示相册列表（如果有已建相册）
2. 每个相册卡片下显示绑定列表（可能为空）
3. 快速推送区块可见
4. 无 JS 报错

- [ ] **Step 3: 提交**

```bash
git add templates/home.html
git commit -m "创建 home.html 单页骨架：相册列表 + 设备绑定行 + 快速推送区块"
```

---

### Task 7: home.html — 新建相册一站式向导

**Files:**
- Modify: `templates/home.html`（在 `<script>` 中追加向导逻辑）

- [ ] **Step 1: 实现向导 modal**

在 home.html 的 `<script>` 中添加 `openWizard()` 函数。向导分步向下延展，在一个 modal 中完成：

1. 输入相册名称（复用 `ink-modal-input`）
2. 点击"下一步" → 展开文件夹选择器（复用现有 `picker` 对象 + `browseFolders` 逻辑，从 albums.html 搬入）
3. 选完文件夹点击"下一步" → 展开设备多选网格（`device-pick-grid`，从 `/api/devices` 加载）+ 推送时间/填充模式选择
4. 点击"创建" → POST `/api/nas-albums` 创建相册，如果选了设备则批量 POST `/api/schedules` 创建绑定

需要搬入的代码（从 albums.html）：
- `picker` 对象（状态管理）
- `showFolderPicker()` → 适配为向导的第 2 步
- `browseFolders()` → 不变
- `toggleFolderSelection()` / `refreshAllChecks()` / `updatePickerOkBtn()` → 不变
- `toggleIncludeSubfolders()` / `toggleFilterSystemDirs()` → 不变

需要搬入的代码（从 schedules.html）：
- `getDevices()` + `devicesCache` + 设备缓存逻辑

设备多选用 `device-pick-grid` 中的 `device-pick-item`，点击切换 `.picked` 类。

「跳过，仅创建相册」按钮在设备选择步骤中可见，点击后直接创建相册（无绑定）。

- [ ] **Step 2: 手动验证**

1. 点击「新建相册」按钮
2. 输入名称 → 下一步
3. 文件夹选择器正常工作 → 下一步
4. 设备列表加载正常，可多选
5. 设置时间和填充模式
6. 点击「创建」→ 相册出现在列表中，绑定行正确显示
7. 测试「跳过」→ 相册创建成功但无绑定

- [ ] **Step 3: 提交**

```bash
git add templates/home.html
git commit -m "实现新建相册一站式向导：名称→文件夹→设备多选→推送设置"
```

---

### Task 8: home.html — 已有相册操作（绑定/菜单/开关/执行）

**Files:**
- Modify: `templates/home.html`（在 `<script>` 中追加）

- [ ] **Step 1: 实现「绑定相框」modal**

`addBinding(albumId)` 函数：弹 modal，内容为设备下拉（排除该相册已绑定的设备）+ 时间选择 + 填充模式选择。确认后 POST `/api/schedules`（带 `nas_album_id`），刷新相册列表。

- [ ] **Step 2: 实现绑定行操作**

从 schedules.html 搬入并适配：
- `toggleBinding(scheduleId, enabled)` → 调用 `/api/schedules/<id>/toggle`
- `runBinding(scheduleId, btn)` → 调用 `/api/schedules/<id>/run`
- `editBinding(schedule)` → 弹 modal 修改时间/填充模式/设备，调用 `/api/schedules/<id>` PUT
- `deleteBinding(scheduleId, deviceName)` → 确认后调用 `/api/schedules/<id>` DELETE

- [ ] **Step 3: 实现相册菜单**

`showAlbumMenu(event, albumId, albumName)` 函数，弹出下拉菜单：
- 重命名 → 调用 `inkPrompt`，PUT `/api/nas-albums/<id>`
- 编辑文件夹 → 打开文件夹选择器（复用向导的选择器），选完后需要新 API 或复用 PUT
- 删除相册 → 调用 `inkConfirm`，DELETE `/api/nas-albums/<id>`（后端已处理级联删除）

- [ ] **Step 4: 手动验证**

1. 点击「绑定相框」→ 设备下拉正常 → 确认 → 绑定行出现
2. 开关切换 → 调度器启用/禁用
3. 「立即执行」→ 按钮变转圈 → 成功反馈
4. 菜单「重命名」→ 名称更新
5. 菜单「删除」→ 相册和关联绑定一起消失

- [ ] **Step 5: 提交**

```bash
git add templates/home.html
git commit -m "实现相册操作：绑定相框、开关/执行/编辑/删除绑定、相册菜单"
```

---

### Task 9: home.html — 快速推送

**Files:**
- Modify: `templates/home.html`（在 `<script>` 中追加）

- [ ] **Step 1: 实现快速推送 modal**

`openQuickPush()` 函数：弹一个较大的 modal（`max-width: 560px`）。

Modal 布局：
- 顶部：已建相册作为标签（小药丸按钮），点击切换照片源
- 中部：照片网格（复用 `renderPhotoGrid` 逻辑）或文件浏览器（复用 `browseFolders` 逻辑）
- 底部：选中照片预览 + 设备多选（`device-pick-grid`）+ 推送按钮

推送逻辑：
1. 选中照片后，底部出现设备选择和推送按钮
2. 对于 NAS 相册中的照片：读取相对路径，POST `/api/upload` 时先 GET `/api/image?path=...` 获取完整图片
3. 对于文件浏览器中的照片：同上
4. 实际推送：构造 FormData（`device_id` + 通过 fetch 获取的图片 blob 作为 `file`），POST `/api/upload`

从现有代码搬入：
- `openAlbum()` / `renderPhotoGrid()` → 用于展示相册照片
- `openLightbox()` / `closeLightbox()` → 照片预览

- [ ] **Step 2: 手动验证**

1. 点击「快速推送」→ modal 打开
2. 点击相册标签 → 照片网格加载
3. 点击文件浏览入口 → 可浏览 NAS 目录
4. 选中一张照片 → 底部出现设备选择
5. 选设备 → 点推送 → 成功

- [ ] **Step 3: 提交**

```bash
git add templates/home.html
git commit -m "实现快速推送：相册选图/文件浏览器选图 → 选设备 → 推送"
```

---

### Task 10: 删除旧模板文件

**Files:**
- Delete: `templates/dashboard.html`
- Delete: `templates/upload.html`
- Delete: `templates/schedules.html`
- Delete: `templates/albums.html`

- [ ] **Step 1: 删除旧模板**

```bash
git rm templates/dashboard.html templates/upload.html templates/schedules.html templates/albums.html
```

- [ ] **Step 2: 手动验证**

启动 dev server，确认：
1. 登录后正确渲染 home.html
2. 所有功能正常（相册列表、向导、绑定、快速推送）
3. 无模板找不到的 500 错误
4. 访问旧路径（`/dashboard`、`/albums`、`/schedules`）返回 404（非 500）

- [ ] **Step 3: 提交**

```bash
git commit -m "删除旧模板文件(dashboard/upload/schedules/albums)"
```

---

### Task 11: 端到端手动测试

- [ ] **Step 1: 完整流程验证**

按照以下场景逐一测试：

1. **新用户流程**：登录 → 看到空的相册列表 + 快速推送 → 点新建相册 → 走完向导 → 相册出现并带绑定
2. **管理流程**：重命名相册 → 删除绑定 → 添加新绑定 → 删除整个相册（确认绑定一起消失）
3. **快速推送**：从相册选图推送 → 从文件浏览器选图推送
4. **开关和执行**：禁用绑定 → 重新启用 → 立即执行一次
5. **响应式**：手机宽度（375px）下所有功能可用
6. **语言切换**：中英文切换后所有文本正确
7. **登出/登入**：退出后重新登录，数据不丢失

- [ ] **Step 2: 修复发现的问题**

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "NAS 极简版重构完成：单页布局、相册+设备绑定合并、快速推送"
```
