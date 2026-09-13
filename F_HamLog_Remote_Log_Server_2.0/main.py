# -*- coding: utf-8 -*-
"""F HamLog 多人日志服务端 2.0（独立版）。

术语统一：本功能统一称为「多人日志」；两个角色统一称为「服务端」与「客户端」。
与客户端内嵌服务端共用同一份 remote_server.LogServer 引擎，做到“只写一次”。
可作为独立 exe 运行，托管一个多人日志服务端，供各客户端通过 IP:端口 + 密码加入。

功能：
- 设置端口与密码后「启动」即可监听，日志落盘到同目录 main.fhl；
- 实时显示监听地址、在线用户数与事件日志；
- 启动后禁用密码输入，避免运行中改动；「停止」或关闭窗口即结束服务（在线客户端会被断开）。
"""

import os
import sys
import json
import socket
from PySide6.QtWidgets import *
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QIcon
import remote_server


def _app_dir():
    return os.path.dirname(os.path.abspath(__file__))


class _Events(QObject):
    """服务端线程 -> GUI 线程的中转信号，保证界面操作线程安全。"""
    status = Signal(str)
    addr = Signal(str)
    clients = Signal(int)
    log = Signal(str)
    control = Signal(bool)   # True=运行中（禁用启动/启用停止），False=已停止


class ServerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('F HamLog 多人日志服务端 2.0')
        self.resize(480, 400)
        ico = os.path.join(_app_dir(), 'F_HamLog.ico')
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))

        self.server = None
        self._ev = _Events()
        self._ev.status.connect(self._on_status)
        self._ev.addr.connect(self._on_addr)
        self._ev.clients.connect(self._on_clients)
        self._ev.log.connect(self._on_log)
        self._ev.control.connect(self._on_control)

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        # 端口 / 密码（密码输入方式与客户端一致：密文显示 + 显示/隐藏切换）
        h1 = QHBoxLayout()
        h1.addWidget(QLabel('端口：'))
        self.port_edit = QLineEdit('8000')
        h1.addWidget(self.port_edit)
        h1.addWidget(QLabel('密码：'))
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText('密码（可留空）')
        h1.addWidget(self.pass_edit)
        self.tgl_btn = QPushButton('显示/隐藏')
        self.tgl_btn.clicked.connect(self._toggle_password)
        h1.addWidget(self.tgl_btn)
        lay.addLayout(h1)

        # 状态信息
        self.status_label = QLabel('状态：未启动')
        self.status_label.setStyleSheet('color: gray;')
        lay.addWidget(self.status_label)

        self.addr_label = QLabel('监听地址：—')
        lay.addWidget(self.addr_label)

        self.clients_label = QLabel('在线用户：0')
        lay.addWidget(self.clients_label)

        # 启动 / 停止
        h2 = QHBoxLayout()
        self.start_btn = QPushButton('启动')
        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn = QPushButton('停止')
        self.stop_btn.clicked.connect(self.stop_server)
        self.stop_btn.setEnabled(False)
        h2.addWidget(self.start_btn)
        h2.addWidget(self.stop_btn)
        lay.addLayout(h2)

        # 事件日志
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        lay.addWidget(self.log_box)

        # 预填已保存的密码（若存在），否则用默认值——密码会随「启动」/关闭自动保存
        self.pass_edit.setText(self._load_password())

        # 显示本机局域网地址，方便分享
        self._ev.log.emit(f'本机局域网地址参考：{remote_server.get_lan_ip()}')

    # ---- 密码持久化 ----
    def _password_path(self):
        return os.path.join(_app_dir(), 'password_xml.txt')

    def _load_password(self):
        pw_file = self._password_path()
        if os.path.exists(pw_file):
            try:
                with open(pw_file, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception:
                pass
        return '000000'

    def _save_password(self):
        try:
            with open(self._password_path(), 'w', encoding='utf-8') as f:
                f.write(self.pass_edit.text())
        except Exception:
            pass

    def _toggle_password(self):
        if self.pass_edit.echoMode() == QLineEdit.Password:
            self.pass_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.pass_edit.setEchoMode(QLineEdit.Password)

    # ---- GUI 线程槽 ----
    def _on_status(self, text):
        self.status_label.setText(text)

    def _on_addr(self, text):
        self.addr_label.setText(text)

    def _on_clients(self, n):
        self.clients_label.setText(f'在线用户：{n}')

    def _on_log(self, text):
        self.log_box.appendPlainText(text)

    def _on_control(self, running):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        # 服务开启后禁用密码输入（连同「显示/隐藏」一起禁用，避免运行中被改动/泄露）
        self.pass_edit.setEnabled(not running)
        self.tgl_btn.setEnabled(not running)

    # ---- 服务端线程回调（仅发射信号，不碰控件）----
    def _emit(self, name, **kw):
        if name == 'start':
            self._ev.status.emit('状态：运行中')
            self._ev.addr.emit(f"监听地址：{kw.get('ip', '')}:{kw.get('port', '')}")
            self._ev.log.emit(f"服务端启动：{kw.get('ip', '')}:{kw.get('port', '')}")
            self._ev.control.emit(True)
        elif name == 'stop':
            self._ev.status.emit('状态：已停止')
            self._ev.addr.emit('监听地址：—')
            self._ev.log.emit('服务端已停止')
            self._ev.control.emit(False)
        elif name == 'client':
            self._ev.clients.emit(kw.get('count', 0))
            self._ev.log.emit(f"在线用户数变化：{kw.get('count', 0)}")

    # ---- 控制 ----
    def start_server(self):
        if self.server is not None:
            return
        try:
            port = int(self.port_edit.text().strip() or '8000')
        except ValueError:
            port = 8000
        password = self.pass_edit.text()
        self._save_password()   # 保存密码，下次启动自动带入
        fhl_path = os.path.join(_app_dir(), 'main.fhl')
        self.server = remote_server.LogServer(
            password=password, port=port, fhl_path=fhl_path, on_event=self._emit)
        try:
            self.server.start()
        except Exception as e:
            QMessageBox.warning(self, '启动失败', f'无法启动服务端：{e}')
            self.server = None
            return

    def stop_server(self):
        if self.server is None:
            return
        self.server.stop()
        self.server = None

    def closeEvent(self, event):
        self._save_password()   # 关闭时再保存一次密码
        if self.server is not None:
            self.server.stop()
            self.server = None
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ico = os.path.join(_app_dir(), 'F_HamLog.ico')
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    win = ServerGUI()
    win.show()
    app.exec()
