from PySide6.QtWidgets import *
import call_upper
import theme
import i18n
from dialog_defaults import desktop_dir

# 「星历数据源」独立窗口的引用（防止被回收；非模态，可重复打开）
tle_source_win = None


def main(window):
    import satellite_pred as sp
    with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
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
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
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
        with open('file/m_xml.txt', 'w', encoding='utf-8') as f:
            f.write(str(data))
        window.close()
    def pack_set():
        print("插件设置")
        import pack_set
        global pack_set_window  # 保持引用，防止被回收
        pack_set_window = QMainWindow()
        pack_set.main(pack_set_window)
        # pack_set.main 会在内部 show 窗口，但保留全局引用以防被回收
    def back_set():
        import os
        import shutil
        print("从其他版本导入数据")  # 保持引用，防止被回收
        folder = QFileDialog.getExistingDirectory(
            window, i18n.tr("选择之前版本 F HamLog.exe 所在的文件夹"), desktop_dir())
        if folder:
            print(f"选择的文件夹: {folder}")
            file_path = os.path.join(folder, 'file')
            if os.path.exists(file_path):
                with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
                    data = eval(f.read())
                with open(os.path.join(file_path, 'm_xml.txt'), 'r', encoding='utf-8') as f:
                    data_old = eval(f.read())
                for i in data_old.keys():
                    data[i] = data_old[i]
                with open('file/m_xml.txt', 'w', encoding='utf-8') as f:
                    f.write(str(data))
                back_item = i18n.tr('用户设置')

                if os.path.exists(os.path.join(file_path, 'main.fhl')):
                    os.remove('file/main.fhl')  # 删除旧的 main.fhl 文件
                    shutil.copyfile(os.path.join(file_path, 'main.fhl'), 'file/main.fhl')
                    back_item += i18n.tr('、通联日志文件')

                if os.path.exists(os.path.join(file_path, 'sat_radio_dict.txt')):
                    shutil.copyfile(os.path.join(file_path, 'sat_radio_dict.txt'), 'file/sat_radio_dict.txt')
                    back_item += i18n.tr('、卫星转发器表')

                if os.path.exists(os.path.join(file_path, 'tqsl_dict.txt')):
                    shutil.copyfile(os.path.join(file_path, 'tqsl_dict.txt'), 'file/tqsl_dict.txt')
                    back_item += i18n.tr('、TQSL映射表')

                if os.path.exists(os.path.join(file_path, 'sat_map_markers.txt')):
                    shutil.copyfile(os.path.join(file_path, 'sat_map_markers.txt'), 'file/sat_map_markers.txt')
                    back_item += i18n.tr('、卫星地图标记点')

                if os.path.exists(os.path.join(file_path, 'tle_sources.txt')):
                    shutil.copyfile(os.path.join(file_path, 'tle_sources.txt'), 'file/tle_sources.txt')
                    back_item += i18n.tr('、星历数据源')

                if os.path.exists(os.path.join(file_path, 'amateur.tle')):
                    shutil.copyfile(os.path.join(file_path, 'amateur.tle'), 'file/amateur.tle')
                    back_item += i18n.tr('、卫星数据缓存')

                if os.path.exists(os.path.join(file_path, 'known_server_keys.txt')):
                    shutil.copyfile(os.path.join(file_path, 'known_server_keys.txt'), 'file/known_server_keys.txt')
                    back_item += i18n.tr('、多人日志缓存')
    

                # 旧版本的数据以「卫星名」为键，这里立即按当前星历升级为卫星编号
                # （静默执行：解析不出的条目原样保留，不打断导入流程）。
                try:
                    sp.migrate_legacy_sat_data()
                except Exception:
                    pass

                QMessageBox.information(
                    window, "从其他版本导入数据",
                    i18n.tr('成功导入{}\n（目前不支持从之前版本中导入插件）').format(back_item))
                window.close()
            else:
                QMessageBox.warning(window, "从其他版本导入数据",
                                    i18n.tr("请选择之前版本 F HamLog.exe 所在的文件夹！"))
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
        import tle_source_window
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
                <div class="t">%s<a href="https://mubi-baihua.github.io/f_hamlog.html">https://mubi-baihua.github.io/f_hamlog.html</a></div>
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

    fk_v = QLabel("F HamLog 版本：2.6.0", central_widget)
    layout.addWidget(fk_v)

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