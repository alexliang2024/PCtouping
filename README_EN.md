# PC Casting Assistant (PC → TV / Set-top Box)

Cast your **full screen**, a **specific app window**, a **local media file**, or **any web URL**
to a TV / set-top box (STB) on your local network.

This tool is built around your STB's built-in **DLNA** renderer, so **no APK needs to be
installed** on the box. When live DLNA streaming is unstable, a "URL-only" mode can fall back
to VLC on the STB.

> Default target in this repo is the author's STB (`192.168.5.6`, 魔百和 B863AV3.1-M2).
> Change the IP in the GUI or via `--ip` / the `DEFAULT_TARGET_IP` constant.

## How it works

```
┌────────── PC (e.g. 192.168.5.222) ──────────┐        ┌────── STB 192.168.5.6 ──────┐
│  ffmpeg capture (fullscreen/window) → H.264  │  HTTP  │  Built-in DLNA renderer     │
│  ↓ local HTTP server (port 8090)             │───────▶│  (当贝投屏G1 / 多屏互动L2 /  │
│  media files served directly over HTTP       │  UPnP  │   MiPT / 我的小电视)         │
│  UPnP pushes SetAVTransportURI + Play ───────│───────▶│  pulls the stream & plays   │
└─────────────────────────────────────────────┘        └────────────────────────────┘
```

- **Media file casting**: the PC runs a small HTTP server that serves the file; UPnP tells the
  STB to play it (same mechanism as phone casting apps).
- **Web URL casting**: push an `http(s)` video / live stream / `.m3u8` link to the STB, which
  fetches and plays it itself.
- **Live screen/window casting**: `ffmpeg` captures the screen (fullscreen or a chosen window)
  with `gdigrab` → H.264 encode (software `libx264` by default; hardware `h264_mf` optional)
  → realtime MPEG-TS (or HLS) → pushed to the STB via UPnP.

## Verified (on the author's STB `192.168.5.6`)

| Feature | Strategy | Result |
|---|---|---|
| Media file (test mp4) | DLNA push | ✅ renderer enters PLAYING |
| Fullscreen live cast (real desktop) | MPEG-TS | ✅ PLAYING |
| **Window live cast (Notepad + audio)** | MPEG-TS | ✅ PLAYING |
| Fullscreen + **system audio** live cast | MPEG-TS | ✅ PLAYING (audio via VB-CABLE, −11.8 dB) |
| Test signal source | HLS | ✅ PLAYING |
| **Web URL (local / public)** | DLNA push | ✅ public Sintel trailer PLAYING on STB |
| Hardware encode (h264_mf) | — | ✅ 720p30 at 8× realtime |

Discovered DLNA renderers: `当贝投屏G1` (44037), `多屏互动L2 / HappyCast` (49152),
`MiPT AV Media Renderer` (1058), `我的小电视` (9958). The program auto-picks the best one,
or you can switch manually in the GUI.

## Requirements

- **Python 3.8+** (developed on 3.12.3). **Standard library only** — no `pip install` needed.
  The GUI uses `tkinter` (bundled with CPython on Windows).
