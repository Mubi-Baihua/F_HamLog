# -*- coding: utf-8 -*-
"""运行日志：stdout / stderr、未捕获异常、线程异常、Qt 消息、C 层崩溃栈全部落盘。

为什么要有它
------------
打包成 ``--windows-console-mode=disable`` 之后没有控制台，``print`` 和 traceback 全部丢失，
用户报「点了没反应 / 闪退」时无从查起。这里把**所有能拿到的输出**都写进 ``file/log/``，
事后让人把日志文件发来即可。

落盘规则
--------
* 目录：``app_path('file/log')``（绝对路径，服从数据目录解析，**不受 cwd 影响**）。
* 文件：``F_HamLog_YYYY-MM-DD.log``（按自然日切分，直接整份发人）；
  C 层崩溃栈单独写 ``F_HamLog_crash_YYYY-MM-DD.log``（faulthandler 需要常开的文件句柄）。
* 保留：**最近三天（今天 + 前两天）**，启动时清掉更早的 ``*.log``。

四路来源
--------
1. 根 logger（代码里 ``logging.getLogger(__name__)`` 直接用）；
2. ``sys.stdout`` / ``sys.stderr`` 换成 :class:`_StreamTee` —— 项目里大量 ``print``
   原样进日志，同时（有控制台时）照旧打到屏幕；
3. ``sys.excepthook`` / ``threading.excepthook`` —— 主线程与 QThread 的未捕获异常；
4. ``faulthandler`` + Qt 的 ``qInstallMessageHandler`` —— 段错误 / Qt 警告也不丢。

两条硬性纪律
------------
* **日志自己绝不能把程序带崩**：所有入口都 try 兜住，写失败就静默跳过。
* **幂等**：``setup()`` 重复调用只装一次（``__main__`` 与 ``main()`` 都会调）。
"""
import datetime as _dt
import faulthandler
import io
import logging
import os
import platform
import re
import sys
import threading
import traceback

from f_hamlog import paths

LOG_DIR_NAME = os.path.join('file', 'log')
RETENTION_DAYS = 3
LOG_PREFIX = 'F_HamLog'
CRASH_PREFIX = 'F_HamLog_crash'

_LOG_FMT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
_LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

_state = {
    'installed': False,
    'path': '',
    'handler': None,
    'stdout': None,
    'stderr': None,
    'excepthook': None,
    'thread_hook': None,
    'crash_fp': None,
}
_date_re = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


# ---------------------------------------------------------------- 目录与文件

def log_dir():
    """日志目录的绝对路径（不保证已存在）。"""
    try:
        return paths.app_path(LOG_DIR_NAME)
    except Exception:
        return ''


def log_path(day=None):
    """当天的主日志文件路径。"""
    day = day or _dt.date.today()
    return os.path.join(log_dir(), '%s_%s.log' % (LOG_PREFIX, day.strftime('%Y-%m-%d')))


def crash_path(day=None):
    """当天的崩溃栈文件路径（faulthandler 专用）。"""
    day = day or _dt.date.today()
    return os.path.join(log_dir(), '%s_%s.log' % (CRASH_PREFIX, day.strftime('%Y-%m-%d')))


def _date_from_name(name):
    """从文件名里取日期（``xxx_2026-10-17.log``）；取不到返回 None。"""
    m = _date_re.search(name)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def purge_old_logs(days=RETENTION_DAYS, directory=None):
    """删掉超过保留期的日志，返回删除的文件数。

    保留**今天 + 前 ``days-1`` 天**（``days=3`` → 今天 / 昨天 / 前天）。
    先看文件名里的日期，认不出就退回文件修改时间；删不掉（被占用）就跳过，
    绝不能因为清日志失败影响启动。
    """
    d = directory or log_dir()
    if not d or not os.path.isdir(d):
        return 0
    try:
        days = max(1, int(days))
    except (TypeError, ValueError):
        days = RETENTION_DAYS
    cutoff = _dt.date.today() - _dt.timedelta(days=days - 1)
    removed = 0
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    for name in names:
        if not name.lower().endswith('.log'):
            continue
        full = os.path.join(d, name)
        if not os.path.isfile(full):
            continue
        day = _date_from_name(name)
        if day is None:
            try:
                day = _dt.date.fromtimestamp(os.path.getmtime(full))
            except (OSError, OverflowError, ValueError):
                continue
        if day >= cutoff:
            continue
        try:
            os.remove(full)
            removed += 1
        except OSError:
            pass
    return removed


# ------------------------------------------------------------ stdout 分流器

