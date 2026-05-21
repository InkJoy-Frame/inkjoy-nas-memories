# InkJoy NAS Manager

## 项目定位

NAS 上运行的 Docker 化 Web 应用，从用户指定的照片目录随机选图，定时推送到 InkJoy 墨水屏相框。
与 [InkJoy Studio](../InkJoy_webtool/) 共享设计语言（logo、色系），但功能子集不同——本项目专注 NAS 定时推送场景。

## 技术栈

Flask + SQLite + APScheduler + Pillow，前端无框架（登录页自定义 CSS，其余页面 Bootstrap 5）。

## 本地运行（无需 Docker）

```powershell
pip install -r requirements.txt
$env:IMAGES_DIR = "<本地照片目录>"
$env:DATA_DIR = "./data"
python app.py
```

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
其余页面（dashboard/upload/schedules）仍用 Bootstrap 5。

## 已知问题

- `app.py:auto_restore_session` 调用 `database.get_saved_account()`，但该函数尚未在 `database.py` 中实现。

## 环境变量

见 `README.md` 的 Environment Variables 表。

## 关联项目

- `C:\Users\Liu_Lei\PycharmProjects\InkJoy_webtool` — InkJoy Studio（Web 版管理工具，登录页设计来源）