- **ffmpeg**: only required for **screen/window casting** (detected at
  `C:\ffmpeg-standalone\bin\ffmpeg.exe` on the author's machine, or set the `FFMPEG` env var).
  Media-file and URL casting do **not** need ffmpeg.
- PC and STB must be on the **same LAN**.

## Quick start

### GUI (recommended)

Double-click **`启动投屏助手.bat`** (or `py run_gui.py`); the window opens maximized.

```
py run_gui.py
```

1. The STB IP defaults to `192.168.5.6`; click **发现设备** (Discover).
2. Pick the target in the device dropdown (best device is pre-selected).
3. Click **投屏全屏** / **投屏窗口** (refresh the window list first to pick a window) / **投媒体文件**.
4. **Web URL**: paste an `http(s)` address into the "网络链接" box → click **投网络链接**.
5. Parameters (tuned for smoothness by default): FPS 12, bitrate 2M, resolution "原始/Original",
   strategy "自动/Auto", hardware-acceleration **unchecked** (software `libx264` for best compatibility).
   If it stutters, lower FPS (10/8) or resolution (540/360) — more effective than lowering bitrate.
6. **Audio**: "同步声音到电视 / Sync audio to TV" is checked by default (system audio is cast
   together with the screen/window). Media/URL casting plays the file's own audio track.
7. Stop: click **停止投屏** (Stop) or close the window.

### Command line

```
py run_cli.py discover                                   # discover devices
py run_cli.py windows                                    # list castable window titles
py run_cli.py media --file "D:\video\movie.mp4"          # cast a local media file
py run_cli.py url --url "https://example.com/video.mp4" # cast a web link
py run_cli.py url --url "https://.../live.m3u8"          # cast an m3u8 live stream
py run_cli.py screen --mode full                         # cast fullscreen (audio on by default)
py run_cli.py screen --mode window --title "Chrome"      # cast a window (with audio)
py run_cli.py screen --mode full --audio off             # picture only, no audio
py run_cli.py screen --mode full --encoder libx264       # force software encode; auto=prefer h264_mf
py run_cli.py screen --mode full --resolution 540 --fps 10 --bitrate 2M  # lower res/fps = smoother
py run_cli.py screen --mode full --strategy hls          # use HLS strategy
py run_cli.py screen --mode full --strategy url          # start stream only; open manually in STB VLC
py run_cli.py stop                                       # stop
py run_cli.py volume                                     # get/set renderer volume
```

All subcommands accept `--ip <IP>` (default `192.168.5.6`), `--device <name>` (filter by
renderer name), `--device-index <n>`, and `--timeout <sec>`. `screen` adds: `--title`,
`--strategy {auto,mpegts,hls,url}`, `--fps`, `--bitrate`, `--rect WxH+X+Y`, `--source
{desktop,lavfi}` (lavfi = test pattern), `--audio {auto,off,<device>}`, `--encoder
{auto,libx264,<enc>}`, `--resolution {auto,原始,1080,720,540,360,WxH}`, `--port`.

### Firewall (important)

The STB accesses the PC's port 8090 to pull the stream. On first run, allow Windows Firewall
access, or pre-open ports 8090–8099 by running `tools\open_firewall.ps1` as Administrator.

## Casting audio to the TV

- **Media / URL casting**: the file's own audio track plays on the STB automatically.
- **Screen/window live casting**: system audio is captured and synced to the TV by default.
  Pipeline: system audio → (default playback device temporarily switched to `CABLE Input`) →
  VB-CABLE virtual soundcard → `CABLE Output` captured by ffmpeg → encoded into the stream.
- Capture device auto-detection order: `CABLE Output` (VB-CABLE) → Stereo Mix → others.
- During casting the PC speakers are muted (audio goes to the TV) and **restored automatically**
  when casting stops.
- GUI checkbox "同步声音到电视" can be toggled anytime; CLI: `--audio off` to disable,
  `--audio auto` to auto-detect, or pass a device name directly.
- **No VB-CABLE?** (1) Enable the sound card's built-in "Stereo Mix" (Sound settings → Recording
  → show disabled devices); the program detects it automatically. (2) If Stereo Mix is unavailable,
  install a virtual soundcard: run `tools\install_vb_cable.ps1` as Administrator (downloads &
  installs VB-CABLE, free), reboot, and `CABLE Output` is detected automatically.

## Casting strategies

| Strategy | Latency | Smoothness | Notes |
|---|---|---|---|
| MPEG-TS (default "auto" usually picks this) | lower (~2–5 s) | depends on renderer's realtime handling | single continuous stream, good realtime; may drop frames on weak boxes |
| HLS | higher (~4–8 s) | usually more stable | 1 s segments the box downloads; good for 乐播-class boxes |
| URL-only (VLC) | higher | **smoothest** | stream is only started on the PC; open the address manually in the STB's VLC |

**Suggestion**: try "auto" (MPEG-TS) first; if it stutters → HLS; if still bad → URL-only (VLC)
on the STB (most robust, smoothest).

**Encoder auto-fallback**: defaults to software encode (`libx264`, best compatibility, verified
stable on 多屏互动L2). When hardware acceleration is enabled, if the TV doesn't actually start
playing (the program checks whether the renderer really pulled stream data), it retries once with
software encode, then falls back to HLS — it won't hang forever (cost: a few extra seconds at start).

