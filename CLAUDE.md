# InkJoy NAS Manager

## 项目定位

NAS 上运行的 Docker 化 Web 应用，从用户指定的照片目录随机选图，定时推送到 InkJoy 墨水屏相框。
与 [InkJoy Studio](../InkJoy_webtool/) 共享设计语言（logo、色系），但功能子集不同——本项目专注 NAS 定时推送场景。

## 技术栈

Flask + SQLite + APScheduler + Pillow，前端无框架（Vanilla JS + Bootstrap 5 辅助）。

## 前端布局

- **导航栏**：顶部 60px 粘性导航栏（logo + 语言切换 + 服务器标签 + 退出）
- **侧边栏**：左侧 200px 深绿背景导航（相册管理、定时任务），手机端变为顶部横条标签栏
- **首页（dashboard）**：画框风格设备卡片（选中交互）+ 推送面板（本地文件浏览 / 上传）
- **相册管理**：方案 B 分区布局（NAS 相册 + 云端相册），自定义 modal（对齐 webtool 样式）
- **登录页**：独立于 Bootstrap，使用 `#login-page` 作用域的自定义 CSS

设备卡片的视觉设计（木框 + 缩略图 + 状态行 + 电池图标）与 InkJoy Studio 对齐。

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

这与 InkJoy Studio 的前端并行检测逻辑对齐，区别仅在执行位置（后端 vs 前端）。

### 登录页独立于 Bootstrap

`templates/login.html` 不加载 Bootstrap，使用 `#login-page` 作用域的自定义 CSS（从 webtool 移植）。
其余页面仍加载 Bootstrap 5，但 dashboard 首页以自定义 CSS 为主。

### 相册管理（NAS 相册 + 云端相册）

`/albums` 页面分两个区块展示相册（方案 B 分区布局）：
- **NAS 相册**：用户多选 NAS 本地文件夹作为相册源，元数据存 `nas_albums` 表。创建流程两步：输入名称 → 文件夹浏览器多选目录（勾选确认模式）。
- **云端相册**：从 InkJoy API 拉取，只读浏览。不提供创建云端相册的入口。

弹窗使用自定义 `ink-modal`（`.ink-modal-overlay` + `.ink-modal-box`），不用 Bootstrap Modal，样式对齐 webtool。

#### NAS 相册数据模型

`nas_albums` 表核心字段：
- `selected_folders TEXT`：JSON 数组，存储用户勾选的所有目录相对路径
- `filter_system_dirs INTEGER`：是否排除 NAS 系统目录（`@eaDir`、`.recycle` 等）
- `folder_path TEXT`：向后兼容字段（= `selected_folders[0]`）

扫描逻辑：`_scan_selected_folders()` 对每个选中目录递归 `os.walk`，去重后返回照片列表。`_get_album_photos()` 兼容新老格式（老数据无 `selected_folders` 时回退到 `folder_path`）。

#### 文件夹选择器 UI

前端状态集中在 `picker` 对象（`albums.html`）。两个 toggle 开关（右端对齐，webtool 风格）：
- **包含子目录里的照片**（默认开）：勾选父目录时自动勾选可见子目录，仅影响 UI 默认勾选行为
- **排除干扰项目**（默认开）：tooltip 说明跳过的系统目录列表

### 认证与 401 处理

上游 InkJoy API 返回 401 时，`_handle_api_error()` 清 session 并返回 401。
前端 `base.html` 有全局 fetch 拦截器，`/api/` 路径收到 401 自动跳转登录页。
与 webtool 的 `apiFetch` 拦截逻辑对齐。

## 已知问题

- `app.py:auto_restore_session` 调用 `database.get_saved_account()`，但该函数尚未在 `database.py` 中实现。

## 环境变量

见 `README.md` 的 Environment Variables 表。

## 关联项目

- `C:\Users\Liu_Lei\PycharmProjects\InkJoy_webtool` — InkJoy Studio（Web 版管理工具，登录页设计来源）
