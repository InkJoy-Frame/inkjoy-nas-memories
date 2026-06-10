# InkJoy Manager - Build & Export for ARM (NAS) on x86 Windows
# Cross-platform build: x86 host -> ARM64 target (Docker Buildx)

param(
    [string]$Tag = "inkjoy-manager:latest",
    [string]$OutputFile = "inkjoy-manager-arm64.tar",
    [string]$Platform = "linux/arm64"
)

$ErrorActionPreference = "Stop"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " InkJoy Manager - ARM64 Build (for NAS)"        -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Platform: $Platform" -ForegroundColor Gray
Write-Host ""

# Check buildx
$buildxCheck = docker buildx version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Buildx not found. Use Docker Desktop or Docker Engine 20.10+ with buildx." -ForegroundColor Red
    exit 1
}

# Create buildx builder if needed
Write-Host "[0/3] Checking buildx builder..." -ForegroundColor Yellow
$builderExists = docker buildx ls | Select-String "multiarch"
if (-not $builderExists) {
    Write-Host "Creating multiarch builder..." -ForegroundColor Gray
    docker buildx create --name multiarch --use 2>$null
    if ($LASTEXITCODE -ne 0) {
        docker buildx use default 2>$null
    }
}

# Build for ARM64 and export to tar
Write-Host ""
Write-Host "[1/2] Building Docker image for ARM64..." -ForegroundColor Yellow
Write-Host "     (First run may be slow, downloading ARM base image)" -ForegroundColor Gray
docker buildx build --platform $Platform -t $Tag --output "type=docker,dest=$OutputFile" .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "Build OK: $Tag (ARM64)" -ForegroundColor Green

$size = [math]::Round((Get-Item $OutputFile).Length / 1MB, 1)
Write-Host "Exported: $OutputFile  ($size MB)" -ForegroundColor Green

Write-Host ""
Write-Host "[2/2] Done!" -ForegroundColor Green
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Next steps on NAS:" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Copy $OutputFile to NAS (SCP or file share)"
Write-Host ""
Write-Host "2. SSH into NAS and run:"
Write-Host "   docker load -i $OutputFile" -ForegroundColor White
Write-Host ""
Write-Host "3. Start container (see README for QNAP/Synology commands)"
Write-Host ""
Write-Host "4. Open browser: http://<NAS_IP>:8080" -ForegroundColor Cyan
Write-Host ""
