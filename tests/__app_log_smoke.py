# -*- coding: utf-8 -*-
"""运行日志（app_log）离屏冒烟：落盘位置、四路来源、保留三天、幂等与拆除。

不碰真实数据目录：把 ``paths.app_path`` 打到临时目录（``file/log`` 就在那儿）。
"""
import datetime
import io
import logging
import os
import sys
import tempfile
import threading
import traceback

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from f_hamlog import app_log, paths

TMP = tempfile.mkdtemp(prefix='fhl_applog_')
LOG_DIR = os.path.join(TMP, 'file', 'log')
_orig_app_path = paths.app_path
paths.app_path = lambda rel: os.path.join(TMP, rel)

_passed = []
_failed = []


def ok(name, cond, detail=''):
    if cond:
        _passed.append(name)
        print('[PASS] %s' % name)
    else:
        _failed.append(name)
        print('[FAIL] %s   %s' % (name, detail))


def read_log(path=None):
    path = path or LOG_PATH
    try:
        with io.open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def flush_log():
    for h in logging.getLogger().handlers:
        try:
            h.flush()
        except Exception:
            pass


# —— L1 装配：目录、文件名、返回路径 ——
LOG_PATH = app_log.setup()
ok('L1 setup 返回当天日志路径', LOG_PATH and os.path.isfile(LOG_PATH), LOG_PATH)
ok('L1b 日志目录 = <数据目录>/file/log',
   os.path.normcase(os.path.dirname(LOG_PATH)) == os.path.normcase(LOG_DIR),
   os.path.dirname(LOG_PATH))
_today = datetime.date.today().strftime('%Y-%m-%d')
ok('L1c 文件名按自然日 = F_HamLog_YYYY-MM-DD.log',
   os.path.basename(LOG_PATH) == 'F_HamLog_%s.log' % _today,
   os.path.basename(LOG_PATH))

# —— L2 启动横幅（版本 / python / 数据目录） ——
flush_log()
text = read_log()
ok('L2 启动横幅写入了版本与平台信息',
   'F HamLog 启动' in text and 'version=' in text and 'platform=' in text
   and '数据目录=' in text, text[:200])

# —— L3 stdout（项目里大量 print）—— 
print('L3-stdout-标记-中文-OK')
flush_log()
ok('L3 print 的内容进了日志', 'L3-stdout-标记-中文-OK' in read_log())

# —— L4 stderr —— 
sys.stderr.write('L4-stderr-标记\n')
flush_log()
ok('L4 stderr 的内容进了日志', 'L4-stderr-标记' in read_log())

# —— L5 Qt 自己的消息（qInstallMessageHandler）——
try:
    from PySide6.QtCore import qWarning
    qWarning('L5b-Qt警告-标记')
    flush_log()
    ok('L5b Qt 警告也进了日志',
       '[Qt warning]' in read_log() and 'L5b-Qt警告-标记' in read_log(),
       read_log()[-300:])
except Exception as _e:                     # PySide6 不可用时不判失败
    ok('L5b Qt 警告也进了日志（跳过：无 PySide6）', isinstance(_e, ImportError), repr(_e))

# —— L6 logging 主动记录（代码里 logging.getLogger 直接写）——
logging.getLogger('f_hamlog.demo').warning('L6-logging-标记 %s', 42)
flush_log()
ok('L6 logging 记录进了日志', 'L6-logging-标记 42' in read_log()
   and '[WARNING]' in read_log())

# —— L7 未捕获异常（主线程钩子）—— 
try:
    _x = 1 / 0
except ZeroDivisionError:
    _et, _ev, _tb = sys.exc_info()
sys.excepthook(_et, _ev, _tb)
flush_log()
text = read_log()
ok('L7 主线程未捕获异常：完整 traceback + 异常类型',
   '未捕获异常' in text and 'Traceback (most recent call last)' in text
   and 'ZeroDivisionError' in text and 'division by zero' in text)
ok('L7b traceback 带源码行号（不是只有一行消息）',
   'line ' in text and '__app_log_smoke.py' in text)

# —— L8 线程异常（threading.excepthook）—— 
def _boom():
    raise RuntimeError('L8-线程异常-标记')


