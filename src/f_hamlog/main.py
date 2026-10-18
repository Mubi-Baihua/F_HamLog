from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer
import sys
import os
import time
import re
import json
from f_hamlog import fhl_rw
from f_hamlog import backup
from f_hamlog import bg_thread
from f_hamlog import theme
from f_hamlog import i18n
from f_hamlog.dialog_defaults import desktop_dir
from f_hamlog.paths import app_path

# 各窗口的强引用必须声明在模块级：
# ① 避免「首次点击 → 名字尚未定义」的 NameError（如新建项目先于通联日志时）；
# ② 便于判断「旧窗口是否正在多人日志会话中」（见 _confirm_replace_session）。
window = None
project_window = None
batch_window = None
set_window = None


def _cleanup_remote_rooms(days=1):
    """启动时清理 file/remote_rooms 中超过 days 天的多人日志房间文件。

    文件名形如「多人日志_YYYYMMDD_HHMMSS.fhl」，优先用文件名里的开放时间戳判定
    新旧；解析失败则回退到文件修改时间。目录不存在时直接返回。"""
    rooms_dir = app_path('file/remote_rooms')
    if not os.path.isdir(rooms_dir):
        return
    cutoff = time.time() - days * 86400.0
    ts_re = re.compile(r'(\d{8})_(\d{6})')
    for fn in os.listdir(rooms_dir):
        if not fn.lower().endswith('.fhl'):
            continue
        full = os.path.join(rooms_dir, fn)
        ts = None
        m = ts_re.search(fn)
        if m:
            try:
                ts = time.mktime(time.strptime(m.group(1) + m.group(2),
                                               '%Y%m%d%H%M%S'))
            except ValueError:
                ts = None
        if ts is None:
            try:
                ts = os.path.getmtime(full)
            except OSError:
                continue
        if ts < cutoff:
            try:
                os.remove(full)
            except OSError:
                pass


def default_quick_project_path():
    """「通联日志」默认打开哪个文件：**优先 `file/main.fhla`，否则老的 `file/main.fhl`**。

    两者都不存在（全新安装）时返回 `.fhla` 路径 —— 默认格式已是带属性的 F HamLog 项目。
    迁移会把 `main.fhl` 删掉，所以下次启动必须能找到新的 `main.fhla`，
    否则「通联日志」会打开一份空项目、每次都重新提示迁移。
    """
    fhla = app_path('file/main.fhla')
    fhl = app_path('file/main.fhl')
    if os.path.exists(fhla):
        return fhla
    if os.path.exists(fhl):
        return fhl
    return fhla


def load_quick_project_data(path):
    """读「通联日志」（`file/main.fhla` 或 `main.fhl`）→ ``(records, key, meta)``。

    文件不存在（首次使用 / 数据目录刚建好）时返回 ``([], None, None)``：**按空项目打开**，
    首次保存时再创建。旧写法直接 ``read_fhl_file(path)``，缺文件就抛
    FileNotFoundError，整个「通联日志」都点不开（2026-10-16 实测崩溃）。
    按扩展名分派：`.fhla` 连属性块一起返回（meta），`.fhl` 的 meta 恒为 None。
    返回 ``(None, None, None)`` 表示用户取消了密钥输入 / 解密失败，调用方应中断打开。
    """
    if not os.path.exists(path):
        return [], None, None
    from f_hamlog import project
    data, key, meta = project.read_project_file(path)
    if data is None:
        return None, None, None
    return data, key, meta


