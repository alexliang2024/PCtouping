# -*- coding: utf-8 -*-
"""高层投屏控制器：把 设备 + HTTP 服务 + ffmpeg 串起来。"""
import os
import re
import socket
import threading
import time
import urllib.parse

from . import audio as audio_mod
from . import screen as screen_mod
from . import upnp
from .config import DEFAULT_PORT, MAX_PORT_TRIES
from .server import StreamServer, Handler, guess_mime

# 分辨率预设 -> (最大宽, 最大高)；None 表示不限制（原始分辨率）
RESOLUTION_PRESETS = {
    "auto": None,
    "原": None,
    "原始": None,
    "1080": (1920, 1080),
    "720": (1280, 720),
    "540": (960, 540),
    "360": (640, 360),
}


def parse_resolution(res):
    if res is None:
        return None
    r = str(res).strip().lower()
    if r in RESOLUTION_PRESETS:
        return RESOLUTION_PRESETS[r]
    # 允许 "1280x720" 或 "1280x720@30" 形式
    m = re.match(r"^(\d+)x(\d+)$", r)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def get_local_ip(target_ip="192.168.5.6"):
    """通过向目标 IP 建立 UDP 连接获取本机局域网 IP。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 9))
        return s.getsockname()[0]
    except OSError:
        pass
    finally:
        s.close()
    try:
        host = socket.gethostbyname_ex(socket.gethostname())[2]
        for h in host:
            if h.startswith("192.168.") or h.startswith("10.") or h.startswith("172."):
                return h
    except OSError:
        pass
    return "127.0.0.1"


class CastSession:
    """一次投屏会话：选定渲染器，管理 HTTP 服务与 ffmpeg 进程。"""

    def __init__(self, device, port=DEFAULT_PORT, log=print):
        self.device = device
        self.port = port
        self.log = log
        self.server = None
        self.server_thread = None
        self.live_proc = None
        self.hls_dir = None
        self.current_uri = None
        self.custom_input = None
        self.audio_device = None
        self.max_size = None
        self._audio_restore = None
        self._lock = threading.Lock()

    # ---------------- 服务器 ----------------
    def ensure_server(self):
        if self.server:
            return self.server
        with self._lock:
            if self.server:
                return self.server
            last_err = None
            for p in range(self.port, self.port + MAX_PORT_TRIES):
                try:
                    srv = StreamServer(("0.0.0.0", p), Handler)
                    srv.log = self.log
                    self.server = srv
                    self.port = p
                    break
                except OSError as e:
                    last_err = e
                    continue
            if not self.server:
                raise RuntimeError(f"无法监听端口 {self.port}-{self.port + MAX_PORT_TRIES - 1}: {last_err}")
            self.server_thread = threading.Thread(
                target=self.server.serve_forever, daemon=True, name="cast-httpd")
            self.server_thread.start()
            self.log(f"HTTP 服务已启动: 端口 {self.port}")
        return self.server

    def pc_url(self, path):
        host = urllib.parse.urlsplit(self.device.base_url).hostname or "192.168.5.6"
        ip = get_local_ip(host)
        return f"http://{ip}:{self.port}{path}"

    def close_server(self):
        with self._lock:
            srv, self.server = self.server, None
        if srv:
            srv.shutdown_server()

    # ---------------- 媒体文件投屏 ----------------
    def cast_media(self, filepath, title=None):
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        mime = guess_mime(filepath)
        self.ensure_server()
        key = os.path.basename(filepath)
        self.server.register_media(key, filepath, mime)
        uri = self.pc_url(f"/media/{urllib.parse.quote(key)}")
        self._push_uri(uri, title or os.path.basename(filepath), mime,
                       f"媒体文件: {filepath}")
        return uri

    # ---------------- 网络链接投屏 ----------------
    def cast_url(self, url, title=None, mime=None):
        """把网络链接(URL)推给机顶盒播放：可以是 http(s) 视频/直播流/m3u8 等。"""
        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("网络链接必须以 http:// 或 https:// 开头")
        if not mime:
            path = urllib.parse.urlsplit(url).path
            mime = guess_mime(path)
            if path.endswith(".m3u8"):
                mime = "video/m3u8"
            elif not mime or mime == "application/octet-stream":
                mime = "video/mp4"
        self._push_uri(url, title or "网络媒体", mime, f"网络链接: {url}")
        return url

    def _push_uri(self, uri, title, mime, desc):
        meta = upnp.build_didl_lite(uri, title, mime)
        self.log(f"推送: {desc}  (类型 {mime})")
        self.device.set_av_transport_uri(uri, meta)
        time.sleep(0.3)
        self.device.play()
        self.current_uri = uri

    # ---------------- 屏幕/窗口投屏 ----------------
    def _build_stream_cmd(self, mode, title, fps, bitrate, rect, output, hls_dir=None,
                          custom_input=None, audio_device=None, encoder="auto"):
        mw, mh = self.max_size or (None, None)
        return screen_mod.build_screen_cmd(
            mode=mode, title=title, fps=fps, bitrate=bitrate,
            rect=rect, output=output, hls_dir=hls_dir,
            custom_input=custom_input, audio_device=audio_device, encoder=encoder,
            max_width=mw, max_height=mh)

    def _resolve_audio(self, audio):
        """audio: auto | off | <设备名> -> 返回设备名或 None"""
        if audio == "off":
            return None
        if audio and audio != "auto":
            return audio
        return screen_mod.find_loopback_audio()

    def _prepare_audio(self, audio):
        if audio == "off":
            self.audio_device = None
            return
        self.audio_device = self._resolve_audio(audio)
        if self.audio_device:
            self.log(f"声音采集: {self.audio_device}（画面+声音将同步到电视）")
            if "cable" in self.audio_device.lower():
                try:
                    self._audio_restore = audio_mod.ensure_cable_default(log=self.log)
                except Exception as e:
                    self.log(f"提示: 自动切换默认播放设备失败 ({e})，"
                             "请手动在系统声音设置里把默认播放设备设为 CABLE Input")
        else:
            self.log("未找到系统声音采集设备（VB-CABLE / 立体声混音），本次仅投画面，无声")
            self.log("提示: 若电脑没有 VB-CABLE，可在声卡驱动中启用「立体声混音」录制设备，"
                     "或运行 tools\\install_vb_cable.ps1 安装免费虚拟声卡后再试")

    def cast_screen(self, mode="full", title=None, fps=15, bitrate="4M",
                    strategy="auto", rect=None, custom_input=None, audio="auto",
                    encoder="auto", resolution="auto"):
        """strategy: auto | mpegts | hls | url;  audio: auto | off | 设备名
        encoder: auto | libx264 | h264_mf/nvenc/qsv/amf
        resolution: auto/原始=不缩放; 1080/720/540/360=分辨率上限; 或 "1280x720" """
        self.custom_input = custom_input
        self.max_size = parse_resolution(resolution)
        if self.max_size:
            self.log(f"采集分辨率上限: {self.max_size[0]}x{self.max_size[1]}（更流畅，画面略糊）")
        self._prepare_audio(audio)
        self.ensure_server()
        if strategy == "auto":
            try:
                sink = " ".join(self.device.protocol_sink()).lower()
            except Exception:
                sink = ""
            has_ts = any(x in sink for x in ("video/mp2t", "video/vnd.dlna.mpeg-tts",
                                             "video/ts", "video/mpeg"))
            has_m3u8 = "m3u8" in sink or "mpegurl" in sink
            strategy = "mpegts" if has_ts else ("hls" if has_m3u8 else "mpegts")
        if strategy == "url":
            return self._start_stream_only(mode, title, fps, bitrate, rect, encoder)
        if strategy == "mpegts":
            return self._cast_mpegts(mode, title, fps, bitrate, rect, encoder)
        if strategy == "hls":
            return self._cast_hls(mode, title, fps, bitrate, rect, encoder)
        raise ValueError(f"未知策略: {strategy}")

    def _live_path(self):
        # 每次会话用唯一路径，避免渲染器缓存/复用旧的 /live.ts
        return f"/live_{int(time.time() * 1000)}.ts"

    def _cast_mpegts(self, mode, title, fps, bitrate, rect, encoder):
        """MPEG-TS 实时流。硬件编码播放失败时自动改用软件编码重试，再失败转 HLS。"""
        enc = screen_mod.pick_video_encoder(force=encoder)
        for attempt in range(2):
            self.server.register_live(
                lambda: self._build_stream_cmd(mode, title, fps, bitrate, rect, "mpegts",
                                               custom_input=self.custom_input,
                                               audio_device=self.audio_device,
                                               encoder=enc)[0])
            uri = self.pc_url(self._live_path())
            meta = upnp.build_didl_lite(uri, "PC 屏幕直播", "video/mp2t",
                                        protocol_info="http-get:*:video/mp2t:*")
            self.server.bytes_streamed = 0
            self.log(f"推送实时流: {uri} (编码 {enc})")
            try:
                self.device.set_av_transport_uri(uri, meta)
                time.sleep(0.3)
                self.device.play()
            except upnp.UPnPError as e:
                self.log(f"MPEG-TS 推流失败 ({e.code}: {e.description})")
                if enc != "libx264":
                    enc = "libx264"
                    continue
                break
            self.current_uri = uri
            if self._check_playing(wait=8, min_bytes=200 * 1024):
                return uri
            if enc != "libx264":
                self.log(f"硬件编码({enc})未能在电视上开始播放，自动改用软件编码重试...")
                if self.server:
                    self.server.abort_live()
                enc = "libx264"
                time.sleep(0.6)
                continue
            break
        self.log("MPEG-TS 未能开始播放，自动尝试 HLS 分片流...")
        return self._cast_hls(mode, title, fps, bitrate, rect, "libx264")

    def _cast_hls(self, mode, title, fps, bitrate, rect, encoder):
        """HLS 分片流。硬件编码失败时退回软件编码。"""
        enc = screen_mod.pick_video_encoder(force=encoder)
        for attempt in range(2):
            if not self.hls_dir:
                self.hls_dir = screen_mod.make_hls_dir()
            self.server.register_hls(self.hls_dir)
            cmd, _ = self._build_stream_cmd(mode, title, fps, bitrate, rect, "hls",
                                            hls_dir=self.hls_dir, custom_input=self.custom_input,
                                            audio_device=self.audio_device, encoder=enc)
            self.log(f"视频编码: {enc}")
            self.live_proc = self._spawn(cmd)
            uri = self.pc_url("/hls/live.m3u8")
            meta = upnp.build_didl_lite(uri, "PC 屏幕直播", "video/m3u8",
                                        protocol_info="http-get:*:video/m3u8:*")
            self.log(f"推送 HLS 流: {uri}")
            self.server.bytes_streamed = 0
            time.sleep(1.5)  # 等 ffmpeg 生成前几个分片
            self.device.set_av_transport_uri(uri, meta)
            time.sleep(0.3)
            self.device.play()
            self.current_uri = uri
            if self._check_playing(wait=8, min_bytes=200 * 1024):
                return uri
            if enc != "libx264":
                self.log(f"硬件编码({enc}) HLS 未开始播放，改用软件编码重试...")
                if self.live_proc:
                    try:
                        self.live_proc.kill()
                    except Exception:
                        pass
                    self.live_proc = None
                enc = "libx264"
                continue
            break
        return uri

    def _start_stream_only(self, mode, title, fps, bitrate, rect, encoder):
        """只启动流，不推送 DLNA，返回 URL（供机顶盒 VLC/浏览器手动打开）。"""
        self.server.register_live(
            lambda: self._build_stream_cmd(mode, title, fps, bitrate, rect, "mpegts",
                                           custom_input=self.custom_input,
                                           audio_device=self.audio_device,
                                           encoder=encoder)[0])
        uri = self.pc_url(self._live_path())
        self.current_uri = uri
        return uri

    def _spawn(self, cmd):
        import subprocess
        self.log("启动 ffmpeg: " + " ".join(cmd))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return proc

    def _check_playing(self, wait=8.0, min_bytes=200 * 1024):
        """判断渲染器是否真的在播放：状态 PLAYING 且确实从我们这里拉取到了数据。
        min_bytes 门槛用于排除渲染器"乐观报告 PLAYING 但实际没拉到流"的情况。"""
        end = time.time() + wait
        last_state = ""
        saw_transition = False
        while time.time() < end:
            try:
                info = self.device.get_transport_info()
                last_state = info.get("state", "")
            except Exception:
                last_state = ""
            served = getattr(self.server, "bytes_streamed", 0) if self.server else 0
            if last_state == "PLAYING" and served >= min_bytes:
                self.log(f"渲染器状态: PLAYING，已实际拉取 {served // 1024}KB —— 投屏成功 ✓")
                return True
            if last_state == "TRANSITIONING":
                saw_transition = True
            time.sleep(0.8)
        if last_state == "PLAYING":
            self.log(f"提醒: 渲染器报告 PLAYING 但没有实际拉取到流（已拉取 "
                     f"{getattr(self.server, 'bytes_streamed', 0) // 1024}KB），"
                     "可能播放失败，正在自动切换方案...")
        elif saw_transition:
            self.log("提醒: 渲染器一直在缓冲(TRANSITIONING)未进入播放。")
        else:
            self.log(f"提醒: 渲染器当前状态为 {last_state or '未知'}，"
                     "如果电视上没有画面，可改用 VLC 手动打开流 URL (见 README)。")
        return False

    # ---------------- 停止 ----------------
    def stop(self):
        if self.device:
            try:
                self.device.stop()
                self.log("已向渲染器发送 Stop")
            except Exception:
                pass
        proc, self.live_proc = self.live_proc, None
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        if self.server:
            try:
                self.server.abort_live()
            except Exception:
                pass
            self.close_server()
        if self.hls_dir:
            screen_mod.cleanup_hls_dir(self.hls_dir)
            self.hls_dir = None
        restore, self._audio_restore = self._audio_restore, None
        if restore:
            try:
                audio_mod.restore_default(restore[0])
                self.log("已恢复默认播放设备")
            except Exception:
                pass
        self.current_uri = None
        self.log("已停止投屏")


def ensure_device(target_ip, device_index=None, name_filter=None, timeout=4):
    """发现设备并按参数选择一个渲染器。"""
    devices = upnp.discover(target=target_ip, timeout=timeout)
    renderers = [d for d in devices if d.is_media_renderer()]
    if not renderers:
        raise RuntimeError("没有发现 DLNA 渲染器，请检查机顶盒与电脑是否在同一网段")
    if name_filter:
        d = upnp.find_renderer_by_name(renderers, name_filter)
        if d:
            return d
    if device_index is not None and 0 <= device_index < len(renderers):
        return renderers[device_index]
    return upnp.pick_best_renderer(renderers)