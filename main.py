from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
import sys
import json
import webbrowser
import urllib.parse
import fhl_rw

def main():
    def quick_project():
        print("通联日志")
        import project
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
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        project.main(project_window)

    def open_project():
        print("打开项目")
        import project
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        save_path = ''
        save_path, _ = QFileDialog.getOpenFileName(
            window,  # 父窗口
            "打开项目",  # 对话框标题
            "",  # 初始目录
            "F HamLog项目 (*.fhl)"  # 文件过滤器
        )
        if save_path == '':
            return
        print(save_path)
        data,key = fhl_rw.read_fhl_file(save_path)
        if data == None:
            return
        project.main(project_window, data, save_path,key_=key)

    '''    
    def remote_project():
        print("远程项目")
        import remote_project
        global project_window  # 保持引用，防止被回收
        project_window = QMainWindow()
        remote_project.main(project_window)'''
    
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
    
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("file/F_HamLog.ico"))

    global window
    window = QMainWindow()
    window.resize(500, 300)
    window.setFixedSize(500, 300)
    window.setWindowTitle('F HamLog 2')

    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(20, 20, 20, 7)
    #main_layout.setSpacing(10)
    #main_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

    text_label = QLabel("F HamLog 2")
    text_label.setAlignment(Qt.AlignCenter)
    font_t = text_label.font()
    font_t.setPointSize(15)
    font_t.setBold(True)
    text_label.setFont(font_t)
    main_layout.addWidget(text_label)

    text_label2 = QLabel("通联日志！")
    text_label2.setAlignment(Qt.AlignCenter)
    font_i = text_label2.font()
    font_i.setPointSize(10)
    text_label2.setFont(font_i)
    main_layout.addWidget(text_label2)

    text_endl = QLabel(" ")
    text_endl.setAlignment(Qt.AlignCenter)
    font_i = text_endl.font()
    font_i.setPointSize(8)
    text_endl.setFont(font_i)
    main_layout.addWidget(text_endl)


    button_quick = QPushButton("通联日志")
    button_quick.setFixedSize(200, 50)
    button_quick.clicked.connect(quick_project)
    main_layout.addWidget(button_quick, alignment=Qt.AlignHCenter)

    row_widget = QWidget()
    row_widget.setFixedSize(200, 40)

    h_layout = QHBoxLayout(row_widget)
    h_layout.setContentsMargins(0, 0, 0, 0)
    h_layout.setSpacing(0)

    button_batch = QPushButton("批量记录")
    button_batch.setFixedSize(100, 40)
    button_batch.clicked.connect(batch_project)
    h_layout.addWidget(button_batch)

    button_qrz = QPushButton("QRZ主页")
    button_qrz.setFixedSize(100, 40)
    h_layout.addWidget(button_qrz)
    button_qrz.clicked.connect(qrz_page)

    main_layout.addWidget(row_widget, alignment=Qt.AlignHCenter)

    row_widget2 = QWidget()
    row_widget2.setFixedSize(200, 40)
    h_layout2 = QHBoxLayout(row_widget2)
    h_layout2.setContentsMargins(0, 0, 0, 0)
    h_layout2.setSpacing(0)

    button_start = QPushButton("新建项目")
    button_start.setFixedSize(100, 40)
    button_start.clicked.connect(new_project)
    h_layout2.addWidget(button_start)

    button_open = QPushButton("打开项目")
    button_open.setFixedSize(100, 40)
    button_open.clicked.connect(open_project)
    h_layout2.addWidget(button_open)

    main_layout.addWidget(row_widget2, alignment=Qt.AlignHCenter)

    '''
    button_open = QPushButton("远程日志")
    button_open.setFixedSize(100, 40)
    button_open.clicked.connect(remote_project)'''

    line = QFrame(central_widget)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)  # 设置线宽
    main_layout.addWidget(line)

    button_set = QPushButton("设置")
    button_set.setFixedSize(100, 40)
    button_set.clicked.connect(set)
    main_layout.addWidget(button_set, alignment=Qt.AlignHCenter)

    main_layout.addStretch(1)

    window.show()
    app.exec()

if __name__ == '__main__':
    main()