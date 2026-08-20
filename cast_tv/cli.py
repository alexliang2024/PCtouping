# -*- coding: utf-8 -*-
"""命令行入口。"""
import argparse
import sys

from . import screen as screen_mod
from . import upnp
from .cast import CastSession, ensure_device
from .config import DEFAULT_TARGET_IP


def cmd_windows(args):
    wins = screen_mod.list_windows()
    print(f"共 {len(wins)} 个可见窗口：")
    for i, w in enumerate(wins):
        print(f"  [{i}] {w}")
    return 0


def cmd_discover(args):
    print(f"正在搜索局域网内的 UPnP/DLNA 设备 (目标: {args.ip or '自动'}) ...")
    devices = upnp.discover(target=args.ip, timeout=args.timeout)
    renderers = [d for d in devices if d.is_media_renderer()]
    others = [d for d in devices if not d.is_media_renderer()]
    print(f"\n发现 {len(devices)} 个设备，其中 DLNA 渲染器 {len(renderers)} 个：\n")
    for i, d in enumerate(renderers):
        sink = ""
        try:
            sink = " ".join(d.protocol_sink())[:120]
        except Exception:
            pass
        print(f"  [{i}] {d.name} | {d.model} | {d.base_url}")
        if sink:
            print(f"       支持: {sink} ...")
    for d in others:
        print(f"  [-] {d.name} | {d.model} | {d.base_url} (非渲染器)")
    if not renderers:
        print("未发现 DLNA 渲染器。")
        return 1
    return 0


def cmd_media(args):
    import time
    device = ensure_device(args.ip, args.device_index, args.device, timeout=args.timeout)
    print(f"使用渲染器: {device.friendly()}")
    sess = CastSession(device, port=args.port)
    try:
        uri = sess.cast_media(args.file, title=args.title)
        print(f"\n已推送媒体: {uri}\n正在播放... 按 Ctrl+C 停止")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        sess.stop()
    return 0


def cmd_url(args):
    import time
    device = ensure_device(args.ip, args.device_index, args.device, timeout=args.timeout)
    print(f"使用渲染器: {device.friendly()}")
    sess = CastSession(device, port=args.port)
    try:
        uri = sess.cast_url(args.url, title=args.title, mime=args.mime)
        print(f"\n已推送网络链接: {uri}\n机顶盒正在拉取播放... 按 Ctrl+C 停止")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        sess.stop()
    return 0


def cmd_screen(args):
    import time
    device = ensure_device(args.ip, args.device_index, args.device, timeout=args.timeout)
    print(f"使用渲染器: {device.friendly()}")
    sess = CastSession(device, port=args.port)
    try:
        custom_input = None
        if args.source == "lavfi":
            custom_input = ["-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate={args.fps}"]
        uri = sess.cast_screen(
            mode=args.mode, title=args.title, fps=args.fps,
            bitrate=args.bitrate, strategy=args.strategy, rect=args.rect,
            custom_input=custom_input, audio=args.audio, encoder=args.encoder,
            resolution=args.resolution)
        print(f"\n流地址: {uri}")
        if args.strategy == "url":
            print("请在机顶盒的 VLC / 浏览器中打开上面的地址（仅 URL 模式，未自动推送到 DLNA）。")
        else:
            print("按 Ctrl+C 停止投屏")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        sess.stop()
    return 0


def cmd_stop(args):
    device = ensure_device(args.ip, args.device_index, args.device, timeout=args.timeout)
    print(f"向 {device.friendly()} 发送 Stop ...")
    device.stop()
    print("完成")
    return 0


def cmd_volume(args):
    device = ensure_device(args.ip, args.device_index, args.device, timeout=args.timeout)
    if args.level is None:
        print(f"当前音量: {device.get_volume()}")
    else:
        print(f"设置音量: {device.set_volume(args.level)}")
    return 0


def _add_device_args(p):
    p.add_argument("--device-index", type=int, default=None)
    p.add_argument("--device", default=None, help="按名称过滤渲染器")
    p.add_argument("--timeout", type=float, default=3.5)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="pc2tv",
        description="PC 投屏到电视机顶盒 (DLNA/UPnP + ffmpeg)。")
    p.add_argument("--ip", default=DEFAULT_TARGET_IP, help=f"机顶盒 IP (默认 {DEFAULT_TARGET_IP})")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="发现局域网 DLNA 设备")
    d.add_argument("--timeout", type=float, default=3.5)
    d.set_defaults(fn=cmd_discover)

    w = sub.add_parser("windows", help="列出可投屏的窗口标题")
    w.set_defaults(fn=cmd_windows)

    m = sub.add_parser("media", help="投屏本地媒体文件")
    m.add_argument("--file", required=True, help="媒体文件路径 (视频/音频/图片)")
    m.add_argument("--title", default=None, help="显示在电视上的标题 (默认文件名)")
    m.add_argument("--port", type=int, default=8090)
    _add_device_args(m)
    m.set_defaults(fn=cmd_media)

    u = sub.add_parser("url", help="投屏网络链接(URL)到电视")
    u.add_argument("--url", required=True, help="http(s) 视频/直播流/m3u8 链接")
    u.add_argument("--title", default=None)
    u.add_argument("--mime", default=None, help="可选，手动指定 MIME 类型")
    u.add_argument("--port", type=int, default=8090)
    _add_device_args(u)
    u.set_defaults(fn=cmd_url)

    s = sub.add_parser("screen", help="投屏全屏或某个窗口 (ffmpeg 实时采集)")
    s.add_argument("--mode", choices=["full", "window"], default="full")
    s.add_argument("--title", default=None, help="窗口模式: 窗口标题 (可用 windows 命令查看)")
    s.add_argument("--strategy", choices=["auto", "mpegts", "hls", "url"], default="auto",
                   help="auto=根据渲染器能力选择; mpegts=实时TS流; hls=分片流; url=只启动流不推送")
    s.add_argument("--fps", type=int, default=12)
    s.add_argument("--bitrate", default="2M")
    s.add_argument("--rect", default=None, help="采集区域 WxH+X+Y，如 1920x1080+0+0 (默认全桌面)")
    s.add_argument("--source", choices=["desktop", "lavfi"], default="desktop",
                   help="desktop=真实屏幕采集; lavfi=测试信号源(仅测试用)")
    s.add_argument("--audio", default="auto",
                   help="声音采集: auto=自动检测(VB-CABLE/立体声混音); off=不采集; 或直接给设备名")
    s.add_argument("--encoder", default="auto",
                   help="视频编码: auto=自动选硬件(h264_mf优先), 失败会自动退回软编; libx264=软编; 或指定编码器")
    s.add_argument("--resolution", default="auto",
                   help="采集分辨率上限: auto/原始=不缩放; 1080/720/540/360=越小越流畅越糊; 或 1280x720")
    s.add_argument("--port", type=int, default=8090)
    _add_device_args(s)
    s.set_defaults(fn=cmd_screen)

    st = sub.add_parser("stop", help="向渲染器发送 Stop")
    _add_device_args(st)
    st.set_defaults(fn=cmd_stop)

    v = sub.add_parser("volume", help="获取/设置渲染器音量")
    v.add_argument("--level", type=int, default=None)
    _add_device_args(v)
    v.set_defaults(fn=cmd_volume)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())