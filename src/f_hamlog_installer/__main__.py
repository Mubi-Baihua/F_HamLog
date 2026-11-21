# -*- coding: utf-8 -*-
"""``python -m f_hamlog_installer`` 的入口。

不带参数（双击 exe 也是这种）→ 开图形界面；
带参数（``list`` / ``download`` / ``install`` …）→ 走命令行，一次都不弹窗。
"""

import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == 'gui':
        from f_hamlog_installer.gui import main as gui_main
        return gui_main()
    from f_hamlog_installer.cli import main as cli_main
    return cli_main(argv)


if __name__ == '__main__':
    sys.exit(main())
