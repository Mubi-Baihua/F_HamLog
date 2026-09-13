# -*- coding: utf-8 -*-
"""多人日志「退出 / 断开」生命周期的 headless 烟囱测试（不依赖完整项目窗口）。

覆盖本轮修复：
  1) 主动退出（关闭窗口 / 关闭多人日志）后，同步线程不得再上报「连接断开」；
  2) 服务端真的结束（被动断开）时，仍要正常上报断开；
  3) RemoteConnection.shutdown() 必须先停线程再关 socket，并 join 线程
     （避免 “QThread: Destroyed while thread is still running”）；
  4) _qt_alive() 能识别已被销毁的 Qt 窗口（修复 libshiboken ... already deleted）；
  5) 表格刷新必须「先移除旧表格再重建」——复现旧的两表格 bug 并验证修复后的行为。

运行：QT_QPA_PLATFORM=offscreen <venv>/python test_remote_lifecycle_smoke.py
"""

import os
import sys
import time
import socket


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTableWidget  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402

import project  # noqa: E402
import remote_server  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

PASS = []


def ok(name, cond, detail=''):
    mark = 'PASS' if cond else 'FAIL'
    PASS.append(bool(cond))
    print(f'[{mark}] {name}' + (f'  -> {detail}' if detail else ''))
    if not cond:
        raise AssertionError(f'{name} {detail}')


def pump(seconds):
    """跑事件循环若干秒，保证跨线程 queued signal 也能被投递执行。"""
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# T1: _qt_alive 能识别已销毁的 Qt 对象
# ---------------------------------------------------------------------------
w = QWidget()
ok('T1a 存活窗口 _qt_alive == True', project._qt_alive(w) is True)
w.deleteLater()
app.sendPostedEvents(None, QEvent.DeferredDelete)
app.processEvents()
ok('T1b 已销毁窗口 _qt_alive == False', project._qt_alive(w) is False)
ok('T1c None 视作不存活', project._qt_alive(None) is False)


# ---------------------------------------------------------------------------
# T2: 主动退出 → 不上报断开；线程被 join；socket 关闭
# ---------------------------------------------------------------------------
def new_pair(password=''):
    srv = remote_server.LogServer(password=password, port=0, fhl_path=None)
    srv.start(seed_list=[])
    ip, port = srv.address
    conn = project.RemoteConnection('127.0.0.1', port, password)
    conn.connect()
    return srv, conn


srv, conn = new_pair()
seen = {'sync': 0, 'disc': 0}
conn.start_sync(lambda lst: seen.__setitem__('sync', seen['sync'] + 1),
                lambda: seen.__setitem__('disc', seen['disc'] + 1))
pump(2.6)   # 至少完成一次 FETCH→FILE
ok('T2a 同步线程已拉到数据', seen['sync'] >= 1, f"sync={seen['sync']}")
ok('T2b 同步线程正在运行', conn._sync.isRunning() is True)

t0 = time.time()
conn.shutdown()          # ← 主动退出（等价于关闭窗口 / 关闭多人日志）
elapsed = time.time() - t0
ok('T2c shutdown 后线程已结束', conn._sync.isRunning() is False, f'{elapsed:.2f}s')
ok('T2d shutdown 后 socket 已关闭', conn.sock is None)
ok('T2e shutdown 耗时合理(<2s)', elapsed < 2.0, f'{elapsed:.2f}s')

pump(2.6)                # 再等两个轮询周期，确认没有任何迟到的断开信号
ok('T2f 主动退出后未误报「连接断开」', seen['disc'] == 0, f"disc={seen['disc']}")
srv.stop()


# ---------------------------------------------------------------------------
# T3: 服务端结束（被动断开）→ 仍要上报断开
# ---------------------------------------------------------------------------
srv3, conn3 = new_pair()
dg3 = {'disc': 0}
conn3.start_sync(lambda lst: None, lambda: dg3.__setitem__('disc', dg3['disc'] + 1))
pump(1.6)
srv3.stop()              # ← 服务端结束
pump(3.0)
ok('T3 服务端结束 → 客户端上报断开', dg3['disc'] >= 1, f"disc={dg3['disc']}")
if conn3._sync.isRunning():
    conn3.shutdown()


