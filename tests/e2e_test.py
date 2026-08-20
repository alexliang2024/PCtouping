# -*- coding: utf-8 -*-
"""端到端测试：真实机顶盒 DLNA 投屏验证（会短暂在电视上显示测试画面，随后自动停止）。"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cast_tv import upnp, screen as screen_mod
from cast_tv.cast import CastSession


def poll_state(dev, wait=15):
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
    target = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.6"
    print("=== 1. 发现设备 ===")
    devices = upnp.discover(target=target, timeout=4)
    renderers = [d for d in devices if d.is_media_renderer()]
    for i, d in enumerate(renderers):
        print(f"  [{i}] {d.friendly()}")
    if not renderers:
        print("未发现渲染器")
        return 2

    best = upnp.pick_best_renderer(renderers)
    print(f"\n最佳渲染器: {best.friendly()}")

    ff = screen_mod.find_ffmpeg()

    # ---- 2. 媒体文件投屏 ----
    print("\n=== 2. 媒体文件投屏 (生成 5 秒测试视频) ===")
    sample = os.path.join(os.path.dirname(__file__), "sample_test.mp4")
    if ff and not os.path.exists(sample):
        subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-t", "5", "-c:v", "libx264", "-preset", "veryfast",
             "-c:a", "aac", "-shortest", sample], check=True, timeout=60)
    sess = CastSession(best, port=8090)
    try:
        uri = sess.cast_media(sample)
        print(f"  推送: {uri}")
        state, ok = poll_state(best, wait=15)
        print(f"  媒体投屏状态: {state} -> {'成功' if ok else '未播放'}")
        sess.stop()
    except Exception as e:
        print(f"  媒体投屏异常: {e}")
        sess.stop()

    # ---- 3. 实时流投屏 (MPEG-TS, lavfi 测试源) ----
    print("\n=== 3. 实时流投屏 MPEG-TS (测试源) ===")
    sess2 = CastSession(best, port=8090)
    try:
        uri = sess2.cast_screen(mode="full", fps=15, bitrate="4M",
                                strategy="mpegts",
                                custom_input=["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=15"])
        print(f"  推送: {uri}")
        state, ok = poll_state(best, wait=12)
        print(f"  MPEG-TS 实时投屏状态: {state} -> {'成功' if ok else '未播放'}")
        sess2.stop()
    except Exception as e:
        print(f"  MPEG-TS 异常: {e}")
        sess2.stop()

    # ---- 4. 实时流投屏 (HLS, lavfi 测试源) ----
    print("\n=== 4. 实时流投屏 HLS (测试源) ===")
    sess3 = CastSession(best, port=8090)
    try:
        uri = sess3.cast_screen(mode="full", fps=15, bitrate="4M",
                                strategy="hls",
                                custom_input=["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=15"])
        print(f"  推送: {uri}")
        state, ok = poll_state(best, wait=15)
        print(f"  HLS 实时投屏状态: {state} -> {'成功' if ok else '未播放'}")
        sess3.stop()
    except Exception as e:
        print(f"  HLS 异常: {e}")
        sess3.stop()

    print("\n=== 测试结束，已全部停止 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())