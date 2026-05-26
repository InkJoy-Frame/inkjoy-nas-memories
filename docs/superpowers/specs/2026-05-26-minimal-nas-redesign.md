# NAS 极简版重构设计

## 背景

NAS 版和 Web 版（webtool）功能重叠度高，用户看到两个相似但不同的界面会困惑。NAS 版的核心场景很简单：选好本地照片文件夹，绑定相框，设好定时推送，然后离开。不需要 dashboard、云端相册、侧边栏导航这些重型功能。

## 设计目标

**用户心智模型**：进来 → 建相册 → 绑相框 → 走人。

**设计原则**：
- 单页应用，无多页面导航
- 相册是唯一主体概念，设备绑定是相册的属性（不暴露"定时任务"这个抽象概念）
- 一站式向导流程，新建相册时直接完成设备绑定和推送设置

## 砍掉的功能

| 功能 | 现有文件 | 处理方式 |
|------|----------|----------|
| Dashboard（设备卡片 + 推送面板） | `dashboard.html` | 删除模板 |
| 云端相册 | `albums.html` 中的云端部分 | 从模板和 JS 中移除 |
| 侧边栏导航 | `base.html` 中的 `<nav class="sidebar">` | 删除 |
| 上传页 | `upload.html` | 删除模板 |
| 多页面路由 | `app.py` 中的 `dashboard`、`upload` 路由 | 删除 |
| 云端相册 API | `app.py` 中的 `/api/cloud-albums` | 删除 |

## 保留的功能

- 登录流程（并行服务器检测，不变）
- NAS 相册 CRUD（`/api/nas-albums/*`）
- 定时任务 CRUD（`/api/schedules/*`）— 后端不变，前端展示方式变化
- 文件浏览（`/api/browse`）
- 图片查看/缩略图（`/api/image`）
- 图片推送（`/api/upload`）
- 设备列表（`/api/devices`）
- 调度器（`/api/scheduler/*`）

## 页面结构

### 导航栏

顶部通栏深绿背景，内部内容 `max-width: 800px; margin: 0 auto` 居中对齐。内容不变：logo + 语言切换 + 服务器标签 + 退出。

### 内容区

无侧边栏，内容区居中 `max-width: 800px`，浅灰背景。两个白色圆角卡片纵向排列：

**区块 1 — NAS 相册（含设备绑定）**

标题行：「NAS 相册」+ 副标题"选择本地文件夹作为相册，绑定相框后自动每天推送" + 「新建相册」按钮。无图标。

每个相册是一个展开的子卡片：
- 头部：封面缩略图 + 名称 + 照片数/文件夹数 + 「绑定相框」按钮 + 菜单（⋮）
- 设备绑定列表：每行显示设备名、推送时间、填充模式、下次执行时间、状态标签、开关
- 无绑定时显示提示文字
- 底部：虚线框「+ 新建相册」入口

**区块 2 — 快速推送**

标题行：「快速推送」+ 副标题"临时推一张照片到相框，不走定时任务"。无图标。

单一入口，点击后弹 modal：顶部展示已建相册作为快捷导航，下方是 NAS 文件浏览器。选中照片 → 选设备 → 推送。

## 交互流程

### 新建相册（一站式向导）

一个 modal，分步向下延展：

1. **输入相册名称**
2. **选择文件夹**：复用现有文件夹选择器（多选目录 + "包含子目录"/"排除系统目录"开关）
3. **选择相框**：设备列表多选（从 `/api/devices` 获取），可跳过（不绑定直接完成）
4. **推送设置**：每日推送时间（time picker）+ 填充模式（下拉选择：模糊填充/智能裁剪/居中裁剪）。所有选中相框共享同一设置
5. **确认**：一次请求创建相册 + 所有设备绑定（schedule）

跳过第 3 步时直接在第 2 步完成后创建相册（无绑定）。

### 为已有相册添加设备绑定

点击相册卡片上的「+ 绑定相框」：
1. 弹 modal：选设备（下拉，排除已绑定的设备）+ 推送时间 + 填充模式
2. 确认 → 创建 schedule，设备绑定行出现在相册卡片内

### 设备绑定行操作

每个绑定行支持：
- **开关**：启用/禁用（调用 `/api/schedules/<id>/toggle`）
- **点击/展开**：编辑（改时间/填充模式/设备），立即执行一次，删除绑定

### 快速推送

1. 点击快速推送区块 → 弹 modal
2. Modal 上半部分：已建相册作为快捷入口（标签或小卡片），点击后展示该相册的照片网格
3. Modal 下半部分：NAS 文件浏览器，可自由导航任意目录
4. 选中一张照片 → 底部出现设备选择器（多选） → 推送按钮
5. 推送调用 `/api/upload`

### 相册管理操作

菜单（⋮）下：
- 重命名
- 编辑文件夹（重新打开文件夹选择器）
- 删除相册（级联删除所有关联的 schedule）

## 文件变更清单

### 删除

- `templates/dashboard.html`
- `templates/upload.html`
- `templates/schedules.html`（逻辑合并到新模板）
- `templates/albums.html`（逻辑合并到新模板）

### 新建

- `templates/home.html` — 单页模板，包含相册区块 + 快速推送区块 + 所有 modal

### 修改

- `templates/base.html` — 删除侧边栏，导航栏内容居中
- `app.py` — 删除 dashboard/upload/cloud-albums 路由，`/` 登录后渲染 `home.html`
- `static/css/style.css` — 删除侧边栏/dashboard 相关样式，新增单页布局样式
- `static/js/i18n.js` — 清理废弃的 i18n key，新增相册绑定相关 key

### 不变

- `templates/login.html`
- `database.py`
- `scheduler.py`
- 后端 API 路由（NAS 相册、定时任务、文件浏览、图片、设备、调度器）

## 数据模型

后端数据模型不需要改动：

- `nas_albums` 表：存相册信息（名称、选中文件夹、过滤设置）
- `schedules` 表：存定时任务（设备、时间、文件夹路径、填充模式）

`schedules` 表增加 `nas_album_id INTEGER` 外键，显式关联相册和任务。创建绑定时写入相册 ID，`folder_path` 保留但由后端自动从相册的 `selected_folders` 带入（调度器执行时仍读 `folder_path`）。

好处：前端按相册分组查询简单，删除相册时可靠级联删除关联 schedule。数据迁移：现有 schedule 的 `nas_album_id` 设为 NULL（无关联），不影响已有定时任务运行。

## 已有功能的复用情况

| 现有组件 | 复用方式 |
|----------|----------|
| 文件夹选择器（picker 对象 + browseFolders） | 直接搬入 home.html |
| ink-modal 系统（inkModalShow/Hide/Prompt/Confirm） | 直接搬入 home.html |
| NAS 相册 CRUD JS（loadNasAlbums, renameNasAlbum, deleteNasAlbum） | 搬入并适配新布局 |
| 定时任务 CRUD JS（saveSchedule, toggleSched, delSched, runNow） | 搬入，作为设备绑定行的操作 |
| 设备加载 + 缓存（getDevices, devicesCache） | 搬入，用于新建向导和绑定 modal |
| 相册照片浏览（openAlbum, renderPhotoGrid, lightbox） | 搬入，用于快速推送的选图 |
