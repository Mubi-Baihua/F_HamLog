# -*- coding: utf-8 -*-
"""日志兜底冒烟：主数据目录不可写时，日志必须退到用户目录并留下原因。

打包安装到 Program Files 又没拿到管理员权限，正是这个场景 ——
以前 setup() 直接返回 ''，日志功能静默失效（「打不开又没日志」的主因之一）。
"""
import logging
import os
import sys
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from f_hamlog import app_log, paths  # noqa: E402

_passed = []
_failed = []


def ok(name, cond, detail=''):
    if cond:
        _passed.append(name)
        print('[PASS] %s' % name)
    else:
        _failed.append(name)
        print('[FAIL] %s   %s' % (name, detail))


# —— 让主目录指向一个绝对建不出来的位置（不存在的盘符）——
_orig_app_path = paths.app_path
paths.app_path = lambda rel: os.path.join('Z:\\fhl_no_such_drive', rel)

# 兜底目录改到临时目录，避免往真实的 %LOCALAPPDATA% 里丢文件
TMP = tempfile.mkdtemp(prefix='fhl_fallback_')
os.environ['LOCALAPPDATA'] = TMP

path = app_log.setup()

ok('B1 主目录不可写时 setup 仍返回路径', bool(path) and os.path.isfile(path), repr(path))
ok('B2 日志退到 %LOCALAPPDATA% 下',
   os.path.normcase(path).startswith(os.path.normcase(os.path.join(TMP, 'F_HamLog', 'log'))),
   path)
ok('B3 last_error 记录了原因',
   'Z:\\fhl_no_such_drive' in app_log.last_error(), app_log.last_error())
ok('B4 log_dir() 与真实落盘目录一致',
   os.path.normcase(app_log.log_dir()) == os.path.normcase(os.path.dirname(path)),
   app_log.log_dir())

logging.getLogger('f_hamlog.app').info('兜底目录可用标记-OK')
for h in logging.getLogger().handlers:
    try:
        h.flush()
    except Exception:
        pass
with open(path, encoding='utf-8', errors='replace') as f:
    content = f.read()
ok('B5 兜底目录里能正常写日志', '兜底目录可用标记-OK' in content)
ok('B6 横幅里写明了装配告警', '日志装配告警' in content)

app_log.teardown()
ok('B7 teardown 清空 last_error / dir',
   app_log.last_error() == '' and app_log.log_dir() != path)

paths.app_path = _orig_app_path

print('')
print('通过 %d / %d' % (len(_passed), len(_passed) + len(_failed)))
print('RESULT=%s' % ('ALL PASS' if not _failed else 'FAILED'))
sys.exit(0 if not _failed else 1)
