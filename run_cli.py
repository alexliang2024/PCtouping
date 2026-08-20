# -*- coding: utf-8 -*-
"""启动命令行。用法示例:
    python run_cli.py discover
    python run_cli.py windows
    python run_cli.py media --file "D:\\video.mp4"
    python run_cli.py screen --mode full --strategy auto
    python run_cli.py screen --mode window --title "记事本" --strategy hls
    python run_cli.py stop
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from cast_tv.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())