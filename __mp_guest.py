# -*- coding: utf-8 -*-
"""真实「客户端」进程：等待房主端口 → 加入 → 新增一条记录 → 轮询自身日志状态。"""
import os, sys, json
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QTableWidget
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)
import project
from project import RemoteConnection

open('__guest_log.txt', 'w').close()


def w(tag, **kw):
    kw['tag'] = tag
    with open('__guest_log.txt', 'a', encoding='utf-8') as f:
        f.write(json.dumps(kw, ensure_ascii=False) + '\n')


state = {'win': None, 'conn': None, 'added': False, 'port': None}


def try_join():
    if state['win'] is not None:
        return
    try:
        with open('__host_port.txt', 'r', encoding='utf-8') as f:
            port = int(f.read().strip())
    except Exception:
        return
    state['port'] = port
    conn = RemoteConnection('127.0.0.1', port, '', role='guest')
    try:
        conn.connect()
    except Exception as e:
        w('join_fail', err=repr(e))
        return
    state['conn'] = conn
    win = QMainWindow()
    state['win'] = win
    project.main(win, filee=conn.initial_file, key_=None, remote=conn)
    w('joined', port=port, initial=len(conn.initial_file),
      o_calls=[r.get('o_call') for r in conn.initial_file])
    QTimer.singleShot(3000, guest_add)


def guest_add():
    win = state['win']
    conn = state['conn']
    n0 = len(project.file)
    win._new_qso()
    pwin = project.project_others_window
    tb = pwin.findChild(QTableWidget)
    tb.item(2, 1).setText('BG1')        # 己方呼号
    tb.item(3, 1).setText('GUESTNEW')   # 对方呼号
    tb.item(4, 1).setText('144')        # 频率
    tb.item(8, 1).setText('FM')         # 调制模式
    for b in pwin.findChildren(QPushButton):
        if b.text() == '新建日志':
            b.click()
            break
    state['added'] = True
    w('guest_added', before=n0, after=len(project.file),
      remote=win._remote is not None, o_calls=[r.get('o_call') for r in project.file])


tm = QTimer()
tm.setInterval(400)
tm.timeout.connect(try_join)
tm.start()

ticks = {'n': 0}


def poll():
    if state['win'] is None:
        return
    ticks['n'] += 1
    win = state['win']
    rows = 0
    for t in win.findChildren(QTableWidget):
        rows = max(rows, t.rowCount())
    w('tick', t=ticks['n'], file_len=len(project.file), rows=rows,
      remote=win._remote is not None, added=state['added'],
      sync_alive=bool(getattr(state['conn'], '_sync', None) and state['conn']._sync.isRunning()),
      o_calls=[r.get('o_call') for r in project.file])
    if ticks['n'] >= 25:
        app.quit()


pt = QTimer()
pt.setInterval(500)
pt.timeout.connect(poll)
pt.start()
QTimer.singleShot(14000, app.quit)
app.exec()
w('exit', file_len=len(project.file))
