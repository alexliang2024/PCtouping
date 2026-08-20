# -*- coding: utf-8 -*-
"""图形界面 (tkinter)。"""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import screen as screen_mod
from . import upnp
from .cast import CastSession
from .config import DEFAULT_TARGET_IP


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("PC 投屏助手 — 电脑 → 电视")
        self.root.geometry("800x680")
        self.root.minsize(720, 600)
        try:
            self.root.option_add("*Font", ("Microsoft YaHei UI", 10))
            style = ttk.Style()
            if "vista" in style.theme_names():
                style.theme_use("vista")
        except Exception:
            pass

        self.devices = []
        self.session = None
        self.session_lock = threading.Lock()
        self.msg_q = queue.Queue()
        self._stopping = False

        self._build_ui()
        try:
            self.root.state("zoomed")   # 启动时最大化
        except Exception:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_queue)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        top = ttk.LabelFrame(self.root, text=" 1. 连接机顶盒 ")
        top.pack(fill="x", padx=8, pady=(8, 4))
        f = ttk.Frame(top)
        f.pack(fill="x", **pad)
        ttk.Label(f, text="机顶盒 IP:").pack(side="left")
        self.ip_var = tk.StringVar(value=DEFAULT_TARGET_IP)
        ttk.Entry(f, textvariable=self.ip_var, width=16).pack(side="left", padx=4)
        ttk.Button(f, text="发现设备", command=self._on_discover).pack(side="left", padx=6)
        ttk.Button(f, text="停止投屏", command=self._on_stop).pack(side="right")
        f2 = ttk.Frame(top)
        f2.pack(fill="x", **pad)
        ttk.Label(f2, text="目标设备:").pack(side="left")
        self.device_var = tk.StringVar()
        self.device_cb = ttk.Combobox(f2, textvariable=self.device_var, state="readonly", width=66)
        self.device_cb.pack(side="left", padx=4, fill="x", expand=True)

        mid = ttk.LabelFrame(self.root, text=" 2. 选择投屏内容 ")
        mid.pack(fill="x", padx=8, pady=4)
        b = ttk.Frame(mid)
        b.pack(fill="x", **pad)
        ttk.Button(b, text="投屏全屏", command=lambda: self._on_screen("full")).pack(side="left", padx=2)
        ttk.Button(b, text="投屏窗口", command=lambda: self._on_screen("window")).pack(side="left", padx=2)
        ttk.Button(b, text="投媒体文件", command=self._on_media).pack(side="left", padx=2)

        w = ttk.Frame(mid)
        w.pack(fill="x", **pad)
        ttk.Label(w, text="窗口:").pack(side="left")
        self.win_var = tk.StringVar()
        self.win_cb = ttk.Combobox(w, textvariable=self.win_var, width=50)
        self.win_cb.pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(w, text="刷新窗口", command=self._on_refresh_windows).pack(side="left", padx=2)

        u = ttk.Frame(mid)
        u.pack(fill="x", **pad)
        ttk.Label(u, text="网络链接:").pack(side="left")
        self.url_var = tk.StringVar()
        ttk.Entry(u, textvariable=self.url_var, width=52).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(u, text="投网络链接", command=self._on_url).pack(side="left", padx=2)

        opt = ttk.Frame(mid)
        opt.pack(fill="x", **pad)
        ttk.Label(opt, text="帧率:").pack(side="left")
        self.fps_var = tk.StringVar(value="12")
        ttk.Spinbox(opt, from_=5, to=30, textvariable=self.fps_var, width=5).pack(side="left", padx=2)
        ttk.Label(opt, text="码率:").pack(side="left")
        self.br_var = tk.StringVar(value="2M")
        ttk.Combobox(opt, textvariable=self.br_var, values=["2M", "4M", "6M", "8M", "12M"],
                     width=6, state="readonly").pack(side="left", padx=2)
        ttk.Label(opt, text="策略:").pack(side="left")
        self.strategy_var = tk.StringVar(value="自动")
        ttk.Combobox(opt, textvariable=self.strategy_var,
                     values=["自动", "MPEG-TS", "HLS", "仅URL(VLC)"],
                     width=12, state="readonly").pack(side="left", padx=2)
        ttk.Label(opt, text="分辨率:").pack(side="left")
        self.res_var = tk.StringVar(value="原始")
        ttk.Combobox(opt, textvariable=self.res_var,
                     values=["原始", "1080", "720", "540", "360"],
                     width=6, state="readonly").pack(side="left", padx=2)
        self.audio_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="同步声音到电视", variable=self.audio_var).pack(side="left", padx=6)
        self.hwenc_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="硬件加速编码(更流畅)", variable=self.hwenc_var).pack(side="left", padx=6)

        vol = ttk.LabelFrame(self.root, text=" 3. 音量 ")
        vol.pack(fill="x", padx=8, pady=4)
        vf = ttk.Frame(vol)
        vf.pack(fill="x", **pad)
        self.vol_var = tk.IntVar(value=50)
        ttk.Scale(vf, from_=0, to=100, variable=self.vol_var,
                  command=lambda _v: None, length=440).pack(side="left")
        ttk.Button(vf, text="读取音量", command=self._on_get_volume).pack(side="left", padx=6)
        ttk.Button(vf, text="设置音量", command=self._on_set_volume).pack(side="left", padx=2)

        logf = ttk.LabelFrame(self.root, text=" 日志 ")
        logf.pack(fill="both", expand=True, padx=8, pady=4)
        self.log_text = tk.Text(logf, height=12, state="disabled", wrap="word")
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y", pady=4)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").pack(fill="x", padx=8, pady=(0, 6))

    # ---------------- 日志 ----------------
    def log(self, msg):
        self.msg_q.put(("log", str(msg)))

    def set_status(self, msg):
        self.msg_q.put(("status", str(msg)))

    def _poll_queue(self):
        try:
            while True:
                kind, val = self.msg_q.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", val + "\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(val)
                elif kind == "devices":
                    self._devices_ready(val)
                elif kind == "windows":
                    self._windows_ready(val)
        except queue.Empty:
            pass
        if not self._stopping:
            self.root.after(100, self._poll_queue)

    def _windows_ready(self, wins):
        self.win_cb["values"] = wins
        if wins:
            cur = self.win_var.get()
            if cur not in wins:
                self.win_var.set(wins[0])
            self.set_status(f"已列出 {len(wins)} 个窗口")
        else:
            self.win_var.set("")
            self.set_status("没有找到可见窗口")
        self.log(f"窗口列表: {len(wins)} 个")

    # ---------------- 动作 ----------------
    def _run_async(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _on_discover(self):
        ip = self.ip_var.get().strip()
        self.set_status("正在发现设备 ...")
        self.log(f"开始搜索 (目标 {ip}) ...")

        def work():
            try:
                devices = upnp.discover(target=ip, timeout=4, progress=self.log)
                renderers = [d for d in devices if d.is_media_renderer()]
                self.msg_q.put(("devices", renderers))
                self.log(f"发现 {len(renderers)} 个 DLNA 渲染器")
            except Exception as e:
                self.set_status("发现失败")
                self.log(f"错误: {e}")

        self._run_async(work)

    def _devices_ready(self, renderers):
        self.devices = renderers
        if not renderers:
            self.device_cb["values"] = []
            self.device_var.set("")
            self.set_status("未发现 DLNA 渲染器")
            messagebox.showwarning("提示", "没有发现 DLNA 渲染器。\n请确认机顶盒与电脑在同一局域网，且投屏应用已开启。")
            return
        self.device_cb["values"] = [d.friendly() for d in renderers]
        best = upnp.pick_best_renderer(renderers)
        idx = renderers.index(best) if best in renderers else 0
        self.device_cb.current(idx)
        self.set_status(f"已发现 {len(renderers)} 个渲染器，已自动选择最佳设备")

    def _selected_device(self):
        if not self.devices:
            raise RuntimeError("请先点击「发现设备」")
        idx = self.device_cb.current()
        if idx < 0 or idx >= len(self.devices):
            idx = 0
        return self.devices[idx]

    def _new_session(self):
        dev = self._selected_device()
        with self.session_lock:
            if self.session:
                self.session.stop()
            sess = CastSession(dev, log=self.log)
            self.session = sess
        self.log(f"已选择设备: {dev.friendly()}")
        return sess

    def _encoder_setting(self):
        return "auto" if self.hwenc_var.get() else "libx264"

    def _on_screen(self, mode):
        if mode == "window" and not self.win_var.get().strip():
            messagebox.showwarning("提示", "请先在窗口列表选择要投屏的窗口，或点击「刷新窗口」")
            return
        if not screen_mod.find_ffmpeg():
            messagebox.showerror("缺少 ffmpeg", "未找到 ffmpeg，无法进行屏幕/窗口采集。\n"
                                 "请安装 ffmpeg 并加入 PATH，或设置环境变量 FFMPEG。\n"
                                 "（媒体文件/网络链接投屏不依赖 ffmpeg）")
            return
        strat_map = {"自动": "auto", "MPEG-TS": "mpegts", "HLS": "hls", "仅URL(VLC)": "url"}
        strategy = strat_map.get(self.strategy_var.get(), "auto")
        try:
            sess = self._new_session()
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return
        fps = self._int_of(self.fps_var.get(), 15, 5, 30)
        bitrate = self.br_var.get() or "4M"
        title = self.win_var.get().strip() if mode == "window" else None
        self.set_status("正在启动屏幕采集与投屏 ...")

        def work():
            try:
                uri = sess.cast_screen(mode=mode, title=title, fps=fps,
                                       bitrate=bitrate, strategy=strategy,
                                       audio="auto" if self.audio_var.get() else "off",
                                       encoder=self._encoder_setting(),
                                       resolution=self.res_var.get())
                self.set_status("投屏中 ...")
                self.log(f"流地址: {uri}")
                if strategy == "url":
                    self.log("（仅 URL 模式：请在机顶盒 VLC/浏览器中打开上面的地址）")
            except Exception as e:
                self.set_status("投屏失败")
                self.log(f"错误: {e}")

        self._run_async(work)

    def _on_media(self):
        path = filedialog.askopenfilename(
            title="选择要投屏的媒体文件",
            filetypes=[("媒体文件", "*.mp4 *.mkv *.avi *.wmv *.mov *.flv *.mpg *.mpeg *.ts "
                                 "*.mp3 *.wav *.flac *.aac *.jpg *.jpeg *.png *.gif"),
                       ("所有文件", "*.*")])
        if not path:
            return
        try:
            sess = self._new_session()
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return
        self.set_status("正在投屏媒体 ...")

        def work():
            try:
                uri = sess.cast_media(path)
                self.set_status("投屏中 ...")
                self.log(f"流地址: {uri}")
            except Exception as e:
                self.set_status("投屏失败")
                self.log(f"错误: {e}")

        self._run_async(work)

    def _on_url(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先输入要投屏的网络链接 (http/https)")
            return
        try:
            sess = self._new_session()
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return
        self.set_status("正在推送网络链接 ...")

        def work():
            try:
                uri = sess.cast_url(url)
                self.set_status("投屏中 ...")
                self.log(f"网络链接: {uri}")
            except Exception as e:
                self.set_status("投屏失败")
                self.log(f"错误: {e}")

        self._run_async(work)

    def _on_stop(self):
        def work():
            with self.session_lock:
                sess, self.session = self.session, None
            if sess:
                try:
                    sess.stop()
                except Exception as e:
                    self.log(f"停止出错: {e}")
            self.set_status("已停止")

        self._run_async(work)

    def _on_refresh_windows(self):
        def work():
            try:
                wins = screen_mod.list_windows()
                self.msg_q.put(("windows", wins))
            except Exception as e:
                self.log(f"获取窗口失败: {e}")

        self._run_async(work)

    def _on_get_volume(self):
        def work():
            try:
                dev = self._selected_device()
                v = dev.get_volume()
                self.vol_var.set(v)
                self.log(f"当前音量: {v}")
            except Exception as e:
                self.log(f"读取音量失败: {e}")

        self._run_async(work)

    def _on_set_volume(self):
        def work():
            try:
                dev = self._selected_device()
                v = dev.set_volume(self.vol_var.get())
                self.log(f"音量已设为: {v}")
            except Exception as e:
                self.log(f"设置音量失败: {e}")

        self._run_async(work)

    def _int_of(self, s, default, lo, hi):
        try:
            v = int(s)
            return max(lo, min(hi, v))
        except Exception:
            return default

    def _on_close(self):
        self._stopping = True
        try:
            with self.session_lock:
                if self.session:
                    self.session.stop()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()