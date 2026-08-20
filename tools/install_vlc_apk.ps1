# 可选：把 VLC for Android 安装到机顶盒（作为屏幕投屏的兜底方案）
# 前置条件:
#   1. 机顶盒开启"开发者选项 -> USB调试/ADB调试"（不同盒子路径不同，魔百和一般在"设置->通用->关于本机"连续点版本号）
#   2. 下载 VLC for Android APK，例如: https://get.videolan.org/vlc-android/  (arm64 版本，如 vlc-3.x-arm64.apk)
# 用法: .\install_vlc_apk.ps1 -BoxIp 192.168.5.6 -ApkPath C:\path\to\vlc.apk
param(
    [string]$BoxIp = "192.168.5.6",
    [string]$ApkPath = ""
)
$ErrorActionPreference = "Stop"
if (-not $ApkPath -or -not (Test-Path $ApkPath)) {
    Write-Host "请用 -ApkPath 指定 APK 文件路径，例如: .\install_vlc_apk.ps1 -ApkPath C:\tmp\vlc.apk"
    exit 1
}
Write-Host "连接 $BoxIp ..."
adb connect "${BoxIp}:5555" | Out-Host
Start-Sleep -Seconds 1
Write-Host "安装 $ApkPath ..."
adb -s "${BoxIp}:5555" install -r $ApkPath | Out-Host
Write-Host "完成。之后投屏使用「仅URL(VLC)」策略，在机顶盒 VLC 中打开程序显示的流地址即可。"