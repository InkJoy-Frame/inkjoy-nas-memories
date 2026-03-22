# InkJoy Manager Manual / 使用手册

This manual is for end users and operators.  
本手册面向最终用户和部署维护人员。

---

## EN

### 1) Local Docker Usage (Windows)

#### Start

```powershell
docker-compose up --build
```

Open `http://localhost:8080` in your browser.

#### Stop

```powershell
docker-compose down
```

### 2) Deploy to NAS

#### Step 1: Build and export image (on Windows PC)

**x86 NAS (Intel/AMD, linux/amd64)**

```powershell
.\build-export-x86.ps1
```

Generates: `inkjoy-manager-x86.tar`

**ARM64 NAS (QNAP/Synology)**

```powershell
.\build-export-arm.ps1
```

Generates: `inkjoy-manager-arm64.tar`

#### Step 2: Copy image tar to NAS

```powershell
scp inkjoy-manager-x86.tar admin@<NAS_IP>:/share/Container/
```

#### Step 3: Load image on NAS

```bash
ssh admin@<NAS_IP>
docker load -i /share/Container/inkjoy-manager-x86.tar
```

### 3) Run container on NAS (CLI)

For the host path mapped to `/images`, **use a folder on your NAS where you already store pictures** (or where you want the app’s library to live). The paths below are examples—adjust them to match your shared-folder layout.

#### QNAP example

```bash
mkdir -p /share/Container/inkjoy/images /share/Container/inkjoy/data

docker run -d \
  --name inkjoy-manager \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /share/Container/inkjoy/images:/images \
  -v /share/Container/inkjoy/data:/data \
  -e TZ=Asia/Shanghai \
  -e SECRET_KEY=change-this-secret \
  inkjoy-manager:latest
```

#### Synology example

```bash
mkdir -p /volume1/docker/inkjoy/images /volume1/docker/inkjoy/data

docker run -d \
  --name inkjoy-manager \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /volume1/docker/inkjoy/images:/images \
  -v /volume1/docker/inkjoy/data:/data \
  -e TZ=Asia/Shanghai \
  -e SECRET_KEY=change-this-secret \
  inkjoy-manager:latest
```

Then open: `http://<NAS_IP>:8080`

### 4) Recommended volume mapping

- `/images`: image library
- `/data`: database (`inkjoy.db`)

If `/data` is not mapped to persistent NAS storage, account and schedule data will be lost after container recreation.

### 5) Remove container/image quickly

```bash
docker stop inkjoy-manager && docker rm inkjoy-manager
docker rmi inkjoy-manager:latest
```

---

## 中文

### 1）本地 Docker 使用（Windows）

#### 启动

```powershell
docker-compose up --build
```

浏览器访问：`http://localhost:8080`

#### 停止

```powershell
docker-compose down
```

### 2）部署到 NAS

#### 第一步：在 Windows 电脑构建并导出镜像

**x86 NAS（Intel/AMD，linux/amd64）**

```powershell
.\build-export-x86.ps1
```

生成：`inkjoy-manager-x86.tar`

**ARM64 NAS（威联通/群晖）**

```powershell
.\build-export-arm.ps1
```

生成：`inkjoy-manager-arm64.tar`

#### 第二步：把镜像 tar 复制到 NAS

```powershell
scp inkjoy-manager-x86.tar admin@<NAS_IP>:/share/Container/
```

#### 第三步：在 NAS 上导入镜像

```bash
ssh admin@<NAS_IP>
docker load -i /share/Container/inkjoy-manager-x86.tar
```

### 3）在 NAS 上启动容器（命令行）

映射到容器内 `/images` 的 NAS 主机目录，**建议选用你在 NAS 上实际存放图片的位置**（或你希望作为图库根目录的文件夹）。下文路径仅为示例，请按你的共享文件夹与习惯自行修改。

#### QNAP 示例

```bash
mkdir -p /share/Container/inkjoy/images /share/Container/inkjoy/data

docker run -d \
  --name inkjoy-manager \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /share/Container/inkjoy/images:/images \
  -v /share/Container/inkjoy/data:/data \
  -e TZ=Asia/Shanghai \
  -e SECRET_KEY=请修改为随机字符串 \
  inkjoy-manager:latest
```

#### Synology 示例

```bash
mkdir -p /volume1/docker/inkjoy/images /volume1/docker/inkjoy/data

docker run -d \
  --name inkjoy-manager \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /volume1/docker/inkjoy/images:/images \
  -v /volume1/docker/inkjoy/data:/data \
  -e TZ=Asia/Shanghai \
  -e SECRET_KEY=请修改为随机字符串 \
  inkjoy-manager:latest
```

然后访问：`http://<NAS_IP>:8080`

### 4）建议的卷挂载

- `/images`：图片库目录
- `/data`：数据库目录（`inkjoy.db`）

如果不把 `/data` 挂载到 NAS 持久化目录，容器重建后账号与定时任务会丢失。

### 5）快速移除容器与镜像

```bash
docker stop inkjoy-manager && docker rm inkjoy-manager
docker rmi inkjoy-manager:latest
```

