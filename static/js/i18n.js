/* InkJoy Manager — i18n module
 * Usage:  t('key')          → translated string
 *         getLang()          → 'en' | 'zh'
 *         setLang('zh')      → persist + reload
 * HTML:   data-i18n="key"          → textContent
 *         data-i18n-ph="key"       → placeholder
 *         data-i18n-title="key"    → title attr
 */

const I18N = {
  en: {
    /* ── Nav ──────────────────────────────────────── */
    'nav.brand':     'InkJoy Manager',
    'nav.manage':    'Manage',
    'nav.devices':   'Devices',
    'nav.albums':    'Albums',
    'nav.upload':    'Upload',
    'nav.schedules': 'Schedules',
    'nav.logout':    'Sign Out',

    /* ── Login ────────────────────────────────────── */
    'login.tagline':     'Turn your NAS into a living photo stream for InkJoy Frame.',
    'login.email':       'Email',
    'login.email.ph':    'your@email.com',
    'login.pwd':         'Password',
    'login.pwd.ph':      'Password',
    'login.submit':      'Login',
    'login.conflict':    'Account found on multiple servers — please select:',
    'login.err.net':     'Network error, please retry',
    'login.err.default': 'Login failed, check email/password',

    /* ── Dashboard ────────────────────────────────── */
    'dash.title':          'My Frames',
    'dash.hint.select':    'Click frames to select',
    'dash.btn.clear':      'Clear',
    'dash.refresh':        'Refresh',
    'dash.loading':        'Loading devices…',
    'dash.empty':          'No devices bound',
    'dash.empty.hint':     'Please bind a device in the InkJoy App first',
    'dash.online':         'Online',
    'dash.offline':        'Offline',
    'dash.btn.upload':     'Upload Image',
    'dash.btn.sched':      'Set Schedule',
    'dash.err.retry':      'Retry',
    'dash.push.title':     'Push Photo',
    'dash.push.lock':      'Select frames above first',
    'dash.push.local':     'NAS Photos',
    'dash.push.local.hint':'Browse local folders',
    'dash.push.upload':    'Upload Photo',
    'dash.push.upload.hint':'Drag & drop or click',
    'dash.push.done':      'Push complete!',

    /* ── Albums ───────────────────────────────────── */
    'albums.nas':              'NAS Albums',
    'albums.nas.new':          'New NAS Album',
    'albums.cloud':            'Cloud Albums',
    'albums.cloud.empty':      'No cloud albums',
    'albums.back':             'Albums',
    'albums.photos.empty':     'No photos in this album',
    'albums.menu.rename':      'Rename',
    'albums.menu.delete':      'Delete',
    'albums.menu.rename.prompt': 'New album name:',
    'albums.menu.delete.confirm': 'Delete album "{name}"?\nThis only removes the shortcut, not the files.',
    'albums.modal.title':      'New NAS Album',
    'albums.modal.name':       'Album Name',
    'albums.modal.name.ph':    'e.g. Family Trip 2025',
    'albums.modal.folder':     'Folder',
    'albums.modal.folder.ph':  'Click Browse to select…',
    'albums.modal.browse':     'Browse',
    'albums.modal.select':        'Select',
    'albums.modal.select.folder': 'Select This Folder',
    'albums.modal.images.found':  'images found',
    'albums.modal.required':   'Please enter album name and select a folder',
    'albums.modal.cancel':     'Cancel',
    'albums.modal.ok':         'OK',
    'albums.modal.create':     'Create',
    'albums.modal.folder.title': 'Select Folder',
    'albums.folder.root':      'Photos Root',

    /* ── Upload ───────────────────────────────────── */
    'up.title':          'Upload Image to Device',
    'up.tab.local':      'Local File',
    'up.tab.server':     'Image Library',
    'up.drop.title':     'Click to Select Image',
    'up.drop.sub':       'Or drag an image here',
    'up.drop.formats':   'JPG / PNG / WEBP / BMP',
    'up.path.ph':        'Type path and press Enter…',
    'up.crop.title':     'Crop',
    'up.crop.ph1':       'Select an image from the left panel',
    'up.crop.ph2':       'Drag to adjust crop box · scroll to zoom',
    'up.device.title':   'Target Device',
    'up.device.loading': 'Loading…',
    'up.device.select':  '-- Select Device --',
    'up.device.none':    'No devices available',
    'up.info.title':     'Device Info',
    'up.info.res':       'Resolution',
    'up.info.ratio':     'Aspect Ratio',
    'up.btn.upload':     'Upload to Device',
    'up.btn.uploading':  'Uploading…',
    'up.ok':             'Upload successful!',
    'up.err.nodev':      'Please select a target device',
    'up.rotate.ccw':     'Rotate 90° CCW',
    'up.rotate.cw':      'Rotate 90° CW',
    'up.reset':          'Reset',
    'up.lock':           'Lock / Unlock aspect ratio',
    'up.parent':         'Parent Directory',
    'up.empty.folder':   'This folder is empty',

    /* ── Schedules ────────────────────────────────── */
    'sched.title':        'Scheduled Tasks',
    'sched.new':          'New Task',
    'sched.loading':      'Loading…',
    'sched.empty':        'No scheduled tasks yet',
    'sched.create.first': 'Create First Task',
    'sched.modal.new':    'New Scheduled Task',
    'sched.modal.edit':   'Edit Scheduled Task',
    'sched.f.name':       'Task Name',
    'sched.f.name.ph':    'e.g. Living Room Daily Shuffle',
    'sched.f.account':    'Account',
    'sched.f.device':     'Target Device',
    'sched.f.time':       'Daily Execute Time',
    'sched.f.folder':     'Image Folder',
    'sched.f.folder.ph':  'Relative path, e.g. nature or photos/2024',
    'sched.f.folder.hint':'Path in image library. A random image will be sent each run.',
    'sched.f.resize':      'Fill Mode',
    'sched.resize.blur':  'Blur Fill (frosted glass padding)',
    'sched.resize.isfr':  'ISFR Smart Crop (upload original)',
    'sched.resize.crop':  'Center Crop (fills screen)',
    'sched.btn.save':     'Save',
    'sched.btn.cancel':   'Cancel',
    'sched.btn.run':      'Run Now',
    'sched.btn.running':  'Running…',
    'sched.btn.ran':      'Success',
    'sched.btn.edit':     'Edit',
    'sched.btn.delete':   'Delete',
    'sched.badge.ok':     'Last: OK',
    'sched.badge.err':    'Last: Failed',
    'sched.badge.never':  'Never run',
    'sched.daily':        'Daily at',
    'sched.last.run':     'Last run:',
    'sched.resize.blur.short': 'Blur',
    'sched.resize.isfr.short': 'ISFR',
    'sched.resize.crop.short': 'Crop',
    'sched.select.account':    '-- Select Account --',
    'sched.select.device':     '-- Select Device --',
    'sched.del.confirm':       'Delete task "{name}"?\nThis cannot be undone.',
    'sched.required':          'Please fill in all required fields (*)',
    'sched.save.err':          'Save failed: ',
    'sched.req.err':           'Request failed: ',
    'sched.run.err':           'Run failed: ',
    'sched.del.err':           'Delete failed: ',
    'sched.fb.title':          'Select Folder',
    'sched.fb.selected':       'Selected:',
    'sched.fb.root':           '/ (root)',
    'sched.fb.confirm':        'Select This Folder',
    'sched.fb.parent':         'Parent Directory',
    'sched.fb.nofolders':      'No sub-folders',
    'sched.fb.browse':         'Browse',
    'sched.resolution.hint':   'Resolution: ',
    'sched.status.btn':        'Scheduler Status',
    'sched.status.title':      'Scheduler Status',
    'sched.status.reload':     'Reload Jobs',
    'sched.next.run':          'Next run:',
    'sched.not.registered':    'Not registered in scheduler! Try Reload Jobs.',
  },

  zh: {
    /* ── Nav ──────────────────────────────────────── */
    'nav.brand':     'InkJoy 管理器',
    'nav.manage':    '管理',
    'nav.devices':   '设备',
    'nav.albums':    '相册管理',
    'nav.upload':    '上传',
    'nav.schedules': '定时任务',
    'nav.logout':    '退出',

    /* ── Login ────────────────────────────────────── */
    'login.tagline':     '让 NAS 成为 InkJoy 相框上的流动相册。',
    'login.email':       '邮箱',
    'login.email.ph':    'your@email.com',
    'login.pwd':         '密码',
    'login.pwd.ph':      '密码',
    'login.submit':      '登录',
    'login.conflict':    '账号在多个服务器上找到，请选择：',
    'login.err.net':     '网络错误，请重试',
    'login.err.default': '登录失败，请检查账号密码',

    /* ── Dashboard ────────────────────────────────── */
    'dash.title':          '我的相框',
    'dash.hint.select':    '点击相框进行选择',
    'dash.btn.clear':      '清除',
    'dash.refresh':        '刷新',
    'dash.loading':        '正在获取设备列表…',
    'dash.empty':          '暂无绑定设备',
    'dash.empty.hint':     '请先在 InkJoy App 中绑定设备',
    'dash.online':         '在线',
    'dash.offline':        '离线',
    'dash.btn.upload':     '上传图片',
    'dash.btn.sched':      '设置定时任务',
    'dash.err.retry':      '重试',
    'dash.push.title':     '推送照片',
    'dash.push.lock':      '请先在上方选择相框',
    'dash.push.local':     'NAS 相册',
    'dash.push.local.hint':'浏览本地文件夹',
    'dash.push.upload':    '上传照片',
    'dash.push.upload.hint':'拖拽或点击上传',
    'dash.push.done':      '推送完成！',

    /* ── Albums ───────────────────────────────────── */
    'albums.nas':              'NAS 相册',
    'albums.nas.new':          '新建 NAS 相册',
    'albums.cloud':            '云端相册',
    'albums.cloud.empty':      '暂无云端相册',
    'albums.back':             '相册',
    'albums.photos.empty':     '此相册没有照片',
    'albums.menu.rename':      '重命名',
    'albums.menu.delete':      '删除',
    'albums.menu.rename.prompt': '新相册名称：',
    'albums.menu.delete.confirm': '删除相册「{name}」？\n仅移除快捷方式，不删除文件。',
    'albums.modal.title':      '新建 NAS 相册',
    'albums.modal.name':       '相册名称',
    'albums.modal.name.ph':    '例：家庭旅行 2025',
    'albums.modal.folder':     '文件夹',
    'albums.modal.folder.ph':  '点击浏览选择…',
    'albums.modal.browse':     '浏览',
    'albums.modal.select':        '选择',
    'albums.modal.select.folder': '选择此文件夹',
    'albums.modal.images.found':  '张图片',
    'albums.modal.required':   '请输入相册名称并选择文件夹',
    'albums.modal.cancel':     '取消',
    'albums.modal.ok':         '确定',
    'albums.modal.create':     '创建',
    'albums.modal.folder.title': '选择文件夹',
    'albums.folder.root':      '照片根目录',

    /* ── Upload ───────────────────────────────────── */
    'up.title':          '上传图片到设备',
    'up.tab.local':      '本地文件',
    'up.tab.server':     '图片库',
    'up.drop.title':     '点击选择图片',
    'up.drop.sub':       '或将图片拖到此处',
    'up.drop.formats':   '支持 JPG / PNG / WEBP / BMP',
    'up.path.ph':        '输入路径回车跳转…',
    'up.crop.title':     '图片裁切',
    'up.crop.ph1':       '从左侧选择图片后，在此裁切',
    'up.crop.ph2':       '拖动调整裁切框 · 滚轮缩放',
    'up.device.title':   '目标设备',
    'up.device.loading': '加载中…',
    'up.device.select':  '-- 选择设备 --',
    'up.device.none':    '暂无设备',
    'up.info.title':     '设备信息',
    'up.info.res':       '分辨率',
    'up.info.ratio':     '宽高比',
    'up.btn.upload':     '上传到设备',
    'up.btn.uploading':  '上传中…',
    'up.ok':             '上传成功！',
    'up.err.nodev':      '请选择目标设备',
    'up.rotate.ccw':     '逆时针90°',
    'up.rotate.cw':      '顺时针90°',
    'up.reset':          '重置',
    'up.lock':           '锁定/解锁比例',
    'up.parent':         '上级目录',
    'up.empty.folder':   '此文件夹为空',

    /* ── Schedules ────────────────────────────────── */
    'sched.title':        '定时任务',
    'sched.new':          '新建任务',
    'sched.loading':      '加载中…',
    'sched.empty':        '还没有定时任务',
    'sched.create.first': '创建第一个任务',
    'sched.modal.new':    '新建定时任务',
    'sched.modal.edit':   '编辑定时任务',
    'sched.f.name':       '任务名称',
    'sched.f.name.ph':    '例：客厅相框每日换图',
    'sched.f.account':    '账号',
    'sched.f.device':     '目标设备',
    'sched.f.time':       '每天执行时间',
    'sched.f.folder':     '图片文件夹',
    'sched.f.folder.ph':  '相对路径，如：风景 或 照片/2024',
    'sched.f.folder.hint':'填写图片库中的文件夹路径，程序会随机选取其中的图片发送。',
    'sched.f.resize':      '图片填充方式',
    'sched.resize.blur':  '适应填充（使用毛玻璃填充周围的区域）',
    'sched.resize.isfr':  'ISFR智能裁切（本地不裁切，直接上传）',
    'sched.resize.crop':  '中心裁切（铺满屏幕，裁去边缘）',
    'sched.btn.save':     '保存',
    'sched.btn.cancel':   '取消',
    'sched.btn.run':      '立即执行',
    'sched.btn.running':  '执行中…',
    'sched.btn.ran':      '执行成功',
    'sched.btn.edit':     '编辑',
    'sched.btn.delete':   '删除',
    'sched.badge.ok':     '上次成功',
    'sched.badge.err':    '上次失败',
    'sched.badge.never':  '从未运行',
    'sched.daily':        '每天',
    'sched.last.run':     '上次运行：',
    'sched.resize.blur.short': '毛玻璃',
    'sched.resize.isfr.short': 'ISFR',
    'sched.resize.crop.short': '裁切',
    'sched.select.account':    '-- 选择账号 --',
    'sched.select.device':     '-- 选择设备 --',
    'sched.del.confirm':       '确认删除任务「{name}」？\n此操作不可恢复。',
    'sched.required':          '请填写所有必填字段（标 * 项）',
    'sched.save.err':          '保存失败：',
    'sched.req.err':           '请求失败：',
    'sched.run.err':           '执行失败：',
    'sched.del.err':           '删除失败：',
    'sched.fb.title':          '选择文件夹',
    'sched.fb.selected':       '已选：',
    'sched.fb.root':           '/（根目录）',
    'sched.fb.confirm':        '选择此文件夹',
    'sched.fb.parent':         '上级目录',
    'sched.fb.nofolders':      '没有子文件夹',
    'sched.fb.browse':         '浏览',
    'sched.resolution.hint':   '分辨率：',
    'sched.status.btn':        '调度器状态',
    'sched.status.title':      '调度器运行状态',
    'sched.status.reload':     '重新加载 Jobs',
    'sched.next.run':          '下次执行：',
    'sched.not.registered':    '未在调度器中注册！请点击「重新加载 Jobs」。',
  },
};

/* ── Core helpers ─────────────────────────────────────── */
window.getLang = () => localStorage.getItem('inkjoy_lang') || 'en';

window.t = (key, vars) => {
  const lang = getLang();
  let str = I18N[lang]?.[key] ?? I18N.en?.[key] ?? key;
  if (vars) Object.entries(vars).forEach(([k, v]) => { str = str.replace(`{${k}}`, v); });
  return str;
};

window.setLang = (lang) => {
  localStorage.setItem('inkjoy_lang', lang);
  location.reload();
};

/* ── Apply to static DOM ──────────────────────────────── */
function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const v = t(el.dataset.i18n);
    if (v) el.textContent = v;
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    const v = t(el.dataset.i18nPh);
    if (v) el.placeholder = v;
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const v = t(el.dataset.i18nTitle);
    if (v) el.title = v;
  });
  // Sync lang toggle button label
  const btn = document.getElementById('langBtn');
  if (btn) btn.textContent = getLang() === 'en' ? '中文' : 'EN';
}

document.addEventListener('DOMContentLoaded', applyI18n);
