# InkJoy NAS Manager

## 项目定位

NAS 上运行的 Docker 化 Web 应用，从用户指定的照片目录随机选图，定时推送到 InkJoy 墨水屏相框。
与 [InkJoy Studio](../webtool/) 共享设计语言（logo、色系），但定位不同——本项目是极简的"设好就走"工具，用户建好相册、绑好相框后就不需要常驻页面。

## 技术栈

Flask + SQLite + APScheduler + Pillow，前端无框架（Vanilla JS + Bootstrap 5 辅助）。

## 前端布局（极简单页版）

- **导航栏**：顶部 60px 粘性导航栏（logo + 语言切换 + 服务器标签 + 退出），内容居中 800px
- **单页内容**：无侧边栏，内容区 `max-width: 800px` 居中，两个白色卡片纵向堆叠
  - **自动播放**：自动播放子卡片列表，每个条目展开显示设备绑定行（设备名 + 推送时间 + 状态 + 开关）
  - **快速推送**：临时推一张照片到相框（从已有播放源选图或浏览 NAS 文件夹）
- **登录页**：独立于 Bootstrap，使用 `#login-page` 作用域的自定义 CSS

## 核心概念：自动播放

用户的心智模型：**自动播放 = 照片源 + 相框绑定**。登录后就像设置一个"自动播放"任务，设好就走。

- 新建自动播放是全页面四步向导：选文件夹 → 选相框 → 推送设置 → 起名字（自动填充默认名）
- 四步各为独立卡片，相框必选（使用 webtool 风格的木框设备卡片）
- 每个自动播放卡片上可以「+ 添加相框」，绑定更多设备
- 删除自动播放时级联删除所有关联的定时任务

## 双版本架构策略

详见 `docs/superpowers/specs/2026-05-23-dual-version-architecture-design.md`。
核心决策：独立仓库、渐进式融合。NAS 版将来需要 Canvas 时，复用 web-tool 前端而非重写。

## 本地运行（无需 Docker）

```powershell
pip install -r requirements.txt
$env:IMAGES_DIR = "<本地照片目录>"
$env:DATA_DIR = "./data"
$env:FLASK_DEBUG = "1"
python app.py
```

`FLASK_DEBUG=1` 开启 debug 模式（热重载 + 模板自动刷新）。

浏览器访问 `http://localhost:8080`。需要 InkJoy 账号和至少一台已绑定相框。

## 关键设计决策

### 登录流程（并行服务器检测）

用户只输入邮箱+密码，后端 `ThreadPoolExecutor` 并行尝试所有 InkJoy 服务器（global / china）：
- 1 个命中 → 直接登录
- 多个命中 → 返回 `{conflict: true, servers: [...]}` 由前端展示下拉选择
- 0 命中 → 登录失败

### 登录页独立于 Bootstrap

`templates/login.html` 不加载 Bootstrap，使用 `#login-page` 作用域的自定义 CSS（从 webtool 移植）。

### 数据模型

**`nas_albums` 表**核心字段：
- `selected_folders TEXT`：JSON 数组，存储用户勾选的所有目录相对路径
- `filter_system_dirs INTEGER`：是否排除 NAS 系统目录（`@eaDir`、`.recycle` 等）
- `folder_path TEXT`：向后兼容字段（= `selected_folders[0]`）

**`schedules` 表**核心字段：
- `nas_album_id INTEGER`：关联 NAS 相册的外键（2026-05-26 新增）
- `device_id`、`schedule_time`、`resize_mode`、`enabled` 等调度参数
- 删除相册时通过 `nas_album_id` 级联删除

### 相册-设备绑定关系

前端通过 `GET /api/nas-albums/<id>/schedules` 获取某相册的所有设备绑定。创建绑定时 POST `/api/schedules` 并带 `nas_album_id`。调度器执行时仍读 `folder_path` 字段。

### 文件夹选择器 UI

前端状态集中在 `picker` 对象（`home.html`）。两个 toggle 开关：
- **包含子目录里的照片**（默认开）：勾选父目录时自动勾选可见子目录
- **排除干扰项目**（默认开）：跳过 `@eaDir`、`.recycle` 等系统目录

### 新建向导（全页面）

点击"+ 新建"时，隐藏 `#mainView`（两个内容卡片），显示 `#wizardPage`（全页面表单）。
四步各为独立白色卡片（选文件夹 → 选相框 → 推送设置 → 起名字），全部可见，用户填完后点"完成"。
第 4 步名称会根据已选文件夹和相框自动生成默认值（如 "Palm Pre照片 → 大的"），用户可覆盖。

### 自定义 Modal 系统

弹窗使用 `ink-modal`（`.ink-modal-overlay` + `.ink-modal-box`），不用 Bootstrap Modal，样式对齐 webtool。
JS API：`inkModalShow(title, bodyHtml, actions)`、`inkPrompt()`、`inkConfirm()`。仅用于确认/重命名等小型对话框，新建向导已不使用 Modal。

### 认证与 401 处理

上游 InkJoy API 返回 401 时，`_handle_api_error()` 清 session 并返回 401。
前端 `base.html` 有全局 fetch 拦截器，`/api/` 路径收到 401 自动跳转登录页。

## 文件结构

```
templates/
  base.html     — 公共骨架（导航栏 + page-content 容器）
  login.html    — 登录页（独立 CSS）
  home.html     — 唯一的业务页面（自动播放列表 + 新建向导 + 绑定操作 + 快速推送）
static/
  css/style.css — 全部样式
  js/i18n.js    — 中英文翻译
app.py          — Flask 路由 + API
database.py     — SQLite 操作
scheduler_manager.py — APScheduler 定时执行
api_client.py   — InkJoy 上游 API 客户端
```

## 已知问题

- `app.py:auto_restore_session` 调用 `database.get_saved_account()`，但该函数尚未在 `database.py` 中实现。

## 环境变量

见 `README.md` 的 Environment Variables 表。

## 关联项目

- `C:\Users\Liu_Lei\PycharmProjects\InkJoy\webtool` — InkJoy Studio（Web 版管理工具，登录页设计来源）
