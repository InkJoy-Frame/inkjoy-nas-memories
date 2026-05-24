# InkJoy 双版本架构策略

日期：2026-05-23

## 背景

InkJoy 有两个面向用户的 Web 应用：

|          | NAS 版                               | Web 版                      |
| -------- | ----------------------------------- | -------------------------- |
| **仓库**   | `InkJoy-Frame/inkjoy-nas-memories`  | `inkjoy-platform/web-tool` |
| **技术栈**  | Python Flask + SQLite + APScheduler | Vanilla JS SPA + Vite      |
| **部署**   | Docker → NAS 设备                     | Cloudflare Pages           |
| **核心场景** | 本地文件浏览 + 定时轮播推送                     | 云端相册管理 + 手动/自动推送           |

两者共享登录、设备管理、图片推送等业务逻辑，但实现语言不同（Python vs JavaScript），无法直接共享代码。

## 核心决策

**独立仓库，渐进式融合。**

不采用分支方案（Python 和 JS 之间开分支无法合并），不采用 monorepo（当前收益不抵复杂度）。

## Phase 1：独立迭代（当前阶段）

两个项目各自独立开发和部署。共享的是设计语言和业务逻辑概念，不是代码。

### NAS 版功能范围

- 本地文件浏览（`/api/browse`）
- 推送图片到相框（`/api/upload`）
- APScheduler 定时轮播（NAS 特有优势：永远在线）
- 多账号 / 多服务器管理
- 查看云端相册（只读，不上传本地文件到云端）

### Web 版功能范围

- 云端相册 CRUD + 照片上传
- 轮播策略配置（依赖云端相册）
- Canvas 自定义画布编辑器
- 手动推送图片到相框

### 保持一致的部分

- 登录流程：并行服务器检测（global / china）
- 设计语言：Logo、墨绿色系（`#1e4d3b`）、登录页视觉风格
- i18n：英文 / 中文双语

## Phase 2：融合（触发条件：NAS 版需要 Canvas）

当 NAS 版需要 Canvas 等复杂前端功能时，不重写，而是复用 web-tool 前端。

### 架构

```
Docker 容器
├── nginx
│   └── web-tool dist/        ← 静态前端（从 web-tool 构建产物引入）
│
└── Flask 后端（仅 NAS 特有 API）
    ├── GET  /api/nas/status   ← NAS 模式检测端点
    ├── GET  /api/browse       ← 本地文件浏览
    ├── CRUD /api/schedules    ← 定时任务管理
    └── POST /api/nas/upload   ← 本地文件处理 + 推送
```

### API 调用策略

- 登录、设备、相册、轮播、Canvas → **前端直接调 InkJoy OpenAPI**（和 web 版完全一致）
- 本地文件浏览、定时任务 → **调 NAS Flask 后端**

### NAS 模式检测

前端启动时 `GET /api/nas/status`：
- 成功 → NAS 模式，显示本地文件浏览、定时任务等菜单项
- 失败 → 云端模式（标准 web-tool 行为）

### 融合时的改动范围

**web-tool 前端：**
- 加入 NAS 模式检测逻辑
- 条件显示 NAS 功能菜单（文件浏览器、定时任务页）
- 新增 NAS 特有视图组件

**NAS Flask 后端：**
- 砍掉 OpenAPI 代理层（登录、设备、推送），这些由前端直接调
- 保留 NAS 特有 API（文件浏览、调度器）
- 加 nginx 配置托管静态前端
- 新增 `/api/nas/status` 端点

## 现在不需要做的

- 不统一 API 路径格式
- 不提前重构 Flask 路由
- 不引入 git submodule 或 monorepo 工具
- 不强制两个项目的 CSS 变量保持同步

## 现在值得保持的

- Flask API 端点保持 RESTful 风格
- NAS 特有逻辑（文件浏览、调度器）和 OpenAPI 代理逻辑在代码中保持分离，将来砍掉代理层时影响最小
