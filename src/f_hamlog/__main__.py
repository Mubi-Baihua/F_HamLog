# -*- coding: utf-8 -*-
"""F HamLog 入口。

启动顺序刻意写成「先兜底日志 → 再导入 f_hamlog → 装配 app_log → 再导入 main」：
打包后的「双击没反应」大多发生在导入阶段，此时 app_log 还没生效，日志一片空白。
下面这段 ``_boot_*`` **只用标准库、不依赖 f_hamlog 的任何模块**，专门负责在这种
情况下留下痕迹（写到 exe 旁的 file/log，写不进去就退到 %LOCALAPPDATA%\\F_HamLog\\log）。
"""
import datetime
import os
import sys
import traceback

_BOOT_PREFIX = 'F_HamLog_boot'


def _boot_candidates():
    """兜底日志的候选目录（按优先级）。

    1) **和主日志同目录**：能导入 ``f_hamlog.paths`` 就听它的。开发时数据目录是
       ``src/f_hamlog``，打包后是 exe 旁，两者都落在用户能找得到的地方；
       少了这一步，开发运行的 boot 日志会跑进 ``.venv\\Scripts\\file\\log``。
    2) exe 旁 ``file/log``：包导入失败时（正是要排查的场景）只能靠这个。
    3) 用户目录 / 临时目录：exe 装在只读位置时的最后退路。
    """
    dirs = []
    try:
        from f_hamlog import paths
        d = paths.app_path(os.path.join('file', 'log'))
        if d:
            dirs.append(d)
    except Exception:
        pass
    try:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cand = os.path.join(exe_dir, 'file', 'log')
        if cand not in dirs:
            dirs.append(cand)
    except Exception:
        pass
    for env in ('LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP'):
        base = os.environ.get(env)
        if not base:
            continue
        cand = os.path.join(base, 'F_HamLog', 'log')
        if cand not in dirs:
            dirs.append(cand)
    return dirs


def _boot_write(text):
    """把 ``text`` 追加到第一个能写的兜底日志，返回落盘路径（全失败返回 ``''``）。"""
    for d in _boot_candidates():
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, '%s_%s.log' % (
                _BOOT_PREFIX, datetime.date.today().strftime('%Y-%m-%d')))
            with open(path, 'a', encoding='utf-8', errors='replace') as f:
                f.write(text)
                f.flush()
            return path
        except Exception:
            continue
    return ''


def _boot(stage, detail=''):
    """记一行启动痕迹；自己绝不能抛异常。"""
    try:
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        text = '%s [boot] %s\n' % (stamp, stage)
        if detail:
            text += detail if detail.endswith('\n') else detail + '\n'
        _boot_write(text)
    except Exception:
        pass


def _boot_start(mode):
    try:
        detail = 'exe=%s\nargv=%s\ncwd=%s\npackage=%r frozen=%s' % (
            sys.executable, sys.argv, os.getcwd(), __package__,
            bool(getattr(sys, 'frozen', False)))
    except Exception:
        detail = ''
    _boot('启动（%s）' % mode, detail)


def _boot_setup_log():
    """导入并装配 app_log；失败只记录、不打断启动。"""
    try:
        from f_hamlog import app_log
    except Exception:
        _boot('导入 f_hamlog.app_log 失败（后续日志不可用）', traceback.format_exc())
        return None
    try:
        path = app_log.setup()
    except Exception:
        _boot('app_log.setup() 抛异常', traceback.format_exc())
        return None
    try:
        reason = app_log.last_error()
    except Exception:
        reason = ''
    if path:
        _boot('app_log 就绪：%s' % path)
    else:
        _boot('app_log 未能落盘（找不到可写目录或建文件失败）', reason)
    if reason and path:
        _boot('app_log 装配告警', reason)
    return path


# Support both invocation styles:
#   python -m f_hamlog                 -> package context, __package__ == "f_hamlog"
#   python src/f_hamlog/__main__.py    -> script context, __package__ in (None, "")
if __package__ in (None, ""):
    # Direct script execution: make the parent of this file (src/) importable.
    _src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
    _boot_start('脚本模式')
    _boot_setup_log()
    # Import the *callable* `main` from the submodule (not the module itself).
    try:
        from f_hamlog.main import main
    except Exception:
        # 导入失败 = 程序注定打不开：留下完整 traceback 再照旧抛出，
        # 否则窗口版 exe 只会「一闪而过」，什么都查不到。
        _boot('导入 f_hamlog.main 失败（程序无法启动）', traceback.format_exc())
        raise
else:
    _boot_start('包模式')
    _boot_setup_log()
    try:
        from .main import main
    except Exception:
        _boot('导入 f_hamlog.main 失败（程序无法启动）', traceback.format_exc())
        raise


if __name__ == '__main__':
    _boot('调用 main()')
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        _boot('main() 抛出未捕获异常', traceback.format_exc())
        raise
