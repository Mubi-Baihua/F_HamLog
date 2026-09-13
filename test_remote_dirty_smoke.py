# -*- coding: utf-8 -*-
"""多人日志「是否有未保存更改」判定的 headless 烟囱测试。

背景：旧实现里“未保存”= 当前内容 != 最近一次**本机写盘**的快照。多人日志下内容会被
同步线程整份替换（其中包含**他人**造成的改动），于是：
  - 每次同步都被判为“有未保存更改” → 1.5s 定时器把共享会话日志写进本机备份文件，
    下次启动 main.py 就会误报“恢复未保存的内容”，恢复还可能覆盖本机项目；
  - 关闭窗口时无端弹「未保存的更改」。

本轮判定规则：
  - 会话进行中：服务端即“已持久化”存储 → 同步/推送即视为已保存，本机不写备份、关闭不提示；
  - 会话结束（关闭多人日志 / 被动断开）：持久化责任回到本机文件，只有“内容相对最近一次
    写入本机文件确有变化”才算未保存，保留「不保存会丢内容」的安全网。

运行：QT_QPA_PLATFORM=offscreen <venv>/python test_remote_dirty_smoke.py
"""

import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

PASS = []
PROMPTS = []   # 记录所有被屏蔽掉的模态弹窗标题
REPORT = []    # 结果同时写文件，便于 headless 下取回（PowerShell 会吃掉 stdout）


