# -*- coding: utf-8 -*-
"""屏幕/窗口采集 (ffmpeg gdigrab) 与 Windows 窗口枚举。"""
import ctypes
import os
import re
import shutil
import subprocess
import tempfile
from ctypes import wintypes

FFMPEG_CANDIDATES = [
    r"C:\ffmpeg-standalone\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]

# 硬件编码器探测顺序（按 Windows 上可用性排序）
HW_ENCODERS = ["h264_mf", "h264_nvenc", "h264_qsv", "h264_amf"]
_ENCODER_CACHE = {}


class FfmpegNotFoundError(Exception):
    pass


def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    env = os.environ.get("FFMPEG")
    if env and os.path.isfile(env):
        return env
    for cand in FFMPEG_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return None


def _bitrate_mul(b, factor):
    m = re.match(r"^(\d+)([kKmM]?)$", str(b).strip())
    if not m:
        return str(b)
    num = int(m.group(1))
    unit = m.group(2).lower()
    val = num * (1024 if unit == "k" else 1024 * 1024 if unit == "m" else 1)
    val = int(val * factor)
    if val % (1024 * 1024) == 0:
        return f"{val // (1024 * 1024)}M"
    if val % 1024 == 0:
        return f"{val // 1024}K"
    return str(val)


# ---------------- 编码器选择 ----------------
def pick_video_encoder(ffmpeg=None, force="auto"):
    """选择视频编码器：force=auto 时实测可用的硬件编码器，都不行退回 libx264。
    force 可指定具体编码器名或 'libx264'。结果缓存。"""
    if force and force != "auto":
        return force
    ff = ffmpeg or find_ffmpeg()
    if not ff:
        return "libx264"
    if ff in _ENCODER_CACHE:
        return _ENCODER_CACHE[ff]
    for enc in HW_ENCODERS:
        try:
            r = subprocess.run(
                [ff, "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5",
                 "-t", "0.4", "-c:v", enc, "-f", "null", "-"],
                capture_output=True, timeout=8)
            if r.returncode == 0:
                _ENCODER_CACHE[ff] = enc
                return enc
        except Exception:
            continue
    _ENCODER_CACHE[ff] = "libx264"
    return "libx264"


def encoder_args(enc, fps, bitrate):
    """根据编码器返回 ffmpeg 编码参数（低延迟取向）。"""
    g = str(max(10, fps * 2))
    if enc == "h264_mf":
        return ["-c:v", "h264_mf", "-b:v", bitrate, "-g", g]
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
                "-b:v", bitrate, "-g", g]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "veryfast", "-look_ahead", "0",
                "-b:v", bitrate, "-g", g]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "speed", "-usage", "lowlatency",
                "-b:v", bitrate, "-g", g]
    return ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-b:v", bitrate,
            "-maxrate", _bitrate_mul(bitrate, 1.5),
            "-bufsize", _bitrate_mul(bitrate, 2), "-g", g]


