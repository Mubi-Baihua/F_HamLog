from PySide6.QtWidgets import *
def main(window):
    with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
        xml_dict = eval(f.read())
    m_call = xml_dict['m_call']
    m_qth = xml_dict['m_qth']
    m_dig = xml_dict['m_dig']
    def set():
        m_call = m_call_input.text()
        m_qth = m_qth_input.text()
        m_dig = m_dig_input.text()
        print(f"保存设置: 我的呼号={m_call}, 我的QTH={m_qth}, 我的设备={m_dig}")
        with open('file/m_xml.txt', 'w', encoding='utf-8') as f:
            f.write(str({
                'm_call': m_call,
                'm_qth': m_qth,
                'm_dig': m_dig
            }))
        window.close()
    window.resize(500, 300)
    window.setFixedSize(500, 300)
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
    sett_button = QPushButton("保存", central_widget)
    sett_button.clicked.connect(lambda: set())
    layout.addWidget(m_call_label)
    layout.addWidget(m_call_input)
    layout.addWidget(m_qth_label)
    layout.addWidget(m_qth_input)
    layout.addWidget(m_dig_label)
    layout.addWidget(m_dig_input)
    layout.addWidget(sett_button)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    fk_l = QLabel("问题反馈到：13577106233@163.com\n版本更新请访问：https://mubi-baihua.github.io", central_widget)
    layout.addWidget(fk_l)

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    layout.addWidget(line)

    fk_v = QLabel("F HamLog 版本：1.2.0", central_widget)
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