**Fixing stutter (most effective first)**:
1. **Lower resolution** (540 or 360, or `--resolution 540`): encoding load is mainly
   resolution × FPS; bitrate barely matters — accept slight blur for a much smoother picture.
2. **Lower FPS** (10, even 8; CLI `--fps 10`).
3. **Hardware acceleration**: unchecked by default (software `libx264`); check it to cut CPU load.
4. **Switch strategy**: HLS or URL-only (VLC).
5. Bitrate (`--bitrate 2M`) helps little with stutter; it mainly affects sharpness.

## Optional: install an APK on the STB as fallback (usually unnecessary)

If DLNA live streaming is unstable on your box, install **VLC for Android**:

1. STB: enable "Developer options → USB/ADB debugging" (魔百和: Settings → General → About →
   tap build number repeatedly).
2. Download VLC APK (arm64, https://get.videolan.org/vlc-android/).
3. On the PC: `powershell -ExecutionPolicy Bypass -File tools\install_vlc_apk.ps1 -BoxIp 192.168.5.6 -ApkPath C:\path\to\vlc.apk`.
4. Use the "URL-only (VLC)" strategy and paste the shown address into the STB's VLC "Network stream".

> Note: the author's box already has multiple DLNA renderers (乐播/多屏互动L2, 当贝投屏G1, MiPT);
> both media and live casting work without any extra APK.

## Troubleshooting

- **Empty window list**: click "刷新窗口 / Refresh windows"; the target window must be visible
  and not minimized.
- **Casting a window then switching to another window → TV picture freezes (audio continues)**:
  Windows `gdigrab` stops producing new frames when the captured window is occluded/minimized.
  Keep the cast window visible (bring it to front), or use fullscreen casting.
- **No picture for a web URL**: confirm the link opens in a PC browser and the STB can reach it
  (public links need internet on the box; LAN links need same network).
- **Stutter**: default is software encode (`libx264`); if CPU is high but still stutters, enable
  GUI "硬件加速编码 / hardware acceleration", or lower FPS(10)/resolution(540); use 5 GHz Wi-Fi.
- **No audio on TV**: ensure GUI "同步声音到电视" is checked (or CLI without `--audio off`);
  ensure VB-CABLE is installed or Stereo Mix enabled; check the log for "声音采集: ..."; the
  default playback device restores after stopping.
- **Black screen / renderer stuck on STOPPED**: switch strategy (auto→MPEG-TS→HLS→URL), or lower
  bitrate(2M)/FPS(10); some boxes buffer slowly — wait 10–20 s.
- **High latency**: realtime streams normally have 2–8 s latency (depends on STB buffering) — normal.
- **Can't discover devices**: confirm PC and STB are on the same subnet; the casting app is in the
  foreground on the box; click "发现设备" a few more times.
- **STB can't pull the stream**: check Windows Firewall allows port 8090 (see above).

## Project structure

```
PCtouping/
├── 启动投屏助手.bat        # double-click to launch the GUI
├── run_gui.py / run_cli.py # entry points
├── cast_tv/
│   ├── upnp.py             # SSDP discovery + SOAP control (SetAVTransportURI/Play/Stop/volume)
│   ├── server.py           # local HTTP: media files (Range) / live TS / HLS
│   ├── screen.py           # ffmpeg gdigrab capture + window enumeration
│   ├── cast.py             # casting controller
│   ├── audio.py            # system audio capture / default playback device switching
│   ├── gui.py / cli.py     # GUI / command line
│   └── config.py           # global config (default IP/port, MIME map, ...)
├── tests/smoke_test.py     # local smoke test (no STB needed)
├── tests/e2e_test.py       # end-to-end test (briefly shows a test picture on the TV)
├── tools/open_firewall.ps1 # open ports 8090–8099
├── tools/set_default_audio.ps1 # switch/restore default playback device (for audio casting)
├── tools/install_vlc_apk.ps1
└── probe/                  # DLNA device descriptions captured during development (reference)
```
