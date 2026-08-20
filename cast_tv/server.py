# -*- coding: utf-8 -*-
"""本地 HTTP 服务：媒体文件 (带 Range) + 实时 MPEG-TS 直播流 + HLS。"""
import os
import re
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import DLNA_HEADERS, MIME_MAP


def guess_mime(path):
    ext = os.path.splitext(path)[1].lower()
    return MIME_MAP.get(ext, "application/octet-stream")


class StreamServer(ThreadingHTTPServer):
    """管理媒体文件与直播流的 HTTP 服务器。"""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, handler_cls):
        super().__init__(addr, handler_cls)
        self.media = {}          # key -> (filepath, mime)
        self.hls_dir = None
        self.live_cmd_builder = None   # callable() -> ffmpeg 命令 (mpegts)
        self._live_lock = threading.Lock()
        self._live_active = False
        self.bytes_streamed = 0        # 本次直播流已推送给渲染器的字节数（判断是否真的在播）
        self.log = print

    def register_media(self, key, filepath, mime=None):
        self.media[key] = (os.path.abspath(filepath), mime or guess_mime(filepath))

    def register_hls(self, hls_dir):
        self.hls_dir = hls_dir

    def register_live(self, builder):
        self.live_cmd_builder = builder

    def is_live_configured(self):
        return self.live_cmd_builder is not None

    def start_live_stream(self):
        """启动一条 mpegts 直播流（同一时刻最多一条），返回 subprocess.Popen。"""
        with self._live_lock:
            if self._live_active:
                return None
            self._live_active = True
        cmd = self.live_cmd_builder()
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._active_proc = proc
        return proc

    def _release_live(self):
        with self._live_lock:
            self._live_active = False
            self._active_proc = None

    def abort_live(self):
        """强制结束当前直播流（用于切换编码器后重启）。"""
        with self._live_lock:
            proc = getattr(self, "_active_proc", None)
            self._live_active = False
            self._active_proc = None
        if proc:
            try:
                proc.kill()
            except Exception:
                pass

    def handle_error(self, request, client_address):
        # 不打印完整堆栈，仅简要记录，避免刷屏
        try:
            self.log(f"HTTP 客户端连接异常: {client_address}")
        except Exception:
            pass

    def shutdown_server(self):
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            self.server_close()
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "PC2TV/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send_dlna_headers(self):
        for k, v in DLNA_HEADERS.items():
            self.send_header(k, v)

    # ---------------- 路由 ----------------
    def do_HEAD(self):
        self._route(head=True)

    def do_GET(self):
        self._route(head=False)

    def _route(self, head):
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith("/media/"):
            self._serve_media(path, head)
        elif path.startswith("/live_") and path.endswith(".ts"):
            self._serve_live(head)
        elif path.startswith("/hls/"):
            self._serve_hls(path, head)
        else:
            self.send_error(404)

    # ---------------- 媒体文件 ----------------
    def _serve_media(self, path, head):
        key = urllib.parse.unquote(path[len("/media/"):])
        entry = self.server.media.get(key)
        if not entry:
            self.send_error(404)
            return
        filepath, mime = entry
        try:
            size = os.path.getsize(filepath)
        except OSError:
            self.send_error(404)
            return
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        status = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                s, e = m.group(1), m.group(2)
                start = int(s) if s else 0
                end = int(e) if e else size - 1
                if start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self._send_dlna_headers()
        self.end_headers()
        if head:
            return
        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
                remaining -= len(chunk)

    # ---------------- 直播流 (MPEG-TS) ----------------
    def _serve_live(self, head):
        if not self.server.is_live_configured():
            self.send_error(404)
            return
        proc = self.server.start_live_stream()
        if proc is None:
            self.send_error(503, "busy")
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self._send_dlna_headers()
            self.end_headers()
            if head:
                return
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.server.bytes_streamed += len(chunk)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            self.server._release_live()

    # ---------------- HLS ----------------
    def _serve_hls(self, path, head):
        hls_dir = self.server.hls_dir
        if not hls_dir:
            self.send_error(404)
            return
        name = path[len("/hls/"):]
        filepath = os.path.normpath(os.path.join(hls_dir, name))
        if not filepath.startswith(os.path.normpath(hls_dir)):
            self.send_error(403)
            return
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        if name.endswith(".m3u8"):
            mime = "video/m3u8"
        else:
            mime = "video/mp2t"
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-cache")
        self._send_dlna_headers()
        self.end_headers()
        if head:
            return
        with open(filepath, "rb") as f:
            try:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.server.bytes_streamed += len(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass