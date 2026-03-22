# InkJoy Manager - Build & Export for x86_64 NAS (linux/amd64)
# 面向 Intel/AMD 64 位 NAS：显式指定平台，避免在 ARM 主机上误打成 arm 镜像。

param(
    [string]$Tag = "inkjoy-manager:latest",
    [string]$OutputFile = "inkjoy-manager-x86.tar",
    [string]$Platform = "linux/amd64"
)

$ErrorActionPreference = "Stop"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " InkJoy Manager - x86_64 (amd64) Build & Export" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Target platform: $Platform  (x86_64 / Intel / AMD NAS)" -ForegroundColor Gray
Write-Host ""

# Preflight: Docker daemon must be running (e.g. Docker Desktop on Windows)
Write-Host "Checking Docker daemon..." -ForegroundColor Yellow
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "无法连接到 Docker 引擎（与脚本本身无关，是当前机器上 Docker 未在运行）。" -ForegroundColor Red
    Write-Host "  1. 启动 Docker Desktop，等到系统托盘里鲸鱼图标显示就绪后再运行本脚本。" -ForegroundColor Yellow
    Write-Host "  2. 若已安装但未用 Desktop：确认 Linux 引擎 / 对应服务已启动，或检查 docker context。" -ForegroundColor Yellow
    Write-Host "  错误里出现 dockerDesktopLinuxEngine 时，几乎总是 Docker Desktop 未启动或未完全启动。" -ForegroundColor Gray
    exit 1
}
Write-Host "Docker daemon OK." -ForegroundColor Green
Write-Host ""

# Step 1: Build (explicit amd64 so output matches x86 NAS expectations)
Write-Host "[1/3] Building Docker image for x86_64 (linux/amd64)..." -ForegroundColor Yellow
docker build --platform $Platform -t $Tag .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "Build OK: $Tag ($Platform)" -ForegroundColor Green

# Step 2: Export
Write-Host ""
Write-Host "[2/3] Exporting image to tar..." -ForegroundColor Yellow
docker save -o $OutputFile $Tag
if ($LASTEXITCODE -ne 0) {
    Write-Host "Export failed!" -ForegroundColor Red
    exit 1
}

$size = [math]::Round((Get-Item $OutputFile).Length / 1MB, 1)
Write-Host "Exported: $OutputFile  ($size MB)" -ForegroundColor Green

# Step 3: Instructions
Write-Host ""
Write-Host "[3/3] Done!" -ForegroundColor Green
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Next steps on your NAS:"                        -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Copy $OutputFile to NAS (SCP or file share)"
Write-Host ""
Write-Host "2. SSH into NAS and run:"
Write-Host "   docker load -i $OutputFile" -ForegroundColor White
Write-Host ""
Write-Host "3. Start the container:"   -ForegroundColor White
Write-Host '   mkdir -p /volume1/docker/inkjoy/images /volume1/docker/inkjoy/data' -ForegroundColor White
Write-Host '   docker run -d \' -ForegroundColor White
Write-Host '     --name inkjoy-manager \' -ForegroundColor White
Write-Host '     --restart unless-stopped \' -ForegroundColor White
Write-Host '     -p 8080:8080 \' -ForegroundColor White
Write-Host '     -v /volume1/docker/inkjoy/images:/images \' -ForegroundColor White
Write-Host '     -v /volume1/docker/inkjoy/data:/data \' -ForegroundColor White
Write-Host '     -e TZ=Asia/Shanghai \' -ForegroundColor White
Write-Host '     -e SECRET_KEY=change-this-secret \' -ForegroundColor White
Write-Host '     inkjoy-manager:latest' -ForegroundColor White
Write-Host ""
Write-Host '4. Open browser: http://<NAS_IP>:8080' -ForegroundColor Cyan
Write-Host ""