_t = threading.Thread(target=_boom, name='L8-线程')
_t.start()
_t.join()
flush_log()
text = read_log()
ok('L8 线程未捕获异常：线程名 + traceback + 异常信息',
   '线程 L8-线程 未捕获异常' in text and 'RuntimeError: L8-线程异常-标记' in text,
   text[-500:])

# —— L9 C 层崩溃栈文件（faulthandler 需要常开句柄）—— 
ok('L9 崩溃栈文件已创建（faulthandler 生效）',
   os.path.isfile(app_log.crash_path()) and app_log._state['crash_fp'] is not None,
   app_log.crash_path())

# —— L10 不换行结尾的输出在 flush 时落盘 —— 
sys.stdout.write('L10-无换行尾巴')
sys.stdout.flush()
flush_log()
_has_tail = 'L10-无换行尾巴' in read_log()
sys.stdout.write('\n')          # 收尾换行：否则后面的 PASS 行会被拼到同一行
ok('L10 结尾没有换行的输出也能落盘', _has_tail)

# —— L11/L12 Tee 本身：原流为 None（打包后窗口版）也不崩 ——
_sink = io.StringIO()
_tee = app_log._StreamTee(_sink, logging.INFO)
_n = _tee.write('L11-双写-标记\n')
flush_log()
ok('L11 Tee 同时写原流与日志',
   _sink.getvalue() == 'L11-双写-标记\n' and 'L11-双写-标记' in read_log(), _sink.getvalue())
_tee_none = app_log._StreamTee(None, logging.INFO)
_ret = _tee_none.write('L12-无原流-标记\n')
_tee_none.flush()
flush_log()
ok('L12 原流为 None（窗口版 exe）时只记日志、不抛异常',
   _ret == len('L12-无原流-标记\n') and 'L12-无原流-标记' in read_log())

# —— L13 保留三天：今天 / 昨天 / 前天留着，更早的删掉 ——
today = datetime.date.today()
made = {}
for _delta in (0, 1, 2, 3, 5):
    _day = today - datetime.timedelta(days=_delta)
    _p = os.path.join(LOG_DIR, 'F_HamLog_%s.log' % _day.strftime('%Y-%m-%d'))
    if not os.path.exists(_p):
        with io.open(_p, 'w', encoding='utf-8') as f:
            f.write('x\n')
    made[_delta] = _p
# 认不出日期的一个文件（按 mtime 判）——刚刚创建，必须留下
_stray = os.path.join(LOG_DIR, 'old_unknown.log')
with io.open(_stray, 'w', encoding='utf-8') as f:
    f.write('x\n')
_removed = app_log.purge_old_logs(days=3, directory=LOG_DIR)
ok('L13 三天前的日志被删掉', _removed >= 2, 'removed=%d' % _removed)
ok('L13b 今天 / 昨天 / 前天都还在',
   all(os.path.exists(made[d]) for d in (0, 1, 2)),
   str({d: os.path.exists(made[d]) for d in (0, 1, 2)}))
ok('L13c 3 天前 / 5 天前的已删除',
   not os.path.exists(made[3]) and not os.path.exists(made[5]))
ok('L13d 认不出日期的新文件按 mtime 保留', os.path.exists(_stray))

# —— L14 幂等：重复 setup 不重复挂 handler ——
_again = app_log.setup()
_flags = [h for h in logging.getLogger().handlers if getattr(h, '_fhamlog', False)]
ok('L14 重复 setup 幂等（同一路径、只有一个文件 handler）',
   _again == LOG_PATH and len(_flags) == 1, '%d 个 handler' % len(_flags))

# —— L15 teardown：恢复流与钩子 ——
_stdout_type = type(sys.stdout)
app_log.teardown()
ok('L15 teardown 还原 sys.stdout / excepthook',
   not isinstance(sys.stdout, app_log._StreamTee)
   and sys.excepthook is not app_log._excepthook,
   '%s / %s' % (_stdout_type, sys.excepthook))

paths.app_path = _orig_app_path
print('')
print('通过 %d / %d' % (len(_passed), len(_passed) + len(_failed)))
print('RESULT=' + ('ALL PASS' if not _failed else 'FAILED: ' + ', '.join(_failed)))
print('日志目录（临时）：' + LOG_DIR)
