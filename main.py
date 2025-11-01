from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
import sys
def main():
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
        with open(save_path, 'r', encoding='utf-8') as f:
            project.main(project_window, f.read(), save_path)
    def set():
        print("设置")
        import set
        global set_window  # 保持引用，防止被回收
        set_window = QMainWindow()
        set.main(set_window)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("file/F_HamLog.ico"))

    global window
    window = QMainWindow()
    window.resize(500, 300)
    window.setFixedSize(500, 300)
    window.setWindowTitle('F HamLog 1')

    text_label = QLabel("F HamLog 1", window)
    text_label.setGeometry(0, 25, 500, 30)
    text_label.setAlignment(Qt.AlignCenter)
    font_t = text_label.font()
    font_t.setPointSize(14)
    font_t.setBold(True)
    text_label.setFont(font_t)

    text_label2 = QLabel("通联日志！", window)
    text_label2.setGeometry(0, 50, 500, 30)
    text_label2.setAlignment(Qt.AlignCenter)
    font_i = text_label2.font()
    font_i.setPointSize(10)
    text_label2.setFont(font_i)

    button_start = QPushButton("新建项目", window)
    button_start.setGeometry(200, 100, 100, 30)
    button_start.resize(100, 50)
    button_start.clicked.connect(new_project)

    button_open = QPushButton("打开项目", window)
    button_open.setGeometry(200, 150, 100, 30)
    button_open.resize(100, 50)
    button_open.clicked.connect(open_project)

    button_set = QPushButton("设置", window)
    button_set.setGeometry(200, 200, 100, 30)
    button_set.resize(100, 50)
    button_set.clicked.connect(set)

    window.show()
    app.exec()

if __name__ == '__main__':
    main()