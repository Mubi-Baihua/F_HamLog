from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QEvent, Signal
import threading
import webbrowser
from f_hamlog import call_upper
from f_hamlog import theme
from f_hamlog import i18n
from f_hamlog import bg_thread
from f_hamlog import __version__
from f_hamlog.dialog_defaults import desktop_dir
from f_hamlog.paths import app_path

# 「星历数据源」独立窗口的引用（防止被回收；非模态，可重复打开）
tle_source_win = None


# ---------------------------------------------------------------------------
# 检查更新：检查 → 多线程下载 → 运行安装包 → 退出本程序
# ---------------------------------------------------------------------------
# 线程必须是**模块级强引用**：QThread 的 C++ 对象一旦被回收而线程还在跑，Qt 会走
# qFatal → abort（见 bg_thread 模块说明）。同时继承 bg_thread.BgThread，退出前由
# stop_all() 兜底。
_update_check_thread = None
_update_download_thread = None
_update_dialog = None       # 下载进度窗（独立顶层窗口，靠这个引用保命）


def _no_maximize(win):
    """把这个窗口钉成「不可以最大化」。

    Qt 的对话框默认带可缩放边框（系统样式 WS_THICKFRAME），拖到屏幕上沿会被 Aero Snap
    拉成整屏；这些窗口都只有几行字，放大之后就是一片空，很难看。所以两件事一起做：
    去掉最大化按钮 + 去掉可缩放边框（固定尺寸对话框样式）。
    """
    win.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
    win.setWindowFlag(Qt.MSWindowsFixedSizeDialogHint, True)


def _revert_maximize(win, event):
    """谁把窗口最大化了就立刻还原（任务栏右键菜单 / ShowWindow 也能放大）。"""
    if event.type() == QEvent.WindowStateChange and win.isMaximized():
        win.showNormal()


