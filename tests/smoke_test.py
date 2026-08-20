# -*- coding: utf-8 -*-
"""本地冒烟测试：不依赖机顶盒，验证 HTTP 服务 / Range / 直播流 / HLS。"""
import http.client
import os
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cast_tv.server import StreamServer, Handler  # noqa: E402
from cast_tv import screen as screen_mod  # noqa: E402

PASS = []


def check(name, cond, extra=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name} {extra}")
    if not cond:
        raise SystemExit(f"smoke test failed at: {name}")
    PASS.append(name)


def get(port, path, headers=None, read_all=True):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    body = r.read() if read_all else b""
    h = dict(r.getheaders())
    c.close()
    return r.status, h, body


def main():
    tmp = tempfile.mkdtemp(prefix="smoke_")
    try:
        # ---- 1. 媒体文件 + Range ----
        media_path = os.path.join(tmp, "test.mp4")
        with open(media_path, "wb") as f:
            f.write(bytes(range(256)) * 1024)  # 256 KB

        srv = StreamServer(("127.0.0.1", 0), Handler)
        port = srv.server_address[1]
        srv.register_media("test.mp4", media_path, "video/mp4")
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        st, h, body = get(port, "/media/test.mp4")
        check("media 200", st == 200 and len(body) == 256 * 1024, f"len={len(body)}")
        check("media content-type", h.get("Content-Type") == "video/mp4")
        check("media dlna header", "contentFeatures.dlna.org" in h)

        st, h, body = get(port, "/media/test.mp4", {"Range": "bytes=100-199"})
        check("media range 206", st == 206 and body == bytes(range(100, 200)),
              f"status={st} len={len(body)}")
        check("range header", h.get("Content-Range") == "bytes 100-199/262144")

        # ---- 2. 直播流 (MPEG-TS via ffmpeg lavfi) ----
        ff = screen_mod.find_ffmpeg()
        if ff:
            cmd = [ff, "-hide_banner", "-loglevel", "error",
                   "-f", "lavfi", "-i", "testsrc=size=320x200:rate=10",
                   "-t", "4", "-c:v", "libx264", "-preset", "ultrafast",
                   "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                   "-f", "mpegts", "pipe:1"]
            srv.register_live(lambda: cmd)
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
            c.request("GET", "/live_test.ts")
            r = c.getresponse()
            first = r.read(65536)
            check("live.ts status", r.status == 200, f"status={r.status}")
            check("live.ts bytes", len(first) > 10000, f"len={len(first)}")
            check("live.ts mime", r.getheader("Content-Type") == "video/mp2t")
            r.close()
            c.close()

            # ---- 3. HLS ----
            hlsdir = screen_mod.make_hls_dir()
            hcmd = [ff, "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x200:rate=10",
                    "-t", "3", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-f", "hls", "-hls_time", "1",
                    "-hls_list_size", "4", "-hls_flags", "delete_segments+append_list",
                    "-hls_segment_filename", os.path.join(hlsdir, "seg_%05d.ts"),
                    os.path.join(hlsdir, "live.m3u8")]
            import subprocess
            subprocess.run(hcmd, check=True, capture_output=True, timeout=30)
            srv.register_hls(hlsdir)
            st, h, body = get(port, "/hls/live.m3u8")
            check("hls m3u8", st == 200 and b"#EXTM3U" in body, f"status={st}")
            seg = [l for l in body.decode().splitlines() if l.endswith(".ts")]
            if seg:
                st2, h2, b2 = get(port, "/hls/" + seg[0])
                check("hls segment", st2 == 200 and len(b2) > 1000,
                      f"status={st2} len={len(b2)}")
            screen_mod.cleanup_hls_dir(hlsdir)
        else:
            print("[SKIP] ffmpeg 未找到，跳过直播/HLS 测试")

        srv.shutdown_server()
        print(f"\n全部通过 ({len(PASS)} 项)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()