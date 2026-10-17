# -*- coding: utf-8 -*-
import sys
import os

# Support both invocation styles:
#   python -m f_hamlog                 -> package context, __package__ == "f_hamlog"
#   python src/f_hamlog/__main__.py    -> script context, __package__ in (None, "")
if __package__ in (None, ""):
    # Direct script execution: make the parent of this file (src/) importable.
    _src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
    # 日志要在「导入 main」之前装配：导入期的 print / 异常（含打包后闪退）也能落盘。
    try:
        from f_hamlog import app_log

        app_log.setup()
    except Exception:
        pass   # 日志装不上不能阻止程序启动
    # Import the *callable* `main` from the submodule (not the module itself).
    from f_hamlog.main import main
else:
    try:
        from . import app_log

        app_log.setup()
    except Exception:
        pass
    from .main import main


if __name__ == '__main__':
    main()
