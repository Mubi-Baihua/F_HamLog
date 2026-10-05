# -*- coding: utf-8 -*-
"""应用数据目录解析（开发模式 / Nuitka 打包后均可用）。

数据文件统一放在包内 ``file/`` 子目录（开发时即 ``src/f_hamlog/file``）。
解析顺序：
  1) 环境变量 ``F_HAMLOG_DATA_DIR``（测试 / 调试用，最高优先）；
  2) 当前工作目录（其下若存在 ``file/``，典型如测试把临时副本 chdir 到这里）；
  3) 可执行文件所在目录（Nuitka 打包后 ``file/`` 在 exe 旁边）；
  4) 本模块所在目录（开发模式 ``src/f_hamlog``）。
"""
import os
import sys

_DATA_SUBDIR = 'file'


def _app_base_dir():
    override = os.environ.get('F_HAMLOG_DATA_DIR')
    if override:
        return override
    candidates = []
    try:
        candidates.append(os.getcwd())
    except Exception:
        pass
    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    for d in candidates:
        if os.path.isdir(os.path.join(d, _DATA_SUBDIR)):
            return d
    return candidates[-1] if candidates else os.getcwd()


DATA_DIR = _app_base_dir()


def app_path(rel):
    """把 ``file/xxx`` 这类数据相对路径解析为绝对路径。

    ``rel`` 通常带 ``file/`` 前缀（与历史写法一致），例如
    ``app_path('file/m_xml.txt')``。
    """
    if os.path.isabs(rel):
        return rel
    return os.path.normpath(os.path.join(DATA_DIR, rel))