def build_screen_cmd(mode="full", title=None, fps=15, bitrate="4M",
                     rect=None, ffmpeg=None, output="mpegts", hls_dir=None,
                     custom_input=None, audio_device=None, encoder="auto",
                     max_width=None, max_height=None):
    """构造 ffmpeg 命令。
    mode: full | window
    rect: "WxH+X+Y" 可选，指定采集区域（默认全桌面）
    output: mpegts(pipe:1) | hls(写文件)
    audio_device: 系统声音采集设备名（如 "CABLE Output (VB-Audio Virtual Cable)"）
    encoder: auto=自动选硬件编码器; libx264=软编; 或指定 h264_mf/nvenc/qsv/amf
    """
    ff = ffmpeg or find_ffmpeg()
    if not ff:
        raise FfmpegNotFoundError("未找到 ffmpeg，请先安装并加入 PATH，或设置环境变量 FFMPEG")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y"]
    if custom_input:
        cmd += list(custom_input)
    elif mode == "window":
        if not title:
            raise ValueError("窗口投屏需要指定窗口标题")
        cmd += ["-f", "gdigrab", "-framerate", str(fps), "-i", f"title={title}"]
    else:
        if rect:
            m = re.match(r"^(\d+)x(\d+)(?:\+(\d+)\+(\d+))?$", rect.strip())
            if m:
                w, h = m.group(1), m.group(2)
                x, y = m.group(3) or 0, m.group(4) or 0
                cmd += ["-video_size", f"{w}x{h}", "-offset_x", str(x), "-offset_y", str(y)]
        cmd += ["-f", "gdigrab", "-framerate", str(fps), "-i", "desktop"]
    # 声音采集（系统声音经 VB-CABLE / 立体声混音）
    if audio_device:
        cmd += ["-f", "dshow", "-rtbufsize", "64M", "-i", f"audio={audio_device}"]
    cmd += ["-map", "0:v:0"]
    if audio_device:
        cmd += ["-map", "1:a:0"]
    # 分辨率上限（降低编码负载让画面更流畅）+ 强制偶数宽高（H.264 要求）
    if max_width or max_height:
        mw = max_width or 99999
        mh = max_height or 99999
        vf = (f"scale='min({mw},iw)':'min({mh},ih)':force_original_aspect_ratio=decrease,"
              "scale=trunc(iw/2)*2:trunc(ih/2)*2")
    else:
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    cmd += ["-pix_fmt", "yuv420p", "-vf", vf]
    enc = pick_video_encoder(ff, force=encoder)
    cmd += encoder_args(enc, fps, bitrate)
    if audio_device:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    if output == "hls":
        cmd += [
            "-f", "hls", "-hls_time", "1", "-hls_list_size", "4",
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", os.path.join(hls_dir, "seg_%05d.ts"),
            os.path.join(hls_dir, "live.m3u8"),
        ]
    else:
        cmd += ["-f", "mpegts", "-muxdelay", "0", "-flush_packets", "1", "pipe:1"]
    return cmd, enc


def make_hls_dir():
    return tempfile.mkdtemp(prefix="pctv_hls_")


def cleanup_hls_dir(d):
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass


# ---------------- 声音采集设备 ----------------
def list_dshow_audio_devices(ffmpeg=None):
    """列出 ffmpeg dshow 可用的音频采集设备名。"""
    ff = ffmpeg or find_ffmpeg()
    if not ff:
        return []
    try:
        r = subprocess.run(
            [ff, "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
            capture_output=True, text=True, errors="replace", timeout=20)
    except Exception:
        return []
    out = []
    for line in (r.stderr or "").splitlines():
        m = re.search(r'"([^"]+)"\s*\(audio\)', line)
        if m:
            out.append(m.group(1))
    return out


def find_loopback_audio(ffmpeg=None):
    """找系统声音采集设备：优先 VB-CABLE，其次 立体声混音/Stereo Mix 等。"""
    devs = list_dshow_audio_devices(ffmpeg)
    prefs = ["cable output", "立体声混音", "stereo mix",
             "what u hear", "what you hear", "混音", "loopback", "virtual"]
    for pref in prefs:
        for d in devs:
            if pref in d.lower():
                return d
    return None


# ---------------- Windows 窗口枚举 ----------------
_user32 = ctypes.windll.user32
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def list_windows():
    """返回所有可见顶层窗口标题（去重、去空）。"""
    results = []

    @_WNDENUMPROC
    def _cb(hwnd, lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title and title != "Program Manager":
            results.append(title)
        return True

    _user32.EnumWindows(_cb, 0)
    seen, out = set(), []
    for t in results:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def get_primary_screen_size():
    try:
        return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
    except Exception:
        return None




def quick_ffmpeg_check(ffmpeg=None):
    ff = ffmpeg or find_ffmpeg()
    if not ff:
        return False, "未找到 ffmpeg"
    try:
        r = subprocess.run([ff, "-version"], capture_output=True, timeout=10)
        return r.returncode == 0, "ffmpeg 可用"
    except Exception as e:
        return False, str(e)