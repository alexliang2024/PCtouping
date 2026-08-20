# -*- coding: utf-8 -*-
"""新功能端到端验证：窗口投屏 / 网络链接投屏 / 硬件编码全屏投屏。"""
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cast_tv import screen as screen_mod
from cast_tv import upnp
from cast_tv.cast import CastSession, get_local_ip

FF = screen_mod.find_ffmpeg()
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "sample_url.mp4")


def make_sample():
    if os.path.exists(SAMPLE):
        return
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-t", "8", "-c:v", "libx264", "-preset", "veryfast",
                    "-c:a", "aac", "-shortest", SAMPLE], check=True, timeout=60)


def poll_state(dev, wait=18):
    end = time.time() + wait
    last = ""
    while time.time() < end:
        try:
            info = dev.get_transport_info()
            last = info.get("state", "")
        except Exception as e:
            last = f"ERR:{e}"
        if last in ("PLAYING", "TRANSITIONING"):
            return last, True
        time.sleep(0.8)
    return last, False


def main():
    print("=== 0. 发现设备 ===")
    renderers = [d for d in upnp.discover(target="192.168.5.6", timeout=4)
                 if d.is_media_renderer()]
    if not renderers:
        print("未发现渲染器")
        return 1
    best = upnp.pick_best_renderer(renderers)
    print("设备:", best.friendly())

    # ---- 1. 窗口投屏（记事本） ----
    print("\n=== 1. 窗口投屏 (记事本) ===")
    notepad = subprocess.Popen(["notepad.exe"])
    time.sleep(2)
    wins = screen_mod.list_windows()
    title = next((w for w in wins if ("记事本" in w or "Notepad" in w)), None)
    print("找到窗口标题:", title)
    if title:
        sess = CastSession(best, port=8090)
        try:
            uri = sess.cast_screen(mode="window", title=title, fps=10,
                                   bitrate="3M", strategy="mpegts", audio="auto",
                                   encoder="auto")
            state, ok = poll_state(best, wait=18)
            print(f"窗口投屏状态: {state} -> {'成功' if ok else '未播放'}")
        except Exception as e:
            print("窗口投屏异常:", e)
        finally:
            sess.stop()
    notepad.kill()

    # ---- 2. 网络链接投屏（本机 URL：验证机制） ----
    print("\n=== 2. 网络链接投屏 (本机 URL) ===")
    make_sample()
    sess = CastSession(best, port=8090)
    try:
        sess.ensure_server()
        key = "sample_url.mp4"
        sess.server.register_media(key, SAMPLE, "video/mp4")
        url = f"http://{get_local_ip('192.168.5.6')}:{sess.port}/media/{key}"
        print("URL:", url)
        sess.cast_url(url, title="URL 测试")
        state, ok = poll_state(best, wait=15)
        print(f"本机URL投屏状态: {state} -> {'成功' if ok else '未播放'}")
    except Exception as e:
        print("URL投屏异常:", e)
    finally:
        sess.stop()

    # ---- 3. 网络链接投屏（公网 URL，机顶盒自行拉取） ----
    print("\n=== 3. 网络链接投屏 (公网 URL) ===")
    sess = CastSession(best, port=8090)
    try:
        url = "https://media.w3.org/2010/05/sintel/trailer.mp4"
        print("URL:", url)
        sess.cast_url(url, title="Sintel Trailer")
        state, ok = poll_state(best, wait=15)
        print(f"公网URL投屏状态: {state} -> {'成功' if ok else '未播放(可能机顶盒无法访问外网)'}")
    except Exception as e:
        print("公网URL投屏异常:", e)
    finally:
        sess.stop()

    # ---- 4. 全屏投屏（硬件编码 h264_mf + 声音） ----
    print("\n=== 4. 全屏投屏 (h264_mf 硬件编码 + 声音) ===")
    sess = CastSession(best, port=8090)
    try:
        enc = screen_mod.pick_video_encoder()
        print("编码器:", enc)
        uri = sess.cast_screen(mode="full", fps=15, bitrate="4M",
                               strategy="mpegts", audio="auto", encoder="auto")
        state, ok = poll_state(best, wait=20)
        print(f"全屏投屏状态: {state} -> {'成功' if ok else '未播放'}")
    except Exception as e:
        print("全屏投屏异常:", e)
    finally:
        sess.stop()

    print("\n=== 完成 ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        for f in (SAMPLE,):
            try:
                os.remove(f)
            except OSError:
                pass