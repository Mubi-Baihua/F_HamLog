# -*- coding: utf-8 -*-
"""真实「服务端（房主）」进程：开房 → 输出端口 → 轮询自身日志状态。"""
import os, sys, json
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QTableWidget
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)
import project


def rec(o):
    return {'date': '2026-01-01', 'time': '10:00', 'm_call': 'BG1', 'o_call': o,
            'freq': '145', 'freq_rx': '', 'mode': 'FM', 'prop_mode': '', 'sat_name': '',
            'm_rst': '59', 'o_rst': '59', 'm_qth': '', 'o_qth': '', 'm_dig': '', 'o_dig': '',
            'm_ant': '', 'o_ant': '', 'm_pow': '', 'o_pow': '', 'notes': ''}


def w(tag, **kw):
    kw['tag'] = tag
    with open('__host_log.txt', 'a', encoding='utf-8') as f:
        f.write(json.dumps(kw, ensure_ascii=False) + '\n')


open('__host_log.txt', 'w').close()

win = QMainWindow()
project.main(win, filee=[rec('BG2'), rec('BG3')], save_path='__host_test.fhl')
w('main_returned', file_len=len(project.file))

# 打开「多人日志管理」菜单项
act = None
for m in win.menuBar().actions():
    if m.text() == '多人日志':
        for a in m.menu().actions():
            if a.text() == '多人日志管理':
                act = a
w('menu_found', ok=act is not None)
act.trigger()
dlg = getattr(win, '_mp_dialog', None)
w('dialog', ok=dlg is not None)

btn = None
for b in dlg.findChildren(QPushButton):
    if b.text() == '开放多人日志':
        btn = b
w('open_btn', ok=btn is not None)
btn.click()
srv = getattr(win, '_server', None)
w('after_open', server=srv is not None, is_host=win._is_host,
  remote=win._remote is not None)

if srv is not None:
    with open('__host_port.txt', 'w', encoding='utf-8') as f:
        f.write(str(srv.address[1]))
    w('port_written', port=srv.address[1],
      fp=getattr(srv, 'fingerprint_short', ''), encrypt=getattr(srv, 'encrypt', None),
      key_path=getattr(srv, 'key_path', None))

# 8 秒后房主自己也新增一条记录
added = {'done': False}


def host_add():
    n0 = len(project.file)
    win._new_qso()
    pwin = project.project_others_window
    tb = pwin.findChild(QTableWidget)
    tb.item(2, 1).setText('BG1')      # 己方呼号
    tb.item(3, 1).setText('HOSTNEW')  # 对方呼号
    tb.item(4, 1).setText('439')      # 频率
    tb.item(8, 1).setText('FM')       # 调制模式
    for b in pwin.findChildren(QPushButton):
        if b.text() == '新建日志':
            b.click()
            break
    added['done'] = True
    w('host_added', before=n0, after=len(project.file), remote=win._remote is not None)


QTimer.singleShot(8000, host_add)

ticks = {'n': 0}


def poll():
    ticks['n'] += 1
    rows = 0
    for t in win.findChildren(QTableWidget):
        rows = max(rows, t.rowCount())
    w('tick', t=ticks['n'], file_len=len(project.file), rows=rows,
      remote=win._remote is not None, host_added=added['done'],
      calls=[r.get('o_call') for r in project.file])
    if ticks['n'] >= 30:
        app.quit()


tm = QTimer()
tm.setInterval(500)
tm.timeout.connect(poll)
tm.start()
QTimer.singleShot(16000, app.quit)
app.exec()
w('exit', file_len=len(project.file))
