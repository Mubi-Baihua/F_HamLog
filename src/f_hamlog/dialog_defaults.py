# -*- coding: utf-8 -*-
"""文件对话框默认路径工具。

集中管理“选择路径 / 保存位置”类对话框的默认行为：
- 默认打开位置：桌面
- 默认保存文件名：空（由调用处传入桌面目录实现，不预填文件名）

这样所有需要选择路径或保存位置的窗口行为一致，便于统一维护。
"""
from PySide6.QtCore import QStandardPaths


def desktop_dir():
    """返回桌面目录路径，用作文件对话框的默认打开位置。

    取不到桌面路径（极少数环境）时回退为空字符串，此时对话框使用系统默认目录。
    """
    path = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
    return path if path else ''
