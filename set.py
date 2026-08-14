from PySide6.QtWidgets import *
import call_upper
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
        print(f"保存设置: 我的呼号={m_call}, 我的QTH={m_qth}, 我的设备={m_dig}, 自动保存={aouto_save_b}, 自动按时间排序={aouto_list_b}, 观测站=({m_lat},{m_lon},{m_alt})")
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
        folder = QFileDialog.getExistingDirectory(window, "选择之前版本 F HamLog.exe 所在的文件夹", "")
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
    except Exception:
        grid_input.setPlaceholderText('梅登黑格网格，如 PM84')
    grid_to_coord = QPushButton('网格→坐标', central_widget)
    grid_to_coord.setToolTip('将梅登黑格网格（如 PM84）转换为经纬度并填入上方输入框')
    aouto_save = QCheckBox("自动保存", central_widget)
    aouto_save.setChecked(aouto_save_b)
    aouto_list_ = QCheckBox("自动按时间排序", central_widget)
    aouto_list_.setChecked(aouto_list_b)
    sat_auto_update = QCheckBox("卫星星历自动更新", central_widget)
    sat_auto_update.setChecked(sat_auto_update_b)
    sat_auto_update.setToolTip("开启后，程序会在后台按设定间隔自动从 Celestrak 刷新卫星星历(TLE) 缓存")
    sat_update_hours_spin = QSpinBox(central_widget)
    sat_update_hours_spin.setRange(1, 168)
    sat_update_hours_spin.setValue(sat_update_hours)
    sat_update_hours_spin.setSuffix(" 小时")
    sat_update_label = QLabel("更新间隔:", central_widget)
    h_layout = QHBoxLayout()
    h_layout.addWidget(aouto_save)
    h_layout.addWidget(aouto_list_)
    h_layout.addSpacing(15)
    h_layout.addWidget(sat_auto_update)
    h_layout.addWidget(sat_update_label)
    h_layout.addWidget(sat_update_hours_spin)
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
    pos_row.addWidget(grid_to_coord)
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
        lat_input.setText(f'{glat:.5f}')
        lon_input.setText(f'{glon:.5f}')

    grid_to_coord.clicked.connect(on_grid_to_coord)
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
    bottom_layout.addWidget(pack_button)
    bottom_layout.addWidget(back_button)
    layout.addLayout(bottom_layout)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)


    fk_l = QLabel()
    fk_l.setText('''<html><head/>
                <style>a {text-decoration: none; 
                        color: #0066cc;}
                .t {margin-top: 5px;}</style>
                </head><body>
                <div class="t">问题反馈到：BI8SQL@outlook.com</div>
                <div class="t">版本更新请访问：<a href="https://mubi-baihua.github.io/f_hamlog.html">https://mubi-baihua.github.io/f_hamlog.html</a></div>
                <div class="t">Github项目：<a href="https://github.com/Mubi-Baihua/F_HamLog/">https://github.com/Mubi-Baihua/F_HamLog/</a></div>
                </body></html>''')
    fk_l.setOpenExternalLinks(True)
    layout.addWidget(fk_l)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    fk_v = QLabel("F HamLog 版本：2.3.0", central_widget)
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
    window=QMainWindow()
    main(window)
    app.exec()