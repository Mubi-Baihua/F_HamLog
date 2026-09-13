from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer
import sys
import json
import webbrowser
import urllib.parse
import fhl_rw
import backup
from dialog_defaults import desktop_dir

# 各窗口的强引用必须声明在模块级：
# ① 避免「首次点击 → 名字尚未定义」的 NameError（如新建项目先于通联日志时）；
# ② 便于判断「旧窗口是否正在多人日志会话中」（见 _confirm_replace_session）。
window = None
project_window = None
batch_window = None
set_window = None

def main():
    def _confirm_replace_session():
        """打开新的项目窗口前先确认。

        main() 只保存一个项目窗口引用（project_window），创建新窗口会让旧窗口失去
        引用而被回收；若旧窗口正作为多人日志的服务端/客户端，会话（含内嵌服务端）
        就会被静默结束——其他端看不到任何日志更新，表现为「日志无法同步」。
        """
        global project_window
        win = project_window
        if win is None:
            return True
        try:
            conn = getattr(win, '_remote', None)
            in_session = conn is not None
        except Exception:
            return True
        if not in_session:
            return True
        role = '服务端' if getattr(win, '_is_host', False) else '客户端'
        addr = f'{getattr(conn, "host", "?")}:{getattr(conn, "port", "?")}'
        return QMessageBox.question(
            window, '结束多人日志',
            f'当前项目窗口正作为多人日志{role}（{addr}）。\n'
            '打开新窗口会结束这个会话，其他用户将无法再与之同步日志。\n\n是否继续？'
        ) == QMessageBox.Yes

    def quick_project():
        print("通联日志")
        import project
        if not _confirm_replace_session():
            return
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        save_path = 'file/main.fhl'
        print(save_path)
        data,key = fhl_rw.read_fhl_file(save_path)
        if data == None:
            return
        project.main(project_window, data, save_path,key_=key,quick_poject=True)
    def new_project():
        print("新建项目")
        import project
        if not _confirm_replace_session():
            return
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        project.main(project_window)

    def open_project():
        print("打开项目")
        import project
        save_path, _ = QFileDialog.getOpenFileName(
            window,  # 父窗口
            "打开项目",  # 对话框标题
            desktop_dir(),  # 初始目录：桌面
            "F HamLog项目 (*.fhl)"  # 文件过滤器
        )
        if save_path == '':
            return
        if not _confirm_replace_session():
            return
        print(save_path)
        data,key = fhl_rw.read_fhl_file(save_path)
        if data == None:
            return
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        project.main(project_window, data, save_path,key_=key)

    def join_server():
        print("加入多人日志")
        import project
        from project import RemoteConnection
        dlg = QDialog(window)
        dlg.setWindowTitle('加入多人日志')
        # 保持高度不变，仅加宽以容纳「显示/隐藏」完整按钮文字
        dlg.setFixedSize(360, 148)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)

        # 紧凑小标签：固定窄宽度 + 小字号，避免撑大窗口
        def _mk_label(text):
            lb = QLabel(text)
            lb.setFixedWidth(34)
            fnt = lb.font(); fnt.setPointSize(9); lb.setFont(fnt)
            return lb

        host_e = QLineEdit(); host_e.setPlaceholderText('服务端地址（IP 或域名）')
        port_e = QLineEdit('8000')
        pw_e = QLineEdit(); pw_e.setEchoMode(QLineEdit.Password); pw_e.setPlaceholderText('密码（可留空）')
        btn_tgl = QPushButton('显示/隐藏')
        fnt = btn_tgl.font(); fnt.setPointSize(9); btn_tgl.setFont(fnt)
        def _tgl():
            if pw_e.echoMode() == QLineEdit.Password:
                pw_e.setEchoMode(QLineEdit.Normal)
            else:
                pw_e.setEchoMode(QLineEdit.Password)
        btn_tgl.clicked.connect(_tgl)
        h1 = QHBoxLayout(); h1.addWidget(_mk_label('服务端')); h1.addWidget(host_e, 1)
        h2 = QHBoxLayout(); h2.addWidget(_mk_label('端口')); h2.addWidget(port_e, 1)
        h3 = QHBoxLayout(); h3.addWidget(_mk_label('密码')); h3.addWidget(pw_e, 1); h3.addWidget(btn_tgl)
        lay.addLayout(h1); lay.addLayout(h2); lay.addLayout(h3)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return
        host = host_e.text().strip()
        if not host:
            QMessageBox.warning(window, '加入失败', '请输入服务端地址。')
            return
        try:
            port = int(port_e.text().strip() or '8000')
        except ValueError:
            port = 8000
        password = pw_e.text()
        conn = RemoteConnection(host, port, password, role='guest')
        try:
            conn.connect()
        except Exception as e:
            QMessageBox.warning(window, '加入失败', f'无法连接服务端：{e}')
            return
        # 旧的 project_window 若正在会话中，直接替换会把它连同会话一起回收 → 先确认
        if not _confirm_replace_session():
            try:
                conn.shutdown()
            except Exception:
                pass
            return
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        # 直接进入项目窗口（不再弹「已加入」提示）；
        # 加入后可在「多人日志 → 多人日志管理」查看在线设备。
        project.main(project_window, filee=conn.initial_file, key_=None, remote=conn)

    def set():
        print("设置")
        import set
        global set_window  # 保持引用，防止被回收
        set_window = QMainWindow()
        set.main(set_window)

    def qrz_page():
        print('qrz主页')
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())
        callsign = xml_dict['m_call']
        if callsign == '':
            url = 'https://www.qrz.com'
        else:
            url = f"https://www.qrz.com/db/{urllib.parse.quote_plus(callsign)}"
        webbrowser.open(url)
    
    def batch_project():
        print("批量记录")
        import batch_project
        global batch_window  # 保持引用，防止被回收
        batch_window = QMainWindow()
        batch_project.main(batch_window)

    def satellite_pred_open():
            print("卫星过境预测")
            import satellite_window
            import batch_project
            _batch_windows = []
            def quick_log(preset):
                # 主页：使用原有批量记录方式，保存时弹出“保存方式选择”对话框
                bw = QMainWindow()
                bw.setWindowTitle('批量记录')
                batch_project.main(bw, preset=preset)
                _batch_windows.append(bw)
            satellite_window.main(None, quick_log_callback=quick_log,
                                  title='卫星过境')
    
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("file/F_HamLog.ico"))

    global window
    window = QMainWindow()
    window.resize(575, 375)
    window.setFixedSize(575, 375)
    window.setWindowTitle('F HamLog 2')

    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(24, 18, 24, 16)
    main_layout.setSpacing(6)

    ACCENT = '#2f6fed'
    BTN_H = 40

    def _style_btn(btn, primary=False):
        if primary:
            btn.setMinimumHeight(BTN_H)
            #btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{background:%s;color:#ffffff;border:none;"
                "border-radius:6px;font-size:13px;font-weight:bold;}"
                "QPushButton:hover{background:#2a63d4;}"
                "QPushButton:pressed{background:#2356ba;}" % ACCENT)

    # ---------- 标题区 ----------
    title = QLabel('F HamLog 2')
    title.setAlignment(Qt.AlignCenter)
    f = title.font(); f.setPointSize(18); f.setBold(True)
    title.setFont(f)
    sub = QLabel('业余无线电通联日志')
    sub.setAlignment(Qt.AlignCenter)
    f = sub.font(); f.setPointSize(10)
    sub.setFont(f)
    sub.setStyleSheet('color:#7a8190;')
    main_layout.addWidget(title)
    main_layout.addWidget(sub)
    main_layout.addSpacing(50)

    main_layout

    # ---------- 主操作 ----------
    button_quick = QPushButton('通联日志')
    button_quick.setFixedSize(220, 46)
    button_quick.clicked.connect(quick_project)
    _style_btn(button_quick, primary=True)
    button_quick.setDefault(True)
    main_layout.addWidget(button_quick, alignment=Qt.AlignHCenter)

    # ---------- 次要操作（两列网格） ----------
    grid_box = QWidget()
    grid_box.setFixedWidth(220)
    grid = QGridLayout(grid_box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(6)

    button_batch = QPushButton('批量记录')
    button_batch.setFixedSize(105, BTN_H)
    button_batch.clicked.connect(batch_project)
    _style_btn(button_batch)

    button_qrz = QPushButton('QRZ主页')
    button_qrz.setFixedSize(105, BTN_H)
    button_qrz.clicked.connect(qrz_page)
    _style_btn(button_qrz)

    button_sat = QPushButton('卫星过境')
    button_sat.setFixedSize(220, BTN_H)
    button_sat.clicked.connect(satellite_pred_open)
    _style_btn(button_sat)

    button_start = QPushButton('新建项目')
    button_start.setFixedSize(105, BTN_H)
    button_start.clicked.connect(new_project)
    _style_btn(button_start)

    button_open = QPushButton('打开项目')
    button_open.setFixedSize(105, BTN_H)
    button_open.clicked.connect(open_project)
    _style_btn(button_open)

    grid.addWidget(button_batch, 0, 0)
    grid.addWidget(button_qrz, 0, 1)
    grid.addWidget(button_sat, 1, 0, 1, 2)
    grid.addWidget(button_start, 2, 0)
    grid.addWidget(button_open, 2, 1)
    main_layout.addWidget(grid_box, alignment=Qt.AlignHCenter)

    # ---------- 加入多人日志（加入入口统一收归主页） ----------
    button_join = QPushButton('加入多人日志')
    button_join.setFixedSize(220, BTN_H)
    button_join.clicked.connect(join_server)
    _style_btn(button_join)
    main_layout.addWidget(button_join, alignment=Qt.AlignHCenter)

    # ---------- 分隔线 ----------
    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)
    main_layout.addWidget(line)

    # ---------- 设置 ----------
    button_set = QPushButton('设置')
    button_set.setFixedSize(105, BTN_H)
    button_set.clicked.connect(set)
    _style_btn(button_set)
    main_layout.addWidget(button_set, alignment=Qt.AlignHCenter)

    main_layout.addStretch(1)

    window.show()

    # 启动卫星星历（TLE）自动定时更新：按“设置”中的开关与间隔，在后台周期性刷新缓存
    import satellite_auto_update
    satellite_auto_updater = satellite_auto_update.AutoTleUpdater(window)
    satellite_auto_updater.start()

    # ---------- 启动时检查并提示恢复未保存的内容 ----------
    def _check_recovery():
        import project
        import batch_project
        items = []
        if backup.is_backup_nonempty(backup.PROJECT_BACKUP):
            items.append(('project', backup.PROJECT_BACKUP))
        if backup.is_backup_nonempty(backup.BATCH_BACKUP):
            items.append(('batch', backup.BATCH_BACKUP))
        if not items:
            return
        names = {'project': '项目', 'batch': '批量记录'}
        detail = '\n'.join('- ' + names[t] for t, _ in items)
        box = QMessageBox(window)
        box.setWindowTitle('恢复未保存的内容')
        box.setText('检测到上次有未保存的更改，是否恢复？')
        box.setInformativeText(detail)
        btn_rec = box.addButton('恢复', QMessageBox.AcceptRole)
        btn_ign = box.addButton('忽略', QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == btn_rec:
            for t, path in items:
                if t == 'project':
                    data, key = fhl_rw.read_fhl_file(path)
                    if data is None:
                        continue
                    global project_window
                    project_window = QMainWindow()
                    project.main(project_window, data, '', key_=key, recovered=True)
                else:
                    data, _ = fhl_rw.read_fhl_file(path)
                    if data is None:
                        continue
                    global batch_window
                    batch_window = QMainWindow()
                    batch_project.main(batch_window, preset_records=data, recovered=True)
            # 恢复后由对应窗口接管备份：保持脏标记，可再次提示恢复，故不清空
        else:
            # 忽略：丢弃所有未保存备份，避免下次启动重复提示
            for _, path in items:
                backup.clear_backup(path)

    QTimer.singleShot(0, _check_recovery)

    app.exec()

if __name__ == '__main__':
    main()