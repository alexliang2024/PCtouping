# 在没有 VB-CABLE 的电脑上安装免费虚拟声卡（用于"系统声音同步投到电视"）。
# 需要管理员权限 + 联网下载。安装后重启一次，然后程序会自动检测到 CABLE Output 采集设备。
# 用法(管理员 PowerShell):  .\install_vb_cable.ps1
$ErrorActionPreference = "Stop"
$zip = Join-Path $env:TEMP "VBCABLE_Driver_Pack.zip"
$dir = Join-Path $env:TEMP "VBCABLE_Driver_Pack"
$url = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip"

Write-Host "下载 VB-CABLE ..."
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
Expand-Archive -Path $zip -DestinationPath $dir -Force
$setup = Get-ChildItem $dir -Recurse -Filter "VBCABLE_Setup*.exe" | Select-Object -First 1
if (-not $setup) { throw "未在压缩包中找到安装程序" }
Write-Host "启动安装程序（请在弹出的窗口点 Install/安装）: $($setup.FullName)"
Start-Process -FilePath $setup.FullName -Wait
Write-Host "完成。建议重启电脑，然后在 声音设置 中把默认播放设备设为 CABLE Input（程序也会自动切换）。"