def say(s):
    REPORT.append(s)
    print(s)
    try:
        with open('__dirty_out.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(REPORT) + '\n')
    except Exception:
        pass


def ok(name, cond, detail=''):
    mark = 'PASS' if cond else 'FAIL'
    PASS.append(bool(cond))
    say(f'[{mark}] {name}' + (f'  -> {detail}' if detail else ''))


def pump(seconds):
    """跑事件循环若干秒：既投递跨线程信号，也让 1.5s 备份定时器跳几拍。"""
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def _fake_exec(self, *a, **k):
    """屏蔽模态弹窗（关闭守卫用 msg.exec()，不屏蔽会卡死测试）。"""
    PROMPTS.append(self.windowTitle())
    return 0            # 等价于“没点任何按钮” → 守卫保持窗口打开


QMessageBox.exec = _fake_exec

import backup  # noqa: E402
import project  # noqa: E402
import remote_server  # noqa: E402

# 拦截关闭守卫的安装，直接拿到 project 内部注册的回调（is_dirty / texts），
# 比只看弹窗副作用更直接。
_orig_install = backup.install_close_guard
GUARDS = []


def _spy_install(window, callbacks):
    GUARDS.append((window, callbacks))
    return _orig_install(window, callbacks)


backup.install_close_guard = _spy_install


def guard_of(win):
    for w, cbs in GUARDS:
        if w is win:
            return cbs
    return None


class _MB(QMessageBox):
    """替换 project.QMessageBox，避免 save/information 等静态弹窗阻塞。"""

    @staticmethod
    def warning(*a, **k):
        return None

    @staticmethod
    def information(*a, **k):
        return None

    @staticmethod
    def question(*a, **k):
        return QMessageBox.No

    @staticmethod
    def critical(*a, **k):
        return None


project.QMessageBox = _MB

BAK = backup.PROJECT_BACKUP
_ORIG_BAK = None
if os.path.exists(BAK):
    with open(BAK, 'rb') as _f:
        _ORIG_BAK = _f.read()


def clear_bak():
    """把备份置空，便于断言“本轮是否写过备份”。"""
    with open(BAK, 'w', encoding='utf-8'):
        pass


def bak_size():
    return os.path.getsize(BAK) if os.path.exists(BAK) else -1


clear_bak()

wins = []
conns = []
srvs = []


def rec(o_call, date='2026-09-12', time_='20:00'):
    return {'date': date, 'time': time_, 'm_call': 'BG1AAA', 'o_call': o_call,
            'freq': '145.000', 'freq_rx': '', 'mode': 'FM', 'prop_mode': '',
            'sat_name': '', 'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '',
            'm_dig': '', 'o_dig': '', 'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '',
            'notes': ''}


def new_server(seed):
    srv = remote_server.LogServer(password='', port=0, fhl_path=None)
    srv.start(seed_list=seed)
    srvs.append(srv)
    return srv


def join(srv, role='host'):
    conn = project.RemoteConnection('127.0.0.1', srv.address[1], '', role=role)
    conn.connect()
    conns.append(conn)
    return conn


def open_project(conn, srv):
    win = QMainWindow()
    project.main(win, filee=conn.initial_file, key_=None, remote=conn,
                 is_host=True, server=srv)
    win.show()
    wins.append(win)
    return win


def dispose(win):
    """彻底销毁窗口（连带其备份定时器）。

    注意：`file` 与备份文件是模块级/全局共享的，若把旧窗口留着，它的 1.5s 定时器
    会跟着**别的窗口**造成的内容变化去写备份，干扰后续断言。真实使用中不会同时留
    这么多窗口，这里是测试侧的必要清理。
    deleteLater() 只是投递延迟删除事件，必须显式派发 DeferredDelete 才会真正销毁
    （否则定时器仍在跑）。
    """
    try:
        win.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
    except Exception:
        pass
    app.processEvents()


try:
    # -------------------------------------------------------------------
    # T1: 会话中「他人改动」同步进来 → 不得被当成“本机未保存更改”
    # -------------------------------------------------------------------
    srv1 = new_server([rec('A1AAA')])
    connA = join(srv1)
    winA = open_project(connA, srv1)
    cbsA = guard_of(winA)
    ok('T1a 已安装关闭守卫', cbsA is not None)
    pump(1.5)
    ok('T1b 打开窗口后内容为 1 条', len(project.file) == 1, f'len={len(project.file)}')

    connB = project.RemoteConnection('127.0.0.1', srv1.address[1], '')
    conns.append(connB)
    connB.connect()
    connB.send_save([rec('A1AAA'), rec('B2BBB')])   # 模拟另一个客户端加了 1 条
    pump(3.0)
    ok('T1c 他人改动已同步到本窗口', len(project.file) == 2, f'len={len(project.file)}')
    ok('T1d 同步后仍判为「已保存」（旧实现恒为脏）', cbsA['is_dirty']() is False)

    pump(2.0)   # 让 1.5s 备份定时器跳几拍
    ok('T1e 会话中不写本机“未保存”备份（旧实现会写）', bak_size() == 0,
       f'size={bak_size()}')

    PROMPTS.clear()
    winA.close()
    app.processEvents()
    ok('T1f 会话中关闭窗口不提示未保存的更改', len(PROMPTS) == 0, f'prompts={PROMPTS}')
    ok('T1g 关闭后已退出会话（连接释放）', winA._remote is None)

    # -------------------------------------------------------------------
    # T2: 会话结束且内容相对本机文件确有变化 → 仍要判为未保存（安全网）
    # -------------------------------------------------------------------
    ok('T2a 退出会话后内容有变化 → 判为未保存', cbsA['is_dirty']() is True)
    clear_bak()
    pump(2.2)
    ok('T2b 退出后会重新写本机备份（内容不会白丢）', bak_size() > 0, f'size={bak_size()}')
    PROMPTS.clear()
    winA.show()
    app.processEvents()
    winA.close()
    app.processEvents()
    ok('T2c 退出后关闭窗口 → 提示保存', len(PROMPTS) >= 1, f'prompts={PROMPTS}')
    dispose(winA)   # 后续断言只关心当前窗口的定时器行为

    # -------------------------------------------------------------------
    # T3: 会话中没有任何变化 → 退出后也不该啰嗦
    # -------------------------------------------------------------------
    clear_bak()
    srv3 = new_server([rec('C3CCC')])
    connC = join(srv3)
    winB = open_project(connC, srv3)
    cbsB = guard_of(winB)
    pump(2.0)
    ok('T3a 会话中无变化同样不写备份', bak_size() == 0, f'size={bak_size()}')
    ok('T3b 会话中无变化 → 判为已保存', cbsB['is_dirty']() is False)
    PROMPTS.clear()
    winB.close()
    app.processEvents()
    ok('T3c 会话中无变化 → 关闭不提示', len(PROMPTS) == 0, f'prompts={PROMPTS}')
    ok('T3d 退出后内容无变化 → 仍为已保存（不打扰）', cbsB['is_dirty']() is False)
    clear_bak()
    pump(2.2)
    ok('T3e 退出后无变化 → 不写备份', bak_size() == 0, f'size={bak_size()}')
    dispose(winB)

    # -------------------------------------------------------------------
    # T4: 会话中确有“未推送”内容 → 判为未保存，且文案改为「同步到服务端」
    # -------------------------------------------------------------------
    clear_bak()
    srv4 = new_server([rec('D4DDD')])
    connD = join(srv4)
    winC = open_project(connD, srv4)
    cbsC = guard_of(winC)
    pump(1.5)
    before = cbsC['is_dirty']()
    project.file.append(rec('E5EEE'))       # 直接改内存：等价于“本地有内容尚未推送”
    ok('T4a 未改动前为已保存', before is False)
    ok('T4b 有未推送内容 → 判为未保存', cbsC['is_dirty']() is True)
    ok('T4c 多人日志文案为「未同步到服务端」',
       (cbsC['texts']() or {}).get('title') == '未同步到服务端',
       f"texts={cbsC['texts']()}")
    clear_bak()
    PROMPTS.clear()
    winC.close()
    app.processEvents()
    ok('T4d 会话中确有未推送内容 → 关闭时提示', len(PROMPTS) >= 1, f'prompts={PROMPTS}')
    ok('T4e 提示标题为「未同步到服务端」',
       any('未同步到服务端' in t for t in PROMPTS), f'prompts={PROMPTS}')
    ok('T4f 未点「同步」→ 本次不写备份', bak_size() == 0, f'size={bak_size()}')

    # -------------------------------------------------------------------
    # T5: 单人模式仍是「保存」措辞（未回归）
    # -------------------------------------------------------------------
    win6 = QMainWindow()
    backup.install_close_guard(win6, {
        'is_dirty': lambda: True,
        'write_backup': lambda: None,
        'clear_backup': lambda: None,
        'do_save': lambda: False,
        'texts': lambda: {},
    })
    PROMPTS.clear()
    win6.show()
    app.processEvents()
    win6.close()
    app.processEvents()
    ok('T5 单人模式用默认「未保存的更改」文案',
       any('未保存的更改' in t for t in PROMPTS), f'prompts={PROMPTS}')
    win6.deleteLater()
    app.processEvents()
except Exception:
    import traceback
    say(traceback.format_exc())
    PASS.append(False)
finally:
    for c in conns:
        try:
            c.shutdown()
        except Exception:
            pass
    for s in srvs:
        try:
            s.stop()
        except Exception:
            pass
    for w in wins:
        try:
            w.deleteLater()
        except Exception:
            pass
    app.processEvents()
    try:
        if _ORIG_BAK is None:
            if os.path.exists(BAK):
                os.remove(BAK)
        else:
            with open(BAK, 'wb') as f:
                f.write(_ORIG_BAK)
    except Exception:
        pass

say('\n=== ALL PASS ===' if all(PASS) else '\n=== SOME FAILED ===')
sys.exit(0 if all(PASS) else 1)
