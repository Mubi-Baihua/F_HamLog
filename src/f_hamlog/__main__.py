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
    # Import the *callable* `main` from the submodule (not the module itself).
    from f_hamlog.main import main
else:
    from .main import main


if __name__ == '__main__':
    main()
