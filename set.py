from PySide6.QtWidgets import *
import call_upper
import theme
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
        print("从之前版本导入数据")  # 保持引用，防止被回收
        folder = QFileDialog.getExistingDirectory(window, "选择之前版本 F HamLog.exe 所在的文件夹", desktop_dir())
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
                back_item = '用户设置'

                if os.path.exists(os.path.join(file_path, 'main.fhl')):
                    os.remove('file/main.fhl')  # 删除旧的 main.fhl 文件
                    shutil.copyfile(os.path.join(file_path, 'main.fhl'), 'file/main.fhl')
                    back_item += '、通联日志文件'

                if os.path.exists(os.path.join(file_path, 'sat_radio_dict.txt')):
                    shutil.copyfile(os.path.join(file_path, 'sat_radio_dict.txt'), 'file/sat_radio_dict.txt')
                    back_item += '、卫星转发器表(sat_radio_dict.txt)'

                if os.path.exists(os.path.join(file_path, 'tqsl_dict.txt')):
                    shutil.copyfile(os.path.join(file_path, 'tqsl_dict.txt'), 'file/tqsl_dict.txt')
                    back_item += '、TQSL映射表(tqsl_dict.txt)'

                QMessageBox.information(window, "从之前版本导入数据", f"成功导入{back_item}\n（目前不支持从之前版本中导入插件）")
                window.close()
            else:
                QMessageBox.warning(window, "从之前版本导入数据", "请选择之前版本 F HamLog.exe 所在的文件夹！")
                back_set()

    # 颜色模式与自动保存合并成一行后，内容高度减少约 30px，窗口高度同步收回
    window.resize(770, 475)
    window.setFixedSize(770, 475)
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
    sat_auto_update.setToolTip("开启后，程序会在后台按设定间隔自动刷新卫星星历(TLE)")
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
    theme_mode_box.setToolTip('跟随系统：随系统深浅色自动切换；浅色/深色：固定外观。'
                              '改动立即生效并保存，无需点「保存更改」。')

    def on_theme_mode_changed(_index=None):
        mode = theme_mode_box.currentData()
        theme.set_mode(mode)    # 立即生效（全部已打开窗口一起刷新）
        theme.save_mode(mode)   # 立即落盘（不必点「保存更改」）
        print('颜色模式:', theme.MODE_LABEL_OF.get(mode, mode))

    theme_mode_box.currentIndexChanged.connect(on_theme_mode_changed)

    # 开关型选项与颜色模式并作一行，省下一行高度留给窗口整体（770px 下合计约 660px）
    h_layout = QHBoxLayout()
    h_layout.addWidget(aouto_save)
    h_layout.addWidget(aouto_list_)
    h_layout.addSpacing(15)
    h_layout.addWidget(sat_auto_update)
    h_layout.addWidget(sat_update_label)
    h_layout.addWidget(sat_update_hours_spin)
    h_layout.addSpacing(15)
    h_layout.addWidget(theme_mode_label)
    h_layout.addWidget(theme_mode_box)

    # ---------- 星历数据源：按钮与「插件设置」同一行（数据源配置在独立窗口） ----------
    src_set_btn = QPushButton("设置星历数据源", central_widget)
    src_set_btn.setToolTip(
        "在独立的「星历数据源」窗口中增删与排序 TLE 下载地址，列表里双击即可编辑；"
        "保存后立即生效。")

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
    layout.addWidget(sett_button)
    
    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    bottom_layout = QHBoxLayout()
    pack_button = QPushButton("插件设置", central_widget)
    pack_button.clicked.connect(lambda: pack_set())
    back_button = QPushButton("从之前版本导入数据", central_widget)
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
                <div class="t">问题反馈到：BI8SQL@outlook.com</div>
                <div class="t">版本更新请访问：<a href="https://mubi-baihua.github.io/f_hamlog.html">https://mubi-baihua.github.io/f_hamlog.html</a></div>
                <div class="t">Github项目：<a href="https://github.com/Mubi-Baihua/F_HamLog/">https://github.com/Mubi-Baihua/F_HamLog/</a></div>
                </body></html>''' % theme.link_color().name()

    fk_l = QLabel()
    fk_l.setText(_link_html())
    fk_l.setOpenExternalLinks(True)
    layout.addWidget(fk_l)
    # 颜色模式切换后重刷链接色
    theme.watch_theme(window, lambda: fk_l.setText(_link_html()))

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    fk_v = QLabel("F HamLog 版本：2.4.0", central_widget)
    layout.addWidget(fk_v)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    cc_l = QLabel("Coded by BI8SQL", central_widget)
    layout.addWidget(cc_l)

    window.show()

if __name__ == '__main__':
    app = QApplication()
    theme.init_app(app)
    window=QMainWindow()
    main(window)
    app.exec()