class _NoMaximizeDialog(QDialog):
    """更新流程用的小对话框：不可以最大化，也不可以拖边改大小。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        _no_maximize(self)

    def changeEvent(self, event):
        super().changeEvent(event)
        _revert_maximize(self, event)


class _UpdateProgressDialog(QProgressDialog):
    """下载进度窗：不可以最大化，也不可以拖边改大小（理由见 :func:`_no_maximize`）。"""

    def __init__(self, parent=None):
        super().__init__(i18n.tr('正在下载更新…'), i18n.tr('取消'), 0, 100, parent)
        _no_maximize(self)

    def changeEvent(self, event):
        super().changeEvent(event)
        _revert_maximize(self, event)


class _CheckThread(bg_thread.BgThread):
    """后台查版本：check_update.check() 内部最多重试 5 次，绝不能放在 UI 线程里跑。"""

    result = Signal(object)

    def run(self):
        try:
            from f_hamlog import check_update
            info = check_update.check()
        except Exception as e:
            info = {'status': 'error', 'version': '', 'url': '', 'detail': str(e)}
        self.result.emit(info)


class _DownloadThread(bg_thread.BgThread):
    """后台下载更新包（多线程分段并行在 check_update.download 里完成）。"""

    progressed = Signal(int, int)   # (已下载字节, 总字节；总字节 0 表示未知)
    done = Signal(str)              # 下载完成 → 本地路径
    failed = Signal(str)            # 失败原因；空串表示用户取消

    def __init__(self, url, sha256='', version='', force=False, parent=None):
        super().__init__(parent)
        self._url = url
        self._sha256 = sha256 or ''
        self._version = version or ''
        self._force = bool(force)
        self._cancel = threading.Event()

    def run(self):
        from f_hamlog import check_update
        try:
            path = check_update.download(
                self._url,
                progress=lambda done, total: self.progressed.emit(int(done), int(total)),
                cancel=self._cancel,
                sha256=self._sha256 or None,
                version=self._version,
                force=self._force)
        except check_update.Cancelled:
            self.failed.emit('')
        except Exception as e:
            self.failed.emit(str(e))
        else:
            self.done.emit(path)

    def stop(self):
        """取消下载（关闭进度窗、退出程序时都会被调到）。"""
        self._cancel.set()


def _is_installer_url(url):
    """下载地址是否直接指向安装包（否则只能打开网页让用户自己下）。"""
    path = str(url or '').split('?', 1)[0].split('#', 1)[0].lower()
    return path.endswith('.exe') or path.endswith('.msi')


def _start_update_check(window, button):
    """「检查更新」按钮的入口：预览版直接拒绝，正式版起线程去查。"""
    global _update_check_thread
    from f_hamlog import check_update
    if check_update.is_preview_version():
        QMessageBox.information(
            window, i18n.tr('检查更新'),
            i18n.tr('当前是预览版，不参与自动更新。\n请从项目主页获取正式版。'))
        return
    if _update_check_thread is not None and _update_check_thread.isRunning():
        return

    button.setEnabled(False)
    button.setText(i18n.tr('检查中…'))
    thread = _CheckThread(window)

    def _finished(info):
        button.setEnabled(True)
        button.setText(i18n.tr('检查更新'))
        _on_update_checked(window, info)

    thread.result.connect(_finished)
    thread.start()
    _update_check_thread = thread


def _on_update_checked(window, info):
    info = info or {}
    status = info.get('status')
    if status == 'error':
        QMessageBox.warning(
            window, i18n.tr('检查更新'),
            i18n.tr('检查更新失败：\n{}\n\n请稍后重试。').format(
                info.get('detail') or i18n.tr('网络不可用')))
        return
    if status == 'preview':
        QMessageBox.information(
            window, i18n.tr('检查更新'),
            i18n.tr('当前是预览版，不参与自动更新。\n请从项目主页获取正式版。'))
        return
    if status == 'latest':
        QMessageBox.information(
            window, i18n.tr('检查更新'),
            i18n.tr('已是最新版本（{}）。').format(__version__))
        return
    if status != 'new':
        return

    version = info.get('version') or '?'
    url = info.get('url') or ''
    if not _is_installer_url(url):
        if QMessageBox.question(
                window, i18n.tr('发现新版本'),
                i18n.tr('发现新版本 {}，是否打开下载页面？').format(version)) == QMessageBox.Yes:
            webbrowser.open(url)
        return

    # 下载前先看本地：上次可能已经下完了（选了「稍后」/ 装到一半取消 / 顺手关了窗），
    # 这时不该再白下几十 MB。
    from f_hamlog import check_update
    cached = check_update.find_installer(url, sha256=info.get('sha256') or '', version=version)
    force = False
    if cached:
        choice = _ask_cached(window, version, cached)
        if choice == 'install':
            _install_update(window, cached['path'], version, confirm=False)
            return
        if choice != 'download':
            return
        force = True                        # 明确选了「重新下载」→ 别又被缓存拦下
    elif QMessageBox.question(
            window, i18n.tr('发现新版本'),
            i18n.tr('发现新版本 {}，是否下载并安装？\n当前版本：{}').format(
                version, __version__)) != QMessageBox.Yes:
        return
    _start_update_download(window, version, url, info.get('sha256') or '', force)


def _ask_cached(window, version, found):
    """本地已有安装包时的三选一，返回 ``'install'`` / ``'download'`` / ``''``（取消）。

    **不能用 QMessageBox**：它按 role 排按钮，RejectRole 会被塞到「立即安装」右边
    （实测 Accept/Reject/Action → 立即安装、稍后、重新下载），更致命的是**没有
    RejectRole 按钮时，标题栏叉号和 Esc 都失效**（实测只有「单按钮 + Accept」那种
    才能被 close() 关掉，两按钮的怎么点都没反应）。这里自己排顺序，叉号 / Esc 都能关。
    """
    from f_hamlog import check_update
    size_txt = check_update.format_size(found.get('size') or 0)
    trusted = found.get('verified') in ('sha256', 'meta')
    picked = {'value': ''}

    dlg = _NoMaximizeDialog(window)
    dlg.setWindowTitle(i18n.tr('发现新版本'))
    dlg.setModal(True)
    dlg.setMinimumWidth(460)
    # 上限：安装包路径可能很长，不封顶的话 QLabel 的单行 sizeHint 会把窗口越撑越宽
    dlg.setMaximumWidth(600)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(18, 16, 18, 14)
    lay.setSpacing(10)

    text = QLabel(i18n.tr('发现新版本 {}，本地已有下载好的安装包：\n{}（{}）').format(
        version, found.get('path') or '', size_txt), dlg)
    text.setWordWrap(True)
    text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(text)

    note = QLabel(i18n.tr('是否直接安装？') if trusted
                  else i18n.tr('这个安装包没有校验过，重新下载更稳妥。'), dlg)
    note.setWordWrap(True)
    note.setStyleSheet(theme.hint_css())
    lay.addWidget(note)
    theme.watch_theme(dlg, lambda: note.setStyleSheet(theme.hint_css()))

    row = QHBoxLayout()
    row.setSpacing(8)
    row.addStretch(1)
    btn_now = QPushButton(i18n.tr('立即安装'), dlg)
    btn_again = QPushButton(i18n.tr('重新下载'), dlg)
    btn_later = QPushButton(i18n.tr('稍后'), dlg)
    for b in (btn_now, btn_again, btn_later):
        row.addWidget(b)
    lay.addLayout(row)

    def _pick(value):
        picked['value'] = value
        dlg.accept()

    btn_now.clicked.connect(lambda: _pick('install'))
    btn_again.clicked.connect(lambda: _pick('download'))
    btn_later.clicked.connect(dlg.reject)       # 与叉号 / Esc 同效
    (btn_now if trusted else btn_again).setDefault(True)
    (btn_now if trusted else btn_again).setFocus()

    dlg.exec()
    return picked['value']


def _alive(window):
    """window 可能已经被销毁（下载窗是非模态的，用户随时能关掉设置窗口）。

    被销毁的 C++ 对象一访问就抛 RuntimeError，这里把它换成 None ——
    没有父窗口的 QMessageBox 照样能弹，不该因为父窗口没了就崩。
    """
    try:
        if window is not None:
            window.windowTitle()        # 碰一下 C++ 对象，探活
        return window
    except RuntimeError:
        return None


def _start_update_download(window, version, url, sha256='', force=False):
    global _update_download_thread, _update_dialog
    if _update_download_thread is not None and _update_download_thread.isRunning():
        # 已经在下了（比如用户又点了一次检查更新）：把现有的进度窗提上来，别开第二个
        if _update_dialog is not None:
            _update_dialog.showNormal()
            _update_dialog.raise_()
            _update_dialog.activateWindow()
        return

    # parent 给 None：进度窗是独立顶层窗口。设了父对象会被当成「被拥有的窗口」，
    # 父窗口一最小化/关闭它就跟着走；而下载期间关掉设置窗口不该中断下载。
    dlg = _UpdateProgressDialog(None)
    dlg.setWindowTitle(i18n.tr('下载更新'))
    # 非模态 + 最小化按钮：模态时最小化了自己，父窗口却仍被阻塞（点了没反应，
    # 看着像卡死）；非模态下可以最小化去干别的，也能继续用主界面。
    # 最大化由 _no_maximize() 关掉（在 __init__ 里就设好了，这里只补最小化）。
    dlg.setWindowModality(Qt.NonModal)
    dlg.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    # 文案要放下「已下载/总大小 · 速度 · 剩余时间」：中文约 406 px、英文约 430 px，
    # 定 480 就够（数字与斜杠之间不留空格，省 12 px）；不设下限的话每次改文案 adjustSize
    # 会让窗口随数字位数忽宽忽窄。
    dlg.setMinimumWidth(480)
    dlg.setValue(0)
    dlg.show()
    if window is not None:
        # 没有父窗口就不会自动居中，手动摆到设置窗口正中间
        geo = window.frameGeometry()
        dlg.move(geo.center() - dlg.rect().center())
    _update_dialog = dlg

    from f_hamlog import check_update
    meter = check_update.Speedometer()      # 滑动窗口算速度，避免数字乱跳
    eta_est = check_update.EtaEstimator()   # 累计平均 + 只降不升，避免剩余时间来回跳

    thread = _DownloadThread(url, sha256, version, force, window)

    # 关闭标记。QProgressDialog 的坑：**setValue() 内部会 ensureDialog() → show()**，
    # 所以点叉关掉之后，只要还有一帧进度信号进来，窗口就会自己弹回来（看起来像关不掉）。
    # 这里用 state 兜住：一旦关闭，后续进度一律不碰窗口。
    state = {'closed': False}

    def _shut():
        global _update_dialog
        state['closed'] = True
        dlg.reset()         # reset 内部也会 setValue()，可能把窗口 show 出来
        dlg.hide()          # 所以顺序必须是「先 reset 再 hide」
        if _update_dialog is dlg:
            _update_dialog = None

    def _progress(done, total):
        if state['closed']:
            return
        # 速度、剩余时间都是与语言无关的数值，只有句式走词表
        speed = meter.update(done)
        speed_txt = check_update.format_speed(speed) if done else '—'
        if total > 0:
            if dlg.maximum() != 100:
                dlg.setMaximum(100)     # 从「不定长」切回百分比
            dlg.setValue(min(100, int(done * 100 / total)))
            eta = check_update.format_eta(eta_est.update(done, total))
            if eta:
                dlg.setLabelText(i18n.tr('{}/{} · {} · 剩余 {}').format(
                    check_update.format_size(done),
                    check_update.format_size(total), speed_txt, eta))
            else:
                dlg.setLabelText(i18n.tr('{}/{} · {}').format(
                    check_update.format_size(done),
                    check_update.format_size(total), speed_txt))
        else:
            if dlg.maximum() != 0:
                dlg.setMaximum(0)       # 拿不到总大小 → 不定长进度条，也算不出剩余时间
            dlg.setLabelText(i18n.tr('已下载 {} · {}').format(
                check_update.format_size(done), speed_txt))

    def _ok(path):
        _shut()
        _install_update(_alive(window), path, version)

    def _fail(message):
        _shut()
        if message:                     # 空串 = 用户主动取消，不再弹窗
            QMessageBox.warning(_alive(window), i18n.tr('下载失败'), message)

    def _cancel():
        """点「取消」/ 点叉 / 按 Esc：先关窗（别让下一帧进度又弹回来），再让线程收手。"""
        _shut()
        thread.stop()

    thread.progressed.connect(_progress)
    thread.done.connect(_ok)
    thread.failed.connect(_fail)
    dlg.canceled.connect(_cancel)
    thread.start()
    _update_download_thread = thread


def _install_update(window, path, version, confirm=True):
    """下载完成 → 问一句 → 运行安装包 → 退出本程序。

    ``confirm=False`` 用于「本地已有安装包」那条路：那边已经问过「是否直接安装」，
    这里别再问第二遍。
    """
    from f_hamlog import check_update
    if confirm:
        box = QMessageBox(window)
        box.setWindowTitle(i18n.tr('安装更新'))
        box.setText(i18n.tr('更新包已下载完成（{}）：\n{}\n\n是否立即安装？').format(version, path))
        box.setInformativeText(i18n.tr('安装程序会关闭 F HamLog，安装完成后请重新打开。'))
        btn_now = box.addButton(i18n.tr('立即安装'), QMessageBox.AcceptRole)
        box.addButton(i18n.tr('稍后'), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_now:
            return

    try:
        check_update.run_installer(path)
    except Exception as e:
        QMessageBox.warning(window, i18n.tr('安装更新'),
                            i18n.tr('无法运行安装包：\n{}').format(e))
        return
    # 安装器已启动：先退程序，它才能覆盖正在运行的主程序文件
    app = QApplication.instance()
    if app is not None:
        app.quit()


def main(window):
    from f_hamlog import satellite_pred as sp
    with open(app_path('file/m_xml.txt'), 'r', encoding='utf-8') as f:
        xml_dict = eval(f.read())
    m_call = xml_dict.get('m_call', '')
    m_qth = xml_dict.get('m_qth', '')
    m_dig = xml_dict.get('m_dig', '')
    aouto_save_b = xml_dict.get('aouto_save', False)
    aouto_list_b = xml_dict.get('aouto_list', False)
    m_lat = xml_dict.get('m_lat', 0.0)
    m_lon = xml_dict.get('m_lon', 0.0)
    m_alt = xml_dict.get('m_alt', 0.0)
    sat_auto_update_b = xml_dict.get('sat_auto_update', False)
    sat_update_hours = int(xml_dict.get('sat_update_hours', 24) or 24)

    def set():
        m_call = m_call_input.text()
        m_qth = m_qth_input.text()
        m_dig = m_dig_input.text()
        aouto_save_b = aouto_save.isChecked()
        aouto_list_b = aouto_list_.isChecked()
        sat_auto_update_b = sat_auto_update.isChecked()
        sat_update_hours = sat_update_hours_spin.value()
        try:
            m_lat = float(lat_input.text())
            m_lon = float(lon_input.text())
            m_alt = float(alt_input.text())
        except ValueError:
            QMessageBox.warning(window, "输入错误", "观测站经纬度/海拔请填写数字。")
            return
        print(f"保存设置: 我的呼号={m_call}, 我的QTH={m_qth}, 我的设备={m_dig}, 自动保存={aouto_save_b}, 自动按时间排序={aouto_list_b}, 观测站=({m_lat},{m_lon},{m_alt}), 星历数据源={sp.load_tle_sources()}")
        # 读取现有设置，仅更新本窗口管理的键，保留其它键（如卫星预测设置 sat_*）
        with open(app_path('file/m_xml.txt'), 'r', encoding='utf-8') as f:
            data = eval(f.read())
        data.update({
            'm_call': m_call,
            'm_qth': m_qth,
            'm_dig': m_dig,
            'aouto_save': aouto_save_b,
            'aouto_list': aouto_list_b,
            'm_lat': m_lat,
            'm_lon': m_lon,
            'm_alt': m_alt,
            'sat_auto_update': sat_auto_update_b,
            'sat_update_hours': sat_update_hours,
        })
        with open(app_path('file/m_xml.txt'), 'w', encoding='utf-8') as f:
            f.write(str(data))
        window.close()
    def pack_set():
        print("插件设置")
        from f_hamlog import pack_set
        global pack_set_window  # 保持引用，防止被回收
        pack_set_window = QMainWindow()
        pack_set.main(pack_set_window)
        # pack_set.main 会在内部 show 窗口，但保留全局引用以防被回收
    def back_set():
        import os
        import shutil
        print("从其他版本导入数据")  # 保持引用，防止被回收
        folder = QFileDialog.getExistingDirectory(
            window, i18n.tr("选择其他版本 F HamLog.exe 所在的文件夹"), desktop_dir())
        if folder:
            print(f"选择的文件夹: {folder}")
            file_path = os.path.join(folder, 'file')
            if os.path.exists(file_path):
                with open(app_path('file/m_xml.txt'), 'r', encoding='utf-8') as f:
                    data = eval(f.read())
                with open(os.path.join(file_path, 'm_xml.txt'), 'r', encoding='utf-8') as f:
                    data_old = eval(f.read())
                for i in data_old.keys():
                    data[i] = data_old[i]
                with open(app_path('file/m_xml.txt'), 'w', encoding='utf-8') as f:
                    f.write(str(data))
                back_item = i18n.tr('用户设置')

                if os.path.exists(os.path.join(file_path, 'main.fhl')):
                    os.remove(app_path('file/main.fhl'))  # 删除旧的 main.fhl 文件
                    shutil.copyfile(os.path.join(file_path, 'main.fhl'), app_path('file/main.fhl'))
                    back_item += i18n.tr('、通联日志文件')

                if os.path.exists(os.path.join(file_path, 'sat_radio_dict.txt')):
                    shutil.copyfile(os.path.join(file_path, 'sat_radio_dict.txt'), app_path('file/sat_radio_dict.txt'))
                    back_item += i18n.tr('、卫星转发器表')

                if os.path.exists(os.path.join(file_path, 'tqsl_dict.txt')):
                    shutil.copyfile(os.path.join(file_path, 'tqsl_dict.txt'), app_path('file/tqsl_dict.txt'))
                    back_item += i18n.tr('、TQSL映射表')

                if os.path.exists(os.path.join(file_path, 'sat_map_markers.txt')):
                    shutil.copyfile(os.path.join(file_path, 'sat_map_markers.txt'), app_path('file/sat_map_markers.txt'))
                    back_item += i18n.tr('、卫星地图标记点')

                if os.path.exists(os.path.join(file_path, 'tle_sources.txt')):
                    shutil.copyfile(os.path.join(file_path, 'tle_sources.txt'), app_path('file/tle_sources.txt'))
                    back_item += i18n.tr('、星历数据源')

                if os.path.exists(os.path.join(file_path, 'amateur.tle')):
                    shutil.copyfile(os.path.join(file_path, 'amateur.tle'), app_path('file/amateur.tle'))
                    back_item += i18n.tr('、卫星数据缓存')

                if os.path.exists(os.path.join(file_path, 'known_server_keys.txt')):
                    shutil.copyfile(os.path.join(file_path, 'known_server_keys.txt'), app_path('file/known_server_keys.txt'))
                    back_item += i18n.tr('、多人日志缓存')
    

                # 旧版本的数据以「卫星名」为键，这里立即按当前星历升级为卫星编号
                # （静默执行：解析不出的条目原样保留，不打断导入流程）。
                try:
                    sp.migrate_legacy_sat_data()
                except Exception:
                    pass

                QMessageBox.information(
                    window, "从其他版本导入数据",
                    i18n.tr('成功导入{}\n（目前不支持从其他版本中导入插件）').format(back_item))
                window.close()
            else:
                QMessageBox.warning(window, "从其他版本导入数据",
                                    i18n.tr("请选择其他版本 F HamLog.exe 所在的文件夹！"))
                back_set()

    # 颜色模式与自动保存合并成一行后，内容高度减少约 30px，窗口高度同步收回。
    # 固定尺寸在窗口建完后由 _fit_window() 统一设定（中文下即 770×475，与历史版本一致；
    # 英文文案更长时按内容放宽，避免被截断）。
    BASE_W, BASE_H = 770, 475
    window.resize(BASE_W, BASE_H)
    window.setWindowTitle('设置')
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    m_call_label = QLabel("我的呼号:", central_widget)
    m_call_input = QLineEdit(central_widget)
    m_call_input.setText(m_call)
    # 我的呼号始终实时转大写
    call_upper.connect_callsign_upper(m_call_input, lambda: 'm_call')
    m_qth_label = QLabel("我的QTH:", central_widget)
    m_qth_input = QLineEdit(central_widget)
    m_qth_input.setText(m_qth)
    m_dig_label = QLabel("我的设备:", central_widget)
    m_dig_input = QLineEdit(central_widget)
    m_dig_input.setText(m_dig)
    lat_input = QLineEdit(central_widget)
    lat_input.setFixedWidth(110)
    lat_input.setText(f"{m_lat:.5f}")
    lon_input = QLineEdit(central_widget)
    lon_input.setFixedWidth(110)
    lon_input.setText(f"{m_lon:.5f}")
    alt_input = QLineEdit(central_widget)
    alt_input.setFixedWidth(90)
    alt_input.setText(f"{m_alt:.1f}")
    grid_input = QLineEdit(central_widget)
    grid_input.setFixedWidth(110)
    try:
        grid_input.setPlaceholderText('梅登黑格网格')
        grid_input.setText(sp.latlon_to_maidenhead(m_lat, m_lon))
    except Exception:
        grid_input.setPlaceholderText('梅登黑格网格，如 PM84')
    aouto_save = QCheckBox("自动保存", central_widget)
    aouto_save.setChecked(aouto_save_b)
    aouto_list_ = QCheckBox("自动按时间排序", central_widget)
    aouto_list_.setChecked(aouto_list_b)
    sat_auto_update = QCheckBox("星历自动更新", central_widget)
    sat_auto_update.setChecked(sat_auto_update_b)
#     sat_auto_update.setToolTip("开启后，程序会在后台按设定间隔自动刷新卫星星历(TLE)")
    sat_update_hours_spin = QSpinBox(central_widget)
    sat_update_hours_spin.setRange(1, 168)
    sat_update_hours_spin.setValue(sat_update_hours)
    sat_update_hours_spin.setSuffix(" 小时")
    sat_update_label = QLabel("更新间隔:", central_widget)

    # ---------- 颜色模式（即改即生效并落盘，与「星历数据源」窗口同样的即时风格） ----------
    theme_mode_label = QLabel('颜色模式:', central_widget)
    theme_mode_box = QComboBox(central_widget)
    for _value, _label in theme.MODE_LABELS:
        theme_mode_box.addItem(_label, _value)
    _idx = theme_mode_box.findData(theme.load_mode())
    if _idx >= 0:
        theme_mode_box.setCurrentIndex(_idx)
#     theme_mode_box.setToolTip('跟随系统：随系统深浅色自动切换；浅色/深色：固定外观。'
#                               '改动立即生效并保存，无需点「保存更改」。')

    def on_theme_mode_changed(_index=None):
        mode = theme_mode_box.currentData()
        theme.set_mode(mode)    # 立即生效（全部已打开窗口一起刷新）
        theme.save_mode(mode)   # 立即落盘（不必点「保存更改」）
        print('颜色模式:', theme.MODE_LABEL_OF.get(mode, mode))

    theme_mode_box.currentIndexChanged.connect(on_theme_mode_changed)

    # ---------- 界面语言（同样即改即生效并落盘） ----------
    lang_label = QLabel('语言 Language:', central_widget)
    lang_box = QComboBox(central_widget)
    for _value, _label in i18n.LANG_LABELS:
        lang_box.addItem(_label, _value)
    _lidx = lang_box.findData(i18n.current_language())
    if _lidx >= 0:
        lang_box.setCurrentIndex(_lidx)

    def on_language_changed(_index=None):
        lang = lang_box.currentData()
        i18n.set_language(lang)     # 立即生效：所有已打开窗口原地重译
        i18n.save_language(lang)    # 立即落盘（不必点「保存更改」）
        _fit_window()               # 英文文案更长，按需放宽窗口，避免被截断
        print('语言:', lang)

    lang_box.currentIndexChanged.connect(on_language_changed)

    # 开关型选项与颜色模式并作一行，省下一行高度留给窗口整体（770px 下合计约 660px）
    h_layout = QHBoxLayout()
    h_layout.addWidget(aouto_save)
    h_layout.addWidget(aouto_list_)
    h_layout.addSpacing(15)
    h_layout.addWidget(sat_auto_update)
    h_layout.addWidget(sat_update_label)
    h_layout.addWidget(sat_update_hours_spin)

    # ---------- 星历数据源：按钮与「插件设置」同一行（数据源配置在独立窗口） ----------
    src_set_btn = QPushButton("设置星历数据源", central_widget)
#     src_set_btn.setToolTip(
#         "在独立的「星历数据源」窗口中增删与排序 TLE 下载地址，列表里双击即可编辑；"
#         "保存后立即生效。")

    def set_sources():
        """打开独立的「星历数据源」窗口（非模态；已打开则前置复用）。"""
        global tle_source_win  # 保持引用，防止被回收
        if tle_source_win is not None:
            try:
                if tle_source_win.isVisible():
                    tle_source_win.raise_()
                    tle_source_win.activateWindow()
                    return
            except RuntimeError:
                tle_source_win = None   # 底层窗口已销毁
        from f_hamlog import tle_source_window
        tle_source_win = QMainWindow()
        tle_source_window.main(tle_source_win)

    src_set_btn.clicked.connect(lambda: set_sources())

    sett_button = QPushButton("保存更改", central_widget)
    sett_button.setMinimumWidth(170)   # 加宽：默认宽度偏窄，与同行控件不协调
    sett_button.clicked.connect(lambda: set())
    layout.addWidget(m_call_label)
    layout.addWidget(m_call_input)
    layout.addWidget(m_qth_label)
    layout.addWidget(m_qth_input)
    layout.addWidget(m_dig_label)
    layout.addWidget(m_dig_input)
    layout.addWidget(QLabel("观测站位置（纬度北纬为正，经度东经为正）：", central_widget))
    pos_row = QHBoxLayout()
    pos_row.addWidget(QLabel("纬度(°):", central_widget))
    pos_row.addWidget(lat_input)
    pos_row.addWidget(QLabel("经度(°):", central_widget))
    pos_row.addWidget(lon_input)
    pos_row.addWidget(QLabel("海拔(m):", central_widget))
    pos_row.addWidget(alt_input)
    pos_row.addSpacing(15)
    pos_row.addWidget(QLabel('坐标网:', central_widget))
    pos_row.addWidget(grid_input)
    pos_row.addStretch(1)
    layout.addLayout(pos_row)

    def on_grid_to_coord():
        text = grid_input.text().strip()
        if not text:
            return
        try:
            glat, glon = sp.maidenhead_to_latlon(text)
        except ValueError as e:
            QMessageBox.warning(window, '网格无效', str(e))
            return
        grid_input.setText(sp.latlon_to_maidenhead(glat, glon))
        lat_input.setText(f'{glat:.5f}')
        lon_input.setText(f'{glon:.5f}')

    def on_coord_to_grid():
        try:
            grid_input.setText(sp.latlon_to_maidenhead(
                float(lat_input.text()), float(lon_input.text())))
        except (TypeError, ValueError):
            return

    lat_input.editingFinished.connect(on_coord_to_grid)
    lon_input.editingFinished.connect(on_coord_to_grid)
    grid_input.editingFinished.connect(on_grid_to_coord)
    layout.addLayout(h_layout)

    # 「颜色模式」+「语言」并作一行，右侧靠边放「保存更改」按钮，中间用 stretch 撑开
    # （先选颜色/语言、再保存，符合操作顺序）。这两项都是「即改即生效并落盘」的设置，
    # 放同一行风格一致；上方那行只留开关与星历间隔，不再挤在一起。
    lang_layout = QHBoxLayout()
    lang_layout.addWidget(theme_mode_label)
    lang_layout.addWidget(theme_mode_box)
    lang_layout.addSpacing(15)
    lang_layout.addWidget(lang_label)
    lang_layout.addWidget(lang_box)
    lang_layout.addStretch(1)
    lang_layout.addWidget(sett_button)
    layout.addLayout(lang_layout)
    
    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    bottom_layout = QHBoxLayout()
    pack_button = QPushButton("插件设置", central_widget)
    pack_button.clicked.connect(lambda: pack_set())
    back_button = QPushButton("从其他版本导入数据", central_widget)
    back_button.clicked.connect(lambda: back_set())
    # 三个按钮平分整行宽度（与「保存更改」同样的通栏样式）
    bottom_layout.addWidget(pack_button, 1)
    bottom_layout.addWidget(src_set_btn, 1)
    bottom_layout.addWidget(back_button, 1)
    layout.addLayout(bottom_layout)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)


    def _link_html():
        """反馈/更新链接的 HTML：链接色跟随主题（写死 #0066cc 在深色底上偏暗）。"""
        return '''<html><head/>
                <style>a {text-decoration: none; 
                        color: %s;}
                .t {margin-top: 5px;}</style>
                </head><body>
                <div class="t">%s</div>
                <div class="t">%s<a href="https://mubi-baihua.pages.dev/f_hamlog.html">https://mubi-baihua.pages.dev/f_hamlog.html</a></div>
                <div class="t">%s<a href="https://github.com/Mubi-Baihua/F_HamLog/">https://github.com/Mubi-Baihua/F_HamLog/</a></div>
                </body></html>''' % (
            theme.link_color().name(),
            i18n.tr('问题反馈到：BI8SQL@outlook.com'),
            i18n.tr('版本更新请访问：'),
            i18n.tr('Github项目：'),
        )

    fk_l = QLabel()
    fk_l.setText(_link_html())
    fk_l.setOpenExternalLinks(True)
    layout.addWidget(fk_l)
    # 颜色模式切换后重刷链接色；语言切换后重刷文案
    theme.watch_theme(window, lambda: fk_l.setText(_link_html()))
    i18n.watch_language(window, lambda: fk_l.setText(_link_html()))

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    def _ver_text():
        # 版本号来自 f_hamlog.__version__（单一来源，见 __init__.py）
        return i18n.tr('F HamLog 版本：') + __version__

    fk_v = QLabel(_ver_text(), central_widget)
    # 语言切换后重刷文案（前缀走词表，版本号动态拼接）
    i18n.watch_language(window, lambda: fk_v.setText(_ver_text()))

    # 「检查更新」与版本号同一行：版本号右侧才是这个按钮的自然位置，
    # 而且不额外占一行高度（设置窗口是固定尺寸，多一行就要重新排版）。
    update_btn = QPushButton(i18n.tr('检查更新'), central_widget)
    update_btn.setFixedHeight(24)
    update_btn.setMinimumWidth(96)
    update_btn.clicked.connect(lambda: _start_update_check(window, update_btn))

    ver_row = QHBoxLayout()
    ver_row.setContentsMargins(0, 0, 0, 0)
    ver_row.addWidget(fk_v)
    ver_row.addStretch(1)
    ver_row.addWidget(update_btn)
    layout.addLayout(ver_row)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    cc_l = QLabel("Coded by BI8SQL", central_widget)
    layout.addWidget(cc_l)

    def _fit_window():
        """把窗口固定为「参考尺寸」与「当前语言下内容所需尺寸」中的较大者。

        中文下内容本来就放进 770×475，尺寸与历史版本**完全一致**；
        英文文案普遍比中文长，按内容放宽，避免控件文字被挤掉/截断。
        """
        i18n.fit_window(window, BASE_W, BASE_H)

    # 先 show()：顶层窗口的 Show 事件会触发 i18n 把控件树翻成当前语言，
    # 之后 _fit_window() 量到的尺寸才是「该语言下真正的」文案宽度。
    # （反过来先量后翻，英文界面会按中文尺寸定死窗口而截断文字。）
    window.show()
    _fit_window()

if __name__ == '__main__':
    app = QApplication()
    theme.init_app(app)
    i18n.install(app)
    window=QMainWindow()
    main(window)
    app.exec()