class _StreamTee(io.TextIOBase):
    """把写入原样转给原流，同时**按行**记进日志。

    * 原流可以是 ``None`` —— 窗口版 exe 下 ``sys.stdout`` / ``sys.stderr`` 就是 None，
      此时只记日志（这正是打包后想看报错的场景）。
    * 按行切分：``print`` 分两次 write（正文 + ``\\n``），攒到换行才落一条日志，
      避免日志里冒出半行 + 大量空行。
    * 所有失败都吞掉：日志写不进去不能反过来打断程序运行。
    """

    def __init__(self, stream, level):
        self._stream = stream
        self._level = level
        self._buf = ''
        self._lock = threading.Lock()
        self._local = threading.local()
        self._logger = logging.getLogger('f_hamlog.output')

    # --- 流的基本属性（标准库/第三方库偶尔会探测） ---
    @property
    def encoding(self):
        return 'utf-8'

    @property
    def errors(self):
        return 'replace'

    def writable(self):
        return True

    def readable(self):
        return False

    def isatty(self):
        return False

    def fileno(self):
        if self._stream is not None:
            try:
                return self._stream.fileno()
            except Exception:
                pass
        raise io.UnsupportedOperation('fileno')

    # --- 主流程 ---
    def write(self, text):
        if not text:
            return 0
        if self._stream is not None:
            try:
                self._stream.write(text)
            except Exception:
                pass
        # 递归保护：万一日志落盘失败，logging 会往 sys.stderr（= 本 Tee）回灌错误信息，
        # 那又会触发落盘失败 —— 不加这个标记就是无限递归。
        if getattr(self._local, 'busy', False):
            return len(text)
        self._local.busy = True
        try:
            self._collect(text)
        except Exception:
            pass
        finally:
            self._local.busy = False
        return len(text)

    def _collect(self, text):
        lines = []
        with self._lock:
            self._buf += text
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                lines.append(line)
        for line in lines:
            if line.strip():
                self._logger.log(self._level, line)

    def flush(self):
        if self._stream is not None:
            try:
                self._stream.flush()
            except Exception:
                pass
        rest = ''
        with self._lock:
            rest, self._buf = self._buf, ''
        if rest.strip():
            try:
                self._logger.log(self._level, rest)
            except Exception:
                pass


# --------------------------------------------------------------- 异常钩子

def _format_exc(exc_type, exc_value, exc_tb):
    try:
        return ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        return '%r / %r\n' % (exc_type, exc_value)


def _excepthook(exc_type, exc_value, exc_tb):
    """主线程未捕获异常：整段 traceback 进日志，控制台照旧能看到。"""
    text = _format_exc(exc_type, exc_value, exc_tb)
    try:
        logging.getLogger('f_hamlog.crash').critical('未捕获异常：\n%s', text)
    except Exception:
        pass
    orig = _state.get('excepthook')
    if orig is not None and orig not in (_excepthook, sys.__excepthook__):
        # 别人装过定制钩子（IPython / 测试框架）→ 照旧交给它
        try:
            orig(exc_type, exc_value, exc_tb)
        except Exception:
            pass
        return
    # 默认钩子就是「把 traceback 打到 sys.stderr」，而 stderr 已被 Tee 接管 ——
    # 再调一次会让同一段 traceback 在日志里出现两遍（CRITICAL 一份、ERROR 一份）。
    # 所以直接写未接管的 sys.__stderr__：控制台照样能看到，日志只留一份。
    stream = getattr(sys, '__stderr__', None)
    if stream is not None:
        try:
            stream.write(text)
            stream.flush()
        except Exception:
            pass


def _thread_excepthook(args):
    """线程（含 QThread 里跑的 Python 代码）未捕获异常 → 日志。

    不调用默认实现：默认实现写 stderr，而 stderr 已被 Tee 接管，会重复记一遍。
    """
    try:
        name = getattr(getattr(args, 'thread', None), 'name', '?')
        logging.getLogger('f_hamlog.crash').critical(
            '线程 %s 未捕获异常：\n%s', name,
            _format_exc(args.exc_type, args.exc_value, args.exc_traceback))
    except Exception:
        pass


def _enable_faulthandler():
    """C 层崩溃（段错误 / 访问违例）也能留下栈：写进 crash 文件，句柄常开。"""
    try:
        fp = open(crash_path(), 'a', encoding='utf-8', errors='replace')
    except Exception:
        return
    try:
        faulthandler.enable(file=fp, all_threads=True)
        _state['crash_fp'] = fp
    except Exception:
        try:
            fp.close()
        except Exception:
            pass


def _install_qt_handler():
    """Qt 自己的 debug/warning/critical 也收进日志（Qt 警告常常是崩溃前的唯一线索）。"""
    try:
        from PySide6.QtCore import qInstallMessageHandler
    except Exception:
        return
    if getattr(_install_qt_handler, '_done', False):
        return
    # QtMsgType: 0=Debug 1=Warning 2=Critical 3=Fatal 4=Info
    levels = {0: logging.DEBUG, 1: logging.WARNING, 2: logging.CRITICAL,
              3: logging.CRITICAL, 4: logging.INFO}
    names = {0: 'debug', 1: 'warning', 2: 'critical', 3: 'fatal', 4: 'info'}
    log = logging.getLogger('f_hamlog.qt')

    def handler(mode, context, message):
        try:
            code = int(mode)
            where = ''
            try:
                if context is not None and context.file:
                    where = ' (%s:%s)' % (context.file, context.line)
            except Exception:
                where = ''
            log.log(levels.get(code, logging.INFO), '[Qt %s] %s%s',
                    names.get(code, 'msg'), message, where)
        except Exception:
            pass

    try:
        qInstallMessageHandler(handler)
        _install_qt_handler._done = True
    except Exception:
        pass


