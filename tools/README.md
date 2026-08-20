# tools 目录说明

- `open_firewall.ps1` — 以管理员身份运行，为 Python 打开 8090~8099 端口的入站规则（机顶盒需要访问
  电脑上的 HTTP 服务才能拉取媒体/直播流）。第一次运行时如果 Windows 弹出防火墙提示，请选择"允许访问"。
- `set_default_audio.ps1` — 切换/恢复系统默认播放设备（VB-CABLE 声音投屏用）。
  一般由程序自动调用，无需手动运行；也可手动测试：
  `powershell -File set_default_audio.ps1 -GetDefault`（查看默认设备）、
  `-DeviceId <ID>`（设置默认设备）。
- `install_vlc_apk.ps1` — 可选。把 VLC for Android 装到机顶盒，作为"屏幕投屏"的兜底方案
  （当 DLNA 实时推流在部分盒子上不稳定时，用「仅URL(VLC)」策略 + VLC 手动打开流地址）。
  需要机顶盒开启 ADB 调试，且 ADB 端口 5555 可访问。