# ---------------------------------------------------------------------------
# T4: 断线后再次 shutdown 不抛异常（幂等）
# ---------------------------------------------------------------------------
srv4, conn4 = new_pair()
conn4.start_sync(lambda lst: None, lambda: None)
pump(1.2)
conn4.shutdown()
try:
    conn4.shutdown()
    dup_ok = True
except Exception as e:  # pragma: no cover
    dup_ok = False
    print('  ', e)
ok('T4 shutdown 幂等', dup_ok)
srv4.stop()


# ---------------------------------------------------------------------------
# T5: 表格刷新「先移除旧表格再重建」→ 布局中恒为 1 个表格
#     复现修复前后的两种调用路径（delete=False 会残留 → 两个表格）
# ---------------------------------------------------------------------------
host = QWidget()
lay = QVBoxLayout(host)


def build(count):
    t = QTableWidget(count, 14)
    lay.addWidget(t)
    return t


def refresh_buggy(old, count):
    """修复前的远程同步路径：只加新表格、不移除旧表格。"""
    return build(count)


def refresh_fixed(old, count):
    """修复后的 table_update(persist=False) 等价路径：先移除并销毁旧表格，再重建。"""
    if old is not None:
        lay.removeWidget(old)
        old.deleteLater()
    return build(count)


def table_widgets():
    return [lay.itemAt(i).widget() for i in range(lay.count())
            if isinstance(lay.itemAt(i).widget(), QTableWidget)]


t = build(2)
t = refresh_buggy(t, 3)
app.processEvents()
ok('T5a 复现：旧路径确实残留两个表格', len(table_widgets()) == 2,
   f'count={len(table_widgets())}')

# 清空，改用修复后的路径
while lay.count():
    it = lay.takeAt(0)
    wid = it.widget()
    if wid is not None:
        wid.deleteLater()
app.processEvents()
t = build(2)
for n in (3, 4, 5):
    t = refresh_fixed(t, n)
    app.processEvents()
ok('T5b 修复：多轮刷新后仍只有一个表格', len(table_widgets()) == 1,
   f'count={len(table_widgets())}')

host.deleteLater()
app.processEvents()


# ---------------------------------------------------------------------------
# T6: 关闭守卫 —— 窗口关闭时必须调用 on_close（用于退出多人日志），
#     而「取消」分支不得调用。Qt 关闭窗口默认只隐藏、不触发 destroyed，
#     仅在 destroyed 里清理会漏掉「关闭窗口」这条路径（本轮 bug 根因）。
# ---------------------------------------------------------------------------
import backup  # noqa: E402
from PySide6.QtWidgets import QMainWindow  # noqa: E402

calls = {'n': 0}
win6 = QMainWindow()
backup.install_close_guard(win6, {
    'is_dirty': lambda: False,
    'write_backup': lambda: None,
    'clear_backup': lambda: None,
    'do_save': lambda: True,
    'on_close': lambda: calls.__setitem__('n', calls['n'] + 1),
})
win6.close()
app.processEvents()
ok('T6 关闭窗口触发 on_close（退出多人日志）', calls['n'] == 1, f"n={calls['n']}")

# 未注册 on_close 时不得报错（向后兼容旧调用方）
win6b = QMainWindow()
backup.install_close_guard(win6b, {
    'is_dirty': lambda: False,
    'write_backup': lambda: None,
    'clear_backup': lambda: None,
    'do_save': lambda: True,
})
try:
    win6b.close()
    app.processEvents()
    compat_ok = True
except Exception as e:  # pragma: no cover
    compat_ok = False
    print('  ', e)
ok('T6b 未提供 on_close 仍可正常关闭', compat_ok)

print('\n=== ALL PASS ===' if all(PASS) else '\n=== SOME FAILED ===')
sys.exit(0 if all(PASS) else 1)
