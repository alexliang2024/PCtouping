# -*- coding: utf-8 -*-
"""启动图形界面。双击 启动投屏助手.bat 或本文件即可。"""
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from cast_tv.gui import main  # noqa: E402

if __name__ == "__main__":
    main()