from PySide6.QtWidgets import *
def main(window):
    with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
        xml_dict = eval(f.read())
    m_call = xml_dict['m_call']
    m_qth = xml_dict['m_qth']
    m_dig = xml_dict['m_dig']
    aouto_save_b = xml_dict['aouto_save']
    aouto_list_b = xml_dict['aouto_list']

    def set():
        m_call = m_call_input.text()
        m_qth = m_qth_input.text()
        m_dig = m_dig_input.text()
        aouto_save_b = aouto_save.isChecked()
        aouto_list_b = aouto_list_.isChecked()
        print(f"保存设置: 我的呼号={m_call}, 我的QTH={m_qth}, 我的设备={m_dig}, 自动保存={aouto_save_b}, 自动按时间排序={aouto_list_b}")
        with open('file/m_xml.txt', 'w', encoding='utf-8') as f:
            f.write(str({
                'm_call': m_call,
                'm_qth': m_qth,
                'm_dig': m_dig,
                'aouto_save': aouto_save_b,
                'aouto_list': aouto_list_b
            }))
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

                QMessageBox.information(window, "从之前版本导入数据", f"成功导入{back_item}\n（目前不支持从之前版本中导入插件）")
                window.close()
            else:
                QMessageBox.warning(window, "从之前版本导入数据", "请选择之前版本 F HamLog.exe 所在的文件夹！")
                back_set()

    window.resize(650, 400)
    window.setFixedSize(650, 400)
    window.setWindowTitle('设置')
    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)
    m_call_label = QLabel("我的呼号:", central_widget)
    m_call_input = QLineEdit(central_widget)
    m_call_input.setText(m_call)
    m_qth_label = QLabel("我的QTH:", central_widget)
    m_qth_input = QLineEdit(central_widget)
    m_qth_input.setText(m_qth)
    m_dig_label = QLabel("我的设备:", central_widget)
    m_dig_input = QLineEdit(central_widget)
    m_dig_input.setText(m_dig)
    aouto_save = QCheckBox("自动保存", central_widget)
    aouto_save.setChecked(aouto_save_b)
    aouto_list_ = QCheckBox("自动按时间排序", central_widget)
    aouto_list_.setChecked(aouto_list_b)
    h_layout = QHBoxLayout()
    h_layout.addWidget(aouto_save)
    h_layout.addWidget(aouto_list_)
    sett_button = QPushButton("保存更改", central_widget)
    sett_button.clicked.connect(lambda: set())
    layout.addWidget(m_call_label)
    layout.addWidget(m_call_input)
    layout.addWidget(m_qth_label)
    layout.addWidget(m_qth_input)
    layout.addWidget(m_dig_label)
    layout.addWidget(m_dig_input)
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

    fk_v = QLabel("F HamLog 版本：1.9.0", central_widget)
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