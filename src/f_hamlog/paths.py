# -*- coding: utf-8 -*-
"""应用数据目录解析（开发模式 / Nuitka 打包后均可用）。

数据文件统一放在包内 ``file/`` 子目录（开发时即 ``src/f_hamlog/file``）。
解析顺序：
  1) 环境变量 ``F_HAMLOG_DATA_DIR``（测试 / 调试用，最高优先）；
  2) 可执行文件所在目录（Nuitka 打包后 ``file/`` 在 exe 旁边）；
  3) 本模块所在目录（开发模式 ``src/f_hamlog``）；
  4) 当前工作目录（**最后**才考虑——任何进程都能在 cwd 下造出 ``file/``）。

「是不是真数据目录」以 ``_DATA_MARKERS`` 文件判定（见 ``_looks_like_data_dir``）：
**一个只有空目录形态的 ``file/`` 不算**。2026-10-16 的教训：旧版 ``backup.py`` 用
cwd 相对的 ``file/project_backup.fhl`` 写备份，在仓库根跑一次就凭空造出
``<仓库根>/file/``；此后 cwd 候选把它当成数据目录 → ``app_path()`` 全部解析到仓库根，
``file/main.fhl``、``file/pack_list.txt`` 集体 FileNotFoundError。

⚠️ 把**模块目录排在 cwd 之前**是第二次加固（同日）：标记文件并不可靠——跑了
一个「src 布局迁移前」的遗留测试（它按相对路径写 ``file/m_xml.txt``、``file/amateur.tle``），
那个假 ``file/`` 就凭空长出了标记，于是又被当成真数据目录。**应用自己的目录才是可信来源**，
cwd 只做兜底。需要指定数据目录时请用 ``F_HAMLOG_DATA_DIR``。
"""
import os
import sys

_DATA_SUBDIR = 'file'

# 数据目录的「身份标记」：真正的应用数据目录里必然有其中至少一个。
# 只用来挡「被误建出来的空 file/」，不做更严格的校验。
_DATA_MARKERS = ('m_xml.txt', 'main.fhl', 'amateur.tle', 'pack_list.txt')


def _looks_like_data_dir(d):
    """``d/file/`` 存在且里面有数据标记文件 → 认为 d 是一份真正的应用数据目录。"""
    sub = os.path.join(d, _DATA_SUBDIR)
    if not os.path.isdir(sub):
        return False
    try:
        return any(os.path.exists(os.path.join(sub, m)) for m in _DATA_MARKERS)
    except Exception:
        return False


def _app_base_dir():
    override = os.environ.get('F_HAMLOG_DATA_DIR')
    if override:
        return override
    candidates = []
    # 应用自己的位置优先：打包后在 exe 旁边，开发时在包目录（src/f_hamlog）。
    # cwd 放最后——它是唯一「别人也能往里塞东西」的候选，历史上两次事故都出在它身上。
    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    try:
        candidates.append(os.getcwd())
    except Exception:
        pass
    # 先挑「看起来真的是数据目录」的（挡住 cwd 下被误建的 file/）
    for d in candidates:
        if _looks_like_data_dir(d):
            return d
    # 退路：只要 file/ 存在就认（保持历史行为，兼容「数据目录里只有非标记文件」的布置）
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