# ------------------------------------------------------------------- 启动横幅

def write_banner(extra=''):
    """在日志开头写一段环境信息 —— 排查问题时最有用的几行。"""
    try:
        from f_hamlog import __version__ as version
    except Exception:
        version = '?'
    log = logging.getLogger('f_hamlog.app')
    try:
        log.info('=' * 68)
        log.info('F HamLog 启动  version=%s  pid=%s', version, os.getpid())
        log.info('python=%s  frozen=%s', sys.version.split()[0],
                 bool(getattr(sys, 'frozen', False)))
        log.info('platform=%s', platform.platform())
        log.info('数据目录=%s', _safe_data_dir())
        log.info('日志文件=%s（保留 %d 天）', _state.get('path') or log_path(), RETENTION_DAYS)
        log.info('argv=%s  cwd=%s', sys.argv, os.getcwd())
        if extra:
            log.info(extra)
        log.info('=' * 68)
    except Exception:
        pass


def _safe_data_dir():
    try:
        return paths.DATA_DIR
    except Exception:
        return '?'


# ------------------------------------------------------------------- 对外接口

def setup(level=logging.INFO, retention_days=RETENTION_DAYS, banner=True):
    """装配日志系统，返回当天日志文件路径（失败返回 ``''``，程序照常运行）。

    ``__main__`` 和 ``main.main()`` 都会调用；重复调用只装一次。
    """
    if _state['installed']:
        return _state['path']
    d = log_dir()
    if not d:
        return ''
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return ''
    try:
        purge_old_logs(retention_days, d)
    except Exception:
        pass

    # 1) 文件 handler（先装，后面的所有钩子才有地方写）
    try:
        handler = logging.FileHandler(log_path(), mode='a', encoding='utf-8',
                                      errors='replace', delay=False)
        handler.setFormatter(logging.Formatter(_LOG_FMT, _LOG_DATEFMT))
        handler._fhamlog = True
        root = logging.getLogger()
        if not any(getattr(h, '_fhamlog', False) for h in root.handlers):
            root.addHandler(handler)
        if root.level > level or root.level == logging.NOTSET:
            root.setLevel(level)
        _state['handler'] = handler
        _state['path'] = handler.baseFilename
    except Exception:
        return ''
    # handler 自己写失败（磁盘满 / 文件被删）时，logging 默认会往 sys.stderr 打错误 ——
    # 而 stderr 已被 Tee 接管，会再触发一次落盘失败。关掉这条回灌通道。
    logging.raiseExceptions = False

    # 2) stdout / stderr 分流（打包后窗口版原流为 None，也照样记日志）
    try:
        _state['stdout'] = sys.stdout
        _state['stderr'] = sys.stderr
        sys.stdout = _StreamTee(sys.stdout, logging.INFO)
        sys.stderr = _StreamTee(sys.stderr, logging.ERROR)
    except Exception:
        pass

    # 3) 异常钩子
    try:
        _state['excepthook'] = sys.excepthook
        sys.excepthook = _excepthook
    except Exception:
        pass
    try:
        _state['thread_hook'] = threading.excepthook
        threading.excepthook = _thread_excepthook
    except Exception:
        pass

    # 4) C 层崩溃 + Qt 消息
    _enable_faulthandler()
    _install_qt_handler()

    _state['installed'] = True
    if banner:
        write_banner()
    return _state['path']


def teardown():
    """拆掉日志系统（测试/重启用）：恢复流与钩子、关掉文件句柄。"""
    try:
        if isinstance(sys.stdout, _StreamTee):
            try:
                sys.stdout.flush()
            except Exception:
                pass
            sys.stdout = _state.get('stdout')
    except Exception:
        pass
    try:
        if isinstance(sys.stderr, _StreamTee):
            try:
                sys.stderr.flush()
            except Exception:
                pass
            sys.stderr = _state.get('stderr')
    except Exception:
        pass
    try:
        if _state.get('excepthook') is not None:
            sys.excepthook = _state['excepthook']
    except Exception:
        pass
    try:
        if _state.get('thread_hook') is not None:
            threading.excepthook = _state['thread_hook']
    except Exception:
        pass
    try:
        faulthandler.disable()
    except Exception:
        pass
    fp = _state.get('crash_fp')
    if fp is not None:
        try:
            fp.flush()
            fp.close()
        except Exception:
            pass
        _state['crash_fp'] = None
    handler = _state.get('handler')
    if handler is not None:
        try:
            logging.getLogger().removeHandler(handler)
            handler.close()
        except Exception:
            pass
    _state.update({'installed': False, 'path': '', 'handler': None,
                   'stdout': None, 'stderr': None,
                   'excepthook': None, 'thread_hook': None})
    try:
        _install_qt_handler._done = False
    except Exception:
        pass
