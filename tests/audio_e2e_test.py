# -*- coding: utf-8 -*-
"""音频端到端验证：确保声音进入虚拟声卡 → 全屏+声音实时投到机顶盒。"""
import math
import os
import struct
import subprocess
import sys
import time
import wave

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cast_tv import audio as audio_mod
from cast_tv import screen as screen_mod
from cast_tv import upnp
from cast_tv.cast import CastSession

FF = screen_mod.find_ffmpeg()
FFPLAY = FF.replace("ffmpeg.exe", "ffplay.exe").replace("ffmpeg.EXE", "ffplay.EXE") if FF else None
HERE = os.path.dirname(os.path.abspath(__file__))
TONE = os.path.join(HERE, "tone_test.wav")
TS_FILE = os.path.join(HERE, "audio_test.ts")


def make_tone(path, secs=60, freq=1000.0, rate=44100):
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * secs)
        data = bytearray()
        for i in range(n):
            data += struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
        w.writeframes(bytes(data))


def mean_volume(args_extra, secs):
    cmd = [FF, "-hide_banner", "-f", "dshow", "-i", args_extra[0], "-t", str(secs),
           "-af", "volumedetect", "-f", "null", "-"] if args_extra[0].startswith("audio=") else None
    if cmd is None:
        cmd = [FF, "-hide_banner"] + args_extra + ["-t", str(secs), "-af", "volumedetect", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=25)
    m = [l for l in r.stderr.splitlines() if "mean_volume" in l]
    return m[-1].strip() if m else "?"


def main():
    dev = screen_mod.find_loopback_audio()
    print("声音采集设备:", dev)
    if not dev:
        print("未找到声音采集设备，无法继续")
        return 1

    # 1) 确保系统声音走虚拟声卡
    restore = audio_mod.ensure_cable_default(log=print)
    print("默认播放设备:", audio_mod.get_default_render_id())

    make_tone(TONE)
    # 用系统默认播放设备播放（此时默认已被切到 CABLE Input，声音进入虚拟声卡）
    ps = "$p = New-Object System.Media.SoundPlayer -ArgumentList '" + TONE + "'; $p.PlaySync(); exit 0"
    player = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                              creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(2)

    print("\n[1] 虚拟声卡是否收到系统声音:", mean_volume([f"audio={dev}"], 6))

    print("\n[2] 全屏+声音 mux 到 TS 文件:")
    cmd, _enc = screen_mod.build_screen_cmd(mode="full", fps=10, bitrate="3M", rect="640x360+0+0",
                                          audio_device=dev)
    cmd = cmd[:-1] + ["-t", "6", TS_FILE]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=30)
    print("   退出码:", r.returncode)
    if r.returncode == 0 and os.path.exists(TS_FILE):
        info = subprocess.run([FF.replace("ffmpeg", "ffprobe") if "ffprobe" in FF else "ffprobe",
                               "-hide_banner", "-show_streams", "-of", "compact", TS_FILE],
                              capture_output=True, text=True, errors="replace", timeout=20)
        has_v = "codec_type=video" in info.stdout
        has_a = "codec_type=audio" in info.stdout
        print("   TS 流: video=%s audio=%s" % (has_v, has_a))
        print("   TS 音频音量:", mean_volume(["-i", TS_FILE, "-map", "0:a:0"], 6))

    print("\n[3] 全屏+声音 实时投到机顶盒:")
    devices = upnp.discover(target="192.168.5.6", timeout=4)
    renderers = [d for d in devices if d.is_media_renderer()]
    if not renderers:
        print("未发现渲染器")
        return 2
    best = upnp.pick_best_renderer(renderers)
    print("   设备:", best.friendly())
    sess = CastSession(best, port=8090)
    try:
        uri = sess.cast_screen(mode="full", fps=10, bitrate="3M", strategy="mpegts", audio="auto")
        print("   流:", uri)
        state, ok = None, False
        end = time.time() + 20
        while time.time() < end:
            try:
                info = best.get_transport_info()
                state = info.get("state", "")
            except Exception as e:
                state = f"ERR:{e}"
            if state in ("PLAYING", "TRANSITIONING"):
                ok = True
                break
            time.sleep(0.8)
        print("   渲染器状态:", state, "->", "成功(音画同步推流)" if ok else "未播放")
        # 投屏期间再次确认虚拟声卡仍在出声
        print("   投屏期间虚拟声卡音量:", mean_volume([f"audio={dev}"], 4))
    finally:
        sess.stop()

    if player:
        player.kill()
    if restore:
        audio_mod.restore_default(restore[0])
        print("已恢复原默认播放设备")
    print("\n=== 完成 ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        for f in (TONE, TS_FILE):
            try:
                os.remove(f)
            except OSError:
                pass