def main():
    # 装配运行日志（幂等：__main__ 已经装过就直接返回）。
    # stdout/stderr、未捕获异常、线程异常、Qt 消息、C 层崩溃栈都落到 file/log/，保留三天。
    try:
        from f_hamlog import app_log
        app_log.setup()
    except Exception:
        pass

    # 启动时清理过期（默认 3 天）的多人日志房间文件
    _cleanup_remote_rooms(days=1)

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
        from f_hamlog import project
        if not _confirm_replace_session():
            return
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        # 优先 .fhla（迁移后的正式格式），没有才退回老的 main.fhl
        save_path = default_quick_project_path()
        print(save_path)
        data, key, fhla_meta = load_quick_project_data(save_path)
        if data == None:
            return
        # 默认日志同样属于「打开 .fhl」→ 也一样提示迁移（用户要求每次打开都提示）。
        # 迁移成功会删掉 main.fhl，下次 default_quick_project_path() 自然找到 main.fhla。
        save_path, fhla_meta = project.offer_migration(window, save_path, data,
                                                       key=key, meta=fhla_meta)
        project.main(project_window, data, save_path, key_=key,
                     quick_poject=True, fhla_meta=fhla_meta)
    def new_project():
        print("新建项目")
        from f_hamlog import project
        if not _confirm_replace_session():
            return
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        project.main(project_window)

    def open_project():
        print("打开项目")
        from f_hamlog import project
        save_path, _ = QFileDialog.getOpenFileName(
            window,  # 父窗口
            i18n.tr("打开项目"),  # 对话框标题
            desktop_dir(),  # 初始目录：桌面
            i18n.tr(project.OPEN_FILTER_BOTH)  # 合并过滤器：.fhla 与 .fhl 一次看全
        )
        if save_path == '':
            return
        if not _confirm_replace_session():
            return
        print(save_path)
        # 按扩展名分派：.fhla 连属性块（创建者/编辑者/时间/版本/加密状态）一起读出，
        # .fhl 行为与旧版完全一致（meta 为 None）。实现见 project.py「.fhla 文件格式」。
        data, key, fhla_meta = project.read_project_file(save_path)
        if data == None:
            return
        # 打开的是 .fhl（兼容项目）→ 每次都问一句要不要迁移成 .fhla；
        # 迁移成功就用新路径 + 新属性块打开，窗口此后的保存直接落到 .fhla。
        save_path, fhla_meta = project.offer_migration(window, save_path, data,
                                                       key=key, meta=fhla_meta)
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        project.main(project_window, data, save_path, key_=key, fhla_meta=fhla_meta)

    def join_server():
        print("加入多人日志")
        from f_hamlog import project
        from f_hamlog.project import RemoteConnection
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
        # 建立连接前先构造指纹核对回调：首次连接/指纹变化时会弹窗请用户核对。
        # 传 None 则不做核对（不推荐），这里始终启用。
        verify = project.make_fingerprint_verifier(window, host, port)
        conn = RemoteConnection(host, port, password, role='guest',
                                verify_fingerprint=verify)
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
        from f_hamlog import set
        global set_window  # 保持引用，防止被回收
        set_window = QMainWindow()
        set.main(set_window)

    def batch_project():
        print("批量记录")
        from f_hamlog import batch_project
        global batch_window  # 保持引用，防止被回收
        batch_window = QMainWindow()
        batch_project.main(batch_window)

    def satellite_pred_open():
            print("卫星过境预测")
            from f_hamlog import satellite_window
            from f_hamlog import batch_project
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
    app.setWindowIcon(QIcon(app_path("file/F_HamLog.ico")))
    # 颜色模式：跟随系统／浅色／深色（保存在设置文件，见 theme.py）
    theme.init_app(app)
    # 界面语言：中文／英文（词表见 i18n_zh_en.py；窗口文字在显示时自动翻译）
    i18n.install(app)

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
            # 高度已由调用处的 setFixedSize 定死（主按钮 46、其余 40）。
            # 这里**不要**再 setMinimumHeight(BTN_H)：那会把固定高 46 改成
            # 「最小 40 / 最大 46」的可伸缩区间，布局在 show() 的两遍排布里
            # 可能一遍取 40、一遍取 46，主按钮位置就跟着上下跳 6px。
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

    # 副标题用次要文字色（跟随主题；写死颜色在深色模式下会看不清）
    def _refresh_theme():
        sub.setStyleSheet(theme.hint_css())

    _refresh_theme()
    theme.watch_theme(window, _refresh_theme)
    main_layout.addWidget(title)
    main_layout.addWidget(sub)
    # 副标题与主按钮之间的留白：**可压缩**（首选 50px、最小 0）。
    #
    # 原来是 addSpacing(50)——固定 50px、不可压缩。而这一列内容的自然高度约
    # 390px，窗口只有 375px，多出来的十几像素没地方去，布局只能从下面那个两列
    # 网格里挤（行距从设计值 6px 被压成 3~4px，还不均匀），而且这次挤压发生在
    # show() 之后（QSS 抛光会让布局再算一遍），于是第一帧和最终帧不一样，
    # 打开主界面时内容会「上下跳一下」。
    # 换成可压缩留白后，溢出的高度由它自己吸收：位置一次算到底，网格保持 6px
    # 行距；窗口更高/英文界面下它仍然会长回 50px。
    main_layout.addItem(QSpacerItem(20, 50, QSizePolicy.Minimum,
                                    QSizePolicy.Expanding))

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

    button_join_grid = QPushButton('加入多人日志')
    button_join_grid.setFixedSize(105, BTN_H)
    button_join_grid.clicked.connect(join_server)
    _style_btn(button_join_grid)

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
    grid.addWidget(button_join_grid, 0, 1)
    grid.addWidget(button_sat, 1, 0, 1, 2)
    grid.addWidget(button_start, 2, 0)
    grid.addWidget(button_open, 2, 1)
    main_layout.addWidget(grid_box, alignment=Qt.AlignHCenter)

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

    # 末尾不再 addStretch(1)：竖向余量全部交给上面那段可压缩留白吸收。
    # 两个都可伸缩时，多余空间按 stretch 因子分给末尾这条，留白仍是 50px，
    # 内容照样超高——等于没改。

    window.show()

    # 窗口尺寸跟随语言：中文下严格 575×375、按钮 105/220px（与历史版本逐像素一致）；
    # 英文按钮文字更长（'Join online log' 等），按文字自然宽度放大按钮与窗口，
    # 否则固定宽度会把英文截断。
    _grid_btns = (button_batch, button_join_grid, button_start, button_open)
    _full_btns = (button_quick, button_sat)

    def _fit_launcher():
        if not i18n.is_english():
            grid_box.setFixedWidth(220)
            for b in _grid_btns:
                b.setFixedSize(105, BTN_H)
            button_quick.setFixedSize(220, 46)
            button_sat.setFixedSize(220, BTN_H)
            window.setFixedSize(575, 375)
            return
        half = max([105] + [b.sizeHint().width() for b in _grid_btns])
        full = max([220, 2 * half + 6] + [b.sizeHint().width() for b in _full_btns])
        for b in _grid_btns:
            b.setFixedSize(half, BTN_H)
        button_quick.setFixedSize(full, 46)
        button_sat.setFixedSize(full, BTN_H)
        grid_box.setFixedWidth(full)
        window.setFixedSize(max(575, full + 48), 375)   # 48 = 主布局左右边距 24+24

    _fit_launcher()
    i18n.watch_language(window, _fit_launcher)

    # 启动卫星星历（TLE）自动定时更新：按“设置”中的开关与间隔，在后台周期性刷新缓存
    from f_hamlog import satellite_auto_update
    satellite_auto_updater = satellite_auto_update.AutoTleUpdater(window)
    satellite_auto_updater.start()
    # 退出前必须停掉后台线程，否则 App 结束时 QThread 仍在运行会被析构 → Qt 走 qFatal
    # （Windows 上表现为 0xc0000409 / 事件日志「应用程序错误 1000」出错模块 Qt6Core.dll，
    #   用户看到的就是「程序突然消失」，且没有任何 Python traceback）。
    # ① 星历线程有自己的停止顺序（先置位再等），先单独停；
    # ② 再用 bg_thread.stop_all() 兜底扫一遍所有登记过的后台线程
    #    —— 覆盖「关掉主窗口退出」「quit()」「最后一个窗口关闭」这些不经过
    #    各窗口 closeEvent 的路径。见 bg_thread 模块说明。
    app.aboutToQuit.connect(satellite_auto_updater.stop)
    app.aboutToQuit.connect(lambda: bg_thread.stop_all())

    # ---------- 启动时静默升级旧版数据（卫星名 → 卫星编号） ----------
    # 自选卫星、卫星转发器表、TQSL 映射表在旧版本里都以「卫星名」为键，而卫星名会
    # 随星历数据源变动（例如 ASRTU-1 换源后由 AO-123 变成 RS64S/BJ2CR）。这里在
    # 启动时按当前星历把它们就地升级为 NORAD 编号：能解析出编号的改写，解析不出的
    # 原样跳过；全程不弹窗、不提示、不打断用户。
    def _migrate_legacy_sat_data():
        try:
            from f_hamlog import satellite_pred
            satellite_pred.migrate_legacy_sat_data()
        except Exception:
            pass

    QTimer.singleShot(0, _migrate_legacy_sat_data)

    # ---------- 启动时检查并提示恢复未保存的内容 ----------
    def _check_recovery():
        from f_hamlog import project
        from f_hamlog import batch_project
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

    # 最后一道网：aboutToQuit 若因异常路径没触发（或退出过程中又起了线程），
    # 这里再扫一遍。stop_all 幂等，重复调用无副作用。
    bg_thread.stop_all()

if __name__ == '__main